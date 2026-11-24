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

"""Exercise frame navigation with real Chromium events, including invisible frames.

Set PT_SNAP_TEST_CHROMIUM to use an existing Chromium executable. CI sets
PT_SNAP_REQUIRE_BROWSER=1 so a missing browser cannot silently skip these tests.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

import pytest

from pt_snap_cli.core.common.models import QueryResult
from pt_snap_cli.memory_tree_render import render_memory_tree
from test._browser_support import browser_expect as expect

pytestmark = pytest.mark.browser

ROOT_BYTES = 471_498_368
GIANT_BYTES = 283_057_288
MALICIOUS_LABEL = (
    '路径/中文 </script><img src=x onerror="window.__frameInjected=true"><script>window.__frameInjected=true</script>'
)


def _complete_rows(specifications):
    """Build an internally consistent tree from preorder (id, parent, label, self)."""
    rows = []
    by_id = {}
    for node_id, parent_id, label, own_bytes in specifications:
        own_blocks = int(own_bytes > 0)
        row = {
            "node_id": node_id,
            "parent_id": parent_id,
            "label": label,
            "depth": 0 if parent_id is None else by_id[parent_id]["depth"] + 1,
            "frame_id": len(rows),
            "category": "dynamic_live_at_event",
            "size_bytes": own_bytes,
            "self_bytes": own_bytes,
            "requested_bytes": own_bytes,
            "self_requested_bytes": own_bytes,
            "block_count": own_blocks,
            "self_block_count": own_blocks,
        }
        rows.append(row)
        by_id[node_id] = row
    for row in reversed(rows):
        if row["parent_id"] is not None:
            parent = by_id[row["parent_id"]]
            for field in ("size_bytes", "requested_bytes", "block_count"):
                parent[field] += row[field]
    total = by_id["root"]["size_bytes"]
    for row in rows:
        row["percent_of_total"] = 100 * row["size_bytes"] / total if total else None
    return rows


@pytest.fixture
def frame_rows():
    rows = _complete_rows(
        [
            ("root", None, "All active memory", 0),
            ("frame:giant", "root", "giant_branch", GIANT_BYTES - 40),
            ("frame:giant/tiny", "frame:giant", "shared_function", 40),
            ("frame:giant/zero", "frame:giant", "zero_parent", 0),
            ("frame:giant/zero/leaf", "frame:giant/zero", "zero_leaf", 0),
            ("frame:other", "root", "other_branch", ROOT_BYTES - GIANT_BYTES - 40),
            ("frame:other/tiny", "frame:other", "shared_function", 40),
            ("frame:malicious", "root", MALICIOUS_LABEL, 0),
        ]
    )
    assert rows[0]["size_bytes"] == ROOT_BYTES
    assert rows[1]["size_bytes"] == GIANT_BYTES
    return rows


@pytest.fixture
def browser_page(chromium_browser) -> Iterator:
    context = chromium_browser.new_context(viewport={"width": 1440, "height": 1000}, locale="en-US")
    errors = []
    try:
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        yield page
    finally:
        context.close()
        assert not errors, f"Uncaught browser errors: {errors}"


def _render(page, rows):
    result = QueryResult(
        total=len(rows),
        returned=len(rows),
        device_id=0,
        rows=rows,
        template="active_memory_frame_tree_at_event",
        total_is_exact=True,
    )
    page.set_content(render_memory_tree(result, event_id=17, html=True), wait_until="load")
    expect(page.locator("#chart .node").first).to_be_attached()


def _button(page, container, node_id):
    return page.locator(f'#{container} button[data-node-id="{node_id}"]')


def _rect(page, node_id):
    return page.locator(f'#chart .node[data-node-id="{node_id}"] > rect').first


def _geometry(page):
    return page.locator("#chart .node").evaluate_all("""groups => groups.map(group => {
            const rect = group.querySelector('rect');
            return [group.dataset.nodeId, rect.getAttribute('x'),
                    rect.getAttribute('y'), rect.getAttribute('width')];
        })""")


def _assert_path(locator, *labels):
    text = locator.inner_text()
    positions = [text.index(label) for label in labels]
    assert positions == sorted(positions), text


def _assert_selected(page, node_id, *labels):
    expect(page.locator("#chart .node").first).to_have_attribute("data-node-id", node_id)
    expect(page.locator("#detail")).to_contain_text(node_id)
    _assert_path(page.locator("#focus-path"), *labels)


def _tab_to(page, target):
    """Reach the control through the browser's native sequential focus order."""
    page.locator("#search").focus()
    for _ in range(350):
        page.keyboard.press("Tab")
        if target.evaluate("element => element === document.activeElement"):
            return
    pytest.fail(f"Control is not reachable with Tab: {target}")


