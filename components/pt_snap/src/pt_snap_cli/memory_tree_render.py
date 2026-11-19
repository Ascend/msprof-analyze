# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2026 Huawei Technologies Co.,Ltd.
#
# MindStudio is licensed under Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#
#          http://license.coscl.org.cn/MulanPSL2
#
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND,
# EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
# MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.
# See the Mulan PSL v2 for more details.
# -------------------------------------------------------------------------

"""Presentation of complete frame trees; occupancy comes from the query layer."""

from __future__ import annotations

import json
from typing import Dict, List, cast

from pt_snap_cli.core.common.models import QueryResult


def render_memory_tree(result: QueryResult, event_id: int, *, html: bool = False) -> str:
    """Render an indented breakdown or a self-contained interactive flamegraph."""
    if result.truncated or result.has_more:
        raise ValueError("A complete frame tree is required to render a memory breakdown.")
    _validate_complete_tree(result.rows)
    title = f"Active memory after event {event_id} · device {result.device_id}"
    if html:
        payload = json.dumps({"title": title, "nodes": result.rows}, ensure_ascii=False)
        # Frame text is untrusted. Escape HTML script delimiters in the data;
        # the renderer inserts labels using textContent, never innerHTML.
        payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        return _HTML.replace("__TREE_DATA__", payload)

    children: Dict[str, List[Dict[str, object]]] = {}
    for row in result.rows:
        children.setdefault(str(row["parent_id"]), []).append(row)
    lines = [title, "Inclusive bytes / self bytes / live blocks"]
    pending = list(reversed(children.get("None", [])))
    while pending:
        row = pending.pop()
        depth = cast(int, row["depth"])
        # Keep each captured frame on one terminal line, even with unusual names.
        label = json.dumps(str(row["label"]), ensure_ascii=False)[1:-1]
        lines.append(f"{'  ' * depth}{label}: {row['size_bytes']} / {row['self_bytes']} / {row['block_count']}")
        pending.extend(reversed(children.get(str(row["node_id"]), [])))
    return "\n".join(lines)


def _validate_complete_tree(rows: List[Dict[str, object]]) -> None:
    """Never display a partial/orphaned graph as a complete occupancy tree."""
    nodes = {str(row["node_id"]): row for row in rows}
    error = "A complete frame tree is required to render a memory breakdown."
    if len(nodes) != len(rows) or "root" not in nodes:
        raise ValueError(error)
    totals: Dict[str, List[int]] = {node_id: [0, 0, 0] for node_id in nodes}
    fields = (
        ("size_bytes", "self_bytes"),
        ("requested_bytes", "self_requested_bytes"),
        ("block_count", "self_block_count"),
    )
    for node_id, row in nodes.items():
        parent_id = row["parent_id"]
        if node_id == "root":
            if parent_id is not None or row["depth"] != 0:
                raise ValueError(error)
        elif not isinstance(parent_id, str) or parent_id not in nodes:
            raise ValueError(error)
        elif cast(int, row["depth"]) != cast(int, nodes[parent_id]["depth"]) + 1:
            raise ValueError(error)
        for index, (total, own) in enumerate(fields):
            # pylint: disable-next=unidiomatic-typecheck  # Reject bool/subclasses: the contract requires exact scalar types.
            if type(row[total]) is not int or type(row[own]) is not int:
                raise ValueError(error)
            if cast(int, row[total]) < 0 or cast(int, row[own]) < 0:
                raise ValueError(error)
            if isinstance(parent_id, str):
                totals[parent_id][index] += cast(int, row[total])
    for node_id, row in nodes.items():
        if any(row[total] != cast(int, row[own]) + totals[node_id][index] for index, (total, own) in enumerate(fields)):
            raise ValueError(error)