def test_search_keeps_true_proportional_geometry_until_navigation(browser_page, frame_rows):
    page = browser_page
    _render(page, frame_rows)
    expect(page.get_by_role("button", name="Parent frame", exact=True)).to_be_disabled()
    expect(page.locator("#search-status")).not_to_be_empty()
    expect(page.locator("#search-results button")).to_have_count(0)
    _assert_selected(page, "root", "All active memory")

    giant_width = float(_rect(page, "frame:giant").get_attribute("width"))
    assert giant_width == pytest.approx(1200 * GIANT_BYTES / ROOT_BYTES - 0.6)
    assert float(_rect(page, "frame:giant/tiny").get_attribute("width")) == 0
    assert float(_rect(page, "frame:giant/zero/leaf").get_attribute("width")) == 0
    original_geometry = _geometry(page)

    page.locator("#search").fill("SHARED_FUNCTION")
    expect(page.locator("#search-results button")).to_have_count(2)
    assert _geometry(page) == original_geometry
    _assert_selected(page, "root", "All active memory")

    _button(page, "search-results", "frame:giant/tiny").click()
    _assert_selected(page, "frame:giant/tiny", "All active memory", "giant_branch", "shared_function")
    assert float(_rect(page, "frame:giant/tiny").get_attribute("width")) == pytest.approx(1199.4)
    page.locator("#reset").click()
    assert _geometry(page) == original_geometry


def test_search_disambiguates_duplicate_paths_and_supports_native_keyboard(browser_page, frame_rows):
    page = browser_page
    _render(page, frame_rows)
    page.locator("#search").fill("sHaReD_fUnCtIoN")
    expect(page.locator("#search-results button")).to_have_count(2)
    expect(page.locator("#search-status")).to_contain_text(re.compile(r"\b2\b"))
    for node_id, branch in (
        ("frame:giant/tiny", "giant_branch"),
        ("frame:other/tiny", "other_branch"),
    ):
        button = _button(page, "search-results", node_id)
        _assert_path(button, "All active memory", branch, "shared_function")
        expect(button).to_contain_text(node_id)
        expect(button).to_contain_text(re.compile(r"40\s+bytes", re.IGNORECASE))
    target = _button(page, "search-results", "frame:giant/tiny")
    _tab_to(page, target)
    page.keyboard.press("Enter")
    _assert_selected(page, "frame:giant/tiny", "All active memory", "giant_branch", "shared_function")
    expect(page.locator("#detail")).to_contain_text("Inclusive: 40 bytes")

    # The other same-named frame remains available outside the focused subtree.
    expect(page.locator("#search-results button")).to_have_count(2)
    target = _button(page, "search-results", "frame:other/tiny")
    _tab_to(page, target)
    page.keyboard.press("Space")
    _assert_selected(page, "frame:other/tiny", "All active memory", "other_branch", "shared_function")