_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>pt-snap memory flamegraph</title>
<style>
body{font:14px system-ui,sans-serif;background:#f8fafc;color:#172033;margin:24px}
h1{font-size:22px}p{max-width:960px;line-height:1.6}
button,input{font:inherit;padding:8px 12px;border:1px solid #cbd5e1;border-radius:6px}
input{width:260px;margin:0 12px}svg{width:100%;background:white;border-radius:8px;margin-top:20px}
.node{cursor:pointer}.node:hover rect{stroke:#0f172a;stroke-width:2}
text{pointer-events:none;font:12px system-ui,sans-serif;fill:#172033}
.navigation{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr));gap:20px}
.node-list{list-style:none;padding:0;max-height:320px;overflow:auto}
.node-list li{margin:6px 0}.node-list button{width:100%;text-align:left;white-space:pre-wrap;overflow-wrap:anywhere;background:white}
button{cursor:pointer}button:disabled{cursor:default}button:focus-visible{outline:3px solid #2563eb;outline-offset:2px}
#focus-path{overflow-wrap:anywhere}h2{font-size:16px}
#detail{padding:12px;background:#e2e8f0;white-space:pre-wrap;overflow-wrap:anywhere}
</style></head><body><h1 id="heading"></h1>
<p>Width = live block bytes, not execution time. Each level groups allocation frames by caller path.
Inclusive = self + direct children. Pending-free blocks stay live until free_completed.
Static, preexisting, empty and missing stacks are separate leaves. Click a frame to zoom; hover for details.
Use the lists below to reach frames too small to click, including zero-byte frames. Buttons support Enter and Space.</p>
<button id="reset" type="button">Reset zoom</button>
<button id="parent" type="button">Parent frame</button>
<label>Find frame <input id="search" type="search" placeholder="Filename, function or node ID"></label>
<span id="summary"></span><svg id="chart" role="img" aria-label="Active memory flamegraph"></svg>
<p id="focus-path" tabindex="-1" aria-live="polite"></p>
<p id="detail" aria-live="polite"></p>
<div class="navigation">
<section aria-labelledby="children-heading"><h2 id="children-heading">Children of selected frame</h2>
<p id="children-status" role="status"></p><ul id="children-list" class="node-list"></ul></section>
<section aria-labelledby="search-heading"><h2 id="search-heading">Search results · entire tree</h2>
<p id="search-status" role="status"></p><ul id="search-results" class="node-list"></ul></section>
</div>
<script id="tree-data" type="application/json">__TREE_DATA__</script>
<script>
const data=JSON.parse(document.getElementById('tree-data').textContent);
document.getElementById('heading').textContent=data.title;
const nodes=new Map(data.nodes.map(n=>[n.node_id,n])),children=new Map();
for(const n of data.nodes){if(n.parent_id!==null){
 if(!children.has(n.parent_id))children.set(n.parent_id,[]);children.get(n.parent_id).push(n);}}
for(const list of children.values())list.sort((a,b)=>b.size_bytes-a.size_bytes||a.node_id.localeCompare(b.node_id));
const svg=document.getElementById('chart'),ns='http://www.w3.org/2000/svg';
let focus='root';
function element(tag,attrs){const el=document.createElementNS(ns,tag);
 for(const [k,v] of Object.entries(attrs))el.setAttribute(k,String(v));return el;}
function detail(n){return n.label+'\\nNode ID: '+n.node_id+'\\nInclusive: '+n.size_bytes.toLocaleString()+' bytes'+
 '\\nSelf: '+n.self_bytes.toLocaleString()+' bytes\\nRequested: '+n.requested_bytes.toLocaleString()+
 ' bytes\\nLive blocks: '+n.block_count+'\\nShare of all selected memory: '+
 (n.percent_of_total===null?'n/a':n.percent_of_total+'%');}
function path(n){const labels=[];
 while(n){labels.push(n.label);n=nodes.get(n.parent_id);}return labels.reverse().join(' → ');}
function matches(n,query){return n.label.toLowerCase().includes(query)||n.node_id.toLowerCase().includes(query);}
function select(nodeId){focus=nodeId;draw();navigation();
 document.getElementById('focus-path').focus({preventScroll:true});}
function nodeButton(n){const button=document.createElement('button');button.type='button';
 button.dataset.nodeId=n.node_id;
 button.textContent=path(n)+' · '+n.size_bytes.toLocaleString()+' bytes · ID: '+n.node_id;
 button.addEventListener('click',()=>select(n.node_id));return button;}
function listNodes(id,list){const target=document.getElementById(id),items=document.createDocumentFragment();
 for(const n of list){const item=document.createElement('li');item.append(nodeButton(n));items.append(item);}
 target.replaceChildren(items);}
function navigation(){const base=nodes.get(focus),list=children.get(focus)||[];
 document.getElementById('parent').disabled=base.parent_id===null;
 document.getElementById('focus-path').textContent='Selected path: '+path(base);
 document.getElementById('detail').textContent=detail(base);
 document.getElementById('children-status').textContent=list.length?list.length+' direct children.':'No child frames.';
 listNodes('children-list',list);}
function search(){const query=document.getElementById('search').value.trim().toLowerCase();
 const results=query?data.nodes.filter(n=>matches(n,query)):[];
 document.getElementById('search-status').textContent=!query?'Search all frames by filename, function or node ID.':
  results.length?results.length+' matching frames in the entire tree.':'No matching frames.';
 listNodes('search-results',results);draw();}
function draw(){svg.replaceChildren();const base=nodes.get(focus);if(!base)return;
 const query=document.getElementById('search').value.trim().toLowerCase();let maxDepth=0;
 const pending=[{n:base,x:0,w:1200,d:0}];let serial=0;
 while(pending.length){const {n,x,w,d}=pending.pop();maxDepth=Math.max(maxDepth,d);
  const y=d*28,group=element('g',{class:'node','data-node-id':n.node_id}),clipId='clip-'+serial++;
  const hit=query&&matches(n,query);
  const hue=n.category==='dynamic_live_at_event'?35+(Number(n.frame_id)%8)*5:205;
  group.append(element('rect',{x,y,width:Math.max(0,w-0.6),height:26,fill:hit?'#facc15':
   'hsl('+hue+' 85% 72%)'}));
  const clip=element('clipPath',{id:clipId});clip.append(element('rect',{x:x+4,y,width:Math.max(0,w-8),height:26}));
  group.append(clip);const text=element('text',{x:x+5,y:y+18,'clip-path':'url(#'+clipId+')'});
  text.textContent=n.label;group.append(text);const tooltip=element('title',{});
  tooltip.textContent=detail(n);group.append(tooltip);
  group.addEventListener('mouseenter',()=>document.getElementById('detail').textContent=detail(n));
  group.addEventListener('click',()=>select(n.node_id));svg.append(group);
  let childX=x;const next=[];
  for(const child of children.get(n.node_id)||[]){const cw=n.size_bytes>0?w*child.size_bytes/n.size_bytes:0;
   next.push({n:child,x:childX,w:cw,d:d+1});childX+=cw;}
  for(let i=next.length-1;i>=0;i--)pending.push(next[i]);
 }
 svg.setAttribute('viewBox','0 0 1200 '+((maxDepth+1)*28));
 document.getElementById('summary').textContent='Showing '+base.size_bytes.toLocaleString()+' bytes';
}
document.getElementById('reset').addEventListener('click',()=>select('root'));
document.getElementById('parent').addEventListener('click',()=>{const parent=nodes.get(focus).parent_id;
 if(parent!==null)select(parent);});
document.getElementById('search').addEventListener('input',search);navigation();search();
</script></body></html>
"""