def test_node_id_search_is_case_insensitive_and_global_after_focus(browser_page, frame_rows):
    page = browser_page
    _render(page, frame_rows)
    _button(page, "children-list", "frame:giant").click()
    page.locator("#search").fill("FRAME:OTHER/TINY")
    expect(page.locator("#search-results button")).to_have_count(1)
    _button(page, "search-results", "frame:other/tiny").click()
    _assert_selected(page, "frame:other/tiny", "All active memory", "other_branch", "shared_function")
    page.locator("#search").fill("ZERO_LEAF")
    expect(page.locator("#search-results button")).to_have_count(1)
    _button(page, "search-results", "frame:giant/zero/leaf").click()
    _assert_selected(
        page,
        "frame:giant/zero/leaf",
        "All active memory",
        "giant_branch",
        "zero_parent",
        "zero_leaf",
    )
    expect(page.locator("#detail")).to_contain_text("Inclusive: 0 bytes")


def test_children_reach_tiny_and_zero_frames_and_parent_retraces_path(browser_page, frame_rows):
    page = browser_page
    _render(page, frame_rows)
    expect(page.locator("#children-list button")).to_have_count(3)
    giant = _button(page, "children-list", "frame:giant")
    _assert_path(giant, "All active memory", "giant_branch")
    expect(giant).to_contain_text("frame:giant")
    expect(giant).to_contain_text("283,057,288 bytes")
    giant.click()
    expect(page.locator("#children-list button")).to_have_count(2)

    tiny = _button(page, "children-list", "frame:giant/tiny")
    _assert_path(tiny, "All active memory", "giant_branch", "shared_function")
    expect(tiny).to_contain_text("40 bytes")
    _tab_to(page, tiny)
    page.keyboard.press("Enter")
    _assert_selected(page, "frame:giant/tiny", "All active memory", "giant_branch", "shared_function")
    expect(page.locator("#children-list button")).to_have_count(0)
    expect(page.locator("#children-status")).not_to_be_empty()
    page.get_by_role("button", name="Parent frame", exact=True).click()

    zero = _button(page, "children-list", "frame:giant/zero")
    expect(zero).to_contain_text("0 bytes")
    _tab_to(page, zero)
    page.keyboard.press("Space")
    _assert_selected(page, "frame:giant/zero", "All active memory", "giant_branch", "zero_parent")
    _button(page, "children-list", "frame:giant/zero/leaf").click()
    _assert_selected(
        page,
        "frame:giant/zero/leaf",
        "All active memory",
        "giant_branch",
        "zero_parent",
        "zero_leaf",
    )
    expect(page.locator("#children-list button")).to_have_count(0)
    expect(page.locator("#children-status")).not_to_be_empty()
    for node_id, labels in (
        ("frame:giant/zero", ("All active memory", "giant_branch", "zero_parent")),
        ("frame:giant", ("All active memory", "giant_branch")),
        ("root", ("All active memory",)),
    ):
        page.get_by_role("button", name="Parent frame", exact=True).click()
        _assert_selected(page, node_id, *labels)
    expect(page.get_by_role("button", name="Parent frame", exact=True)).to_be_disabled()


def test_reset_is_repeatable_and_preserves_global_search(browser_page, frame_rows):
    page = browser_page
    _render(page, frame_rows)
    original_geometry = _geometry(page)
    page.locator("#search").fill("shared_function")
    for node_id in ("frame:giant/tiny", "frame:other/tiny", "frame:giant/tiny"):
        _button(page, "search-results", node_id).click()
        page.locator("#reset").click()
        _assert_selected(page, "root", "All active memory")
        expect(page.locator("#search")).to_have_value("shared_function")
        expect(page.locator("#search-results button")).to_have_count(2)
        expect(page.locator("#children-list button")).to_have_count(3)
        expect(page.get_by_role("button", name="Parent frame", exact=True)).to_be_disabled()
        assert _geometry(page) == original_geometry
    page.locator("#reset").click()
    _assert_selected(page, "root", "All active memory")


def test_no_results_and_clearing_search_leave_navigation_usable(browser_page, frame_rows):
    page = browser_page
    _render(page, frame_rows)
    instructions = page.locator("#search-status").inner_text()
    _button(page, "children-list", "frame:giant").click()
    geometry = _geometry(page)
    page.locator("#search").fill("there is no such frame")
    expect(page.locator("#search-results button")).to_have_count(0)
    expect(page.locator("#search-status")).to_have_text("No matching frames.")
    assert _geometry(page) == geometry
    _assert_selected(page, "frame:giant", "All active memory", "giant_branch")
    expect(page.locator("#children-list button")).to_have_count(2)
    page.locator("#search").fill("")
    expect(page.locator("#search-status")).to_have_text(instructions)
    expect(page.locator("#search-results button")).to_have_count(0)
    _button(page, "children-list", "frame:giant/tiny").click()
    _assert_selected(page, "frame:giant/tiny", "All active memory", "giant_branch", "shared_function")


def test_unicode_and_html_like_labels_remain_plain_text_everywhere(browser_page, frame_rows):
    page = browser_page
    _render(page, frame_rows)
    root_child = _button(page, "children-list", "frame:malicious")
    expect(root_child).to_contain_text(MALICIOUS_LABEL)
    page.locator("#search").fill("中文")
    expect(page.locator("#search-results button")).to_have_count(1)
    result = _button(page, "search-results", "frame:malicious")
    expect(result).to_contain_text(MALICIOUS_LABEL)
    result.click()
    _assert_selected(page, "frame:malicious", "All active memory", MALICIOUS_LABEL)
    expect(page.locator("#detail")).to_contain_text(MALICIOUS_LABEL)
    expect(page.locator("#chart text")).to_have_text(MALICIOUS_LABEL)
    expect(page.locator("img")).to_have_count(0)
    expect(page.locator("script")).to_have_count(2)
    assert page.evaluate("window.__frameInjected === undefined")
    page.locator("#reset").click()
    expect(_button(page, "children-list", "frame:malicious")).to_contain_text(MALICIOUS_LABEL)


def test_search_does_not_silently_truncate_more_than_100_matches(browser_page):
    page = browser_page
    rows = _complete_rows(
        [("root", None, "All active memory", 0)]
        + [(f"batch:{index:03d}", "root", f"batch frame {index:03d}", 1) for index in range(151)]
    )
    _render(page, rows)
    page.locator("#search").fill("BATCH FRAME")
    expect(page.locator("#search-results button")).to_have_count(151)
    expect(page.locator("#search-status")).to_contain_text(re.compile(r"\b151\b"))
    _button(page, "search-results", "batch:150").click()
    _assert_selected(page, "batch:150", "All active memory", "batch frame 150")
    expect(page.locator("#search-results button")).to_have_count(151)
    page.locator("#reset").click()
    expect(page.locator("#children-list button")).to_have_count(151)


def test_zero_total_tree_can_be_explored_and_reset(browser_page):
    page = browser_page
    rows = _complete_rows(
        [
            ("root", None, "Empty active memory", 0),
            ("empty:branch", "root", "empty branch", 0),
            ("empty:leaf", "empty:branch", "empty leaf", 0),
            ("empty:sibling", "root", "empty sibling", 0),
        ]
    )
    _render(page, rows)
    original_geometry = _geometry(page)
    assert float(_rect(page, "empty:branch").get_attribute("width")) == 0
    expect(page.locator("#children-list button")).to_have_count(2)
    _button(page, "children-list", "empty:branch").click()
    leaf = _button(page, "children-list", "empty:leaf")
    _tab_to(page, leaf)
    page.keyboard.press("Enter")
    _assert_selected(page, "empty:leaf", "Empty active memory", "empty branch", "empty leaf")
    expect(page.locator("#detail")).to_contain_text("Inclusive: 0 bytes")
    expect(page.locator("#detail")).to_contain_text("n/a")
    expect(page.locator("#children-status")).not_to_be_empty()
    page.locator("#search").fill("empty sibling")
    _button(page, "search-results", "empty:sibling").click()
    _assert_selected(page, "empty:sibling", "Empty active memory", "empty sibling")
    page.locator("#reset").click()
    _assert_selected(page, "root", "Empty active memory")
    assert _geometry(page) == original_geometry
    assert "NaN" not in page.locator("#chart").inner_html()
    assert "Infinity" not in page.locator("#chart").inner_html()


def test_existing_svg_click_and_hover_keep_working(browser_page, frame_rows):
    page = browser_page
    _render(page, frame_rows)
    _rect(page, "frame:giant").hover()
    expect(page.locator("#detail")).to_contain_text("283,057,288 bytes")
    _rect(page, "frame:giant").click()
    _assert_selected(page, "frame:giant", "All active memory", "giant_branch")
    expect(page.locator("#children-list button")).to_have_count(2)
    page.locator("#reset").click()
    _assert_selected(page, "root", "All active memory")


def test_keyboard_focus_survives_continuous_descent_parent_and_reset(browser_page, frame_rows):
    page = browser_page
    _render(page, frame_rows)
    path = page.locator("#focus-path")
    _button(page, "children-list", "frame:giant").click()
    expect(path).to_be_focused()

    # No focus() helper between navigations: the next Tab reaches the new children.
    page.keyboard.press("Tab")
    expect(_button(page, "children-list", "frame:giant/tiny")).to_be_focused()
    page.keyboard.press("Tab")
    expect(_button(page, "children-list", "frame:giant/zero")).to_be_focused()
    page.keyboard.press("Space")
    expect(path).to_be_focused()
    page.keyboard.press("Tab")
    expect(_button(page, "children-list", "frame:giant/zero/leaf")).to_be_focused()
    page.keyboard.press("Enter")
    _assert_selected(
        page,
        "frame:giant/zero/leaf",
        "All active memory",
        "giant_branch",
        "zero_parent",
        "zero_leaf",
    )
    expect(path).to_be_focused()

    page.keyboard.press("Shift+Tab")
    expect(page.locator("#search")).to_be_focused()
    page.keyboard.press("Shift+Tab")
    expect(page.get_by_role("button", name="Parent frame", exact=True)).to_be_focused()
    page.keyboard.press("Enter")
    _assert_selected(page, "frame:giant/zero", "All active memory", "giant_branch", "zero_parent")
    expect(path).to_be_focused()

    for _ in range(3):
        page.keyboard.press("Shift+Tab")
    expect(page.locator("#reset")).to_be_focused()
    page.keyboard.press("Space")
    _assert_selected(page, "root", "All active memory")
    expect(path).to_be_focused()
    expect(page.get_by_role("button", name="Parent frame", exact=True)).to_be_disabled()
    page.keyboard.press("Tab")
    expect(_button(page, "children-list", "frame:giant")).to_be_focused()


def test_special_allocation_categories_remain_reachable(browser_page):
    page = browser_page
    categories = (
        ("static", "[static]", "static"),
        ("preexisting_live_at_event", "[preexisting live]", "preexisting_live_at_event"),
        ("empty_callstack", "[empty captured callstack]", "empty_callstack"),
        ("missing", "[missing callstack]", "dynamic_live_at_event"),
    )
    rows = _complete_rows(
        [("root", None, "All active memory", ROOT_BYTES)]
        + [(node_id, "root", label, 0) for node_id, label, _ in categories]
    )
    for row, (_, _, category) in zip(rows[1:], categories, strict=True):
        row["category"] = category
        row["frame_id"] = None
    _render(page, rows)
    for node_id, label, _ in categories:
        assert float(_rect(page, node_id).get_attribute("width")) == 0
        _button(page, "children-list", node_id).click()
        _assert_selected(page, node_id, "All active memory", label)
        expect(page.locator("#children-status")).not_to_be_empty()
        page.locator("#reset").click()
        page.locator("#search").fill(node_id)
        expect(page.locator("#search-results button")).to_have_count(1)
        _button(page, "search-results", node_id).click()
        _assert_selected(page, node_id, "All active memory", label)
        page.locator("#reset").click()
