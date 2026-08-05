#!/bin/bash
# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------
# This file is part of the MindStudio project.
# Copyright (c) 2026 Huawei Technologies Co.,Ltd.
#
# MindStudio is licensed under Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#
#           http://license.coscl.org.cn/MulanPSL2
#
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND,
# EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
# MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.
# See the Mulan PSL v2 for more details.
# -------------------------------------------------------------------------

log() { echo "[post-create] $*"; }
warn() { echo "[post-create] WARN: $*"; }

# ──────────────────────────────────────────────────────────────────────────────
# 1. 用户级命令目录
# ──────────────────────────────────────────────────────────────────────────────
configure_user_bin() {
    log "Configuring user bin directory..."
    mkdir -p "$HOME/.local/bin"
    npm config set prefix "$HOME/.local" 2>/dev/null || warn "npm config set prefix failed"

    local marker="# msprof-analyze-devcontainer-user-bin"
    for rcfile in "$HOME/.bashrc" "$HOME/.bash_profile"; do
        if [ -f "$rcfile" ] && ! grep -qF "$marker" "$rcfile"; then
            cat >> "$rcfile" <<EOF
$marker
export PATH="\$HOME/.local/bin:\$PATH"
EOF
            log "Appended PATH to $rcfile"
        fi
    done
}

# ──────────────────────────────────────────────────────────────────────────────
# 2. Python 3
# ──────────────────────────────────────────────────────────────────────────────
configure_python3() {
    log "Configuring Python 3..."
    if [ -f "/etc/profile.d/pyenv.sh" ]; then
        source /etc/profile.d/pyenv.sh 2>/dev/null || warn "Failed to source pyenv.sh"
        log "Loaded pyenv profile"
    fi

    for candidate in /opt/python/cp*-cp*; do
        if [ -d "$candidate/bin" ] && [ -x "$candidate/bin/python3" ]; then
            local pyenv_python="$candidate/bin"
            log "Python (pyenv) found at $pyenv_python"

            local marker="# msprof-analyze-pyenv-python"
            for rcfile in "$HOME/.bashrc" "$HOME/.bash_profile"; do
                if [ -f "$rcfile" ] && ! grep -qF "$marker" "$rcfile"; then
                    cat >> "$rcfile" <<EOF
$marker
export PATH="$pyenv_python:\$PATH"
EOF
                    log "Prepended pyenv Python to PATH in $rcfile"
                fi
            done
            export PATH="$pyenv_python:$PATH"
            break
        fi
    done

    if command -v python3 &>/dev/null; then
        log "Python 3 found: $(python3 --version 2>&1)"
    else
        warn "python3 not found in PATH"
    fi
}

# ──────────────────────────────────────────────────────────────────────────────
# 3. 安装编译和测试依赖 (幂等)
# ──────────────────────────────────────────────────────────────────────────────
install_build_deps() {
    log "Installing build dependencies..."

    # --- gitleaks ---
    if ! command -v gitleaks &>/dev/null; then
        log "  Installing gitleaks..."
        GITLEAKS_VER="8.18.4"
        case "$(uname -m)" in
            x86_64)  GITLEAKS_ARCH="amd64";;
            aarch64) GITLEAKS_ARCH="arm64";;
            *)       warn "Unsupported architecture $(uname -m), skipping gitleaks";;
        esac
        if [ -n "$GITLEAKS_ARCH" ]; then
            GITLEAKS_INSTALLED=false
            for MIRROR in \
                "https://ghproxy.com/https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VER}/gitleaks_${GITLEAKS_VER}_linux_${GITLEAKS_ARCH}.tar.gz" \
                "https://mirror.ghproxy.com/https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VER}/gitleaks_${GITLEAKS_VER}_linux_${GITLEAKS_ARCH}.tar.gz" \
                "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VER}/gitleaks_${GITLEAKS_VER}_linux_${GITLEAKS_ARCH}.tar.gz"; do
                log "    Trying: ${MIRROR}"
                curl -fsSL "${MIRROR}" -o /tmp/gitleaks.tar.gz --connect-timeout 10 2>/dev/null && \
                    sudo tar -xzf /tmp/gitleaks.tar.gz -C /usr/local/bin gitleaks 2>/dev/null && \
                    GITLEAKS_INSTALLED=true && break
                rm -f /tmp/gitleaks.tar.gz
            done
            if ${GITLEAKS_INSTALLED}; then
                sudo chmod +x /usr/local/bin/gitleaks
                # CI 兼容：pre-commit 使用 ./gitleaks 入口，在仓库根目录创建软链
                ln -sf /usr/local/bin/gitleaks ./gitleaks 2>/dev/null || true
                log "  gitleaks ${GITLEAKS_VER} (${GITLEAKS_ARCH}) installed"
            else
                warn "gitleaks install failed (all mirrors unreachable)"
            fi
        fi
    else
        log "  System pkg OK: gitleaks"
    fi

    # --- pip 包 ---
    local pip_pkgs=(
        wheel
        pre-commit
        "bandit[toml]"
    )

    for PY in $(command -v python3 2>/dev/null) $(command -v python 2>/dev/null); do
        log "Installing pip packages for: $($PY --version 2>&1)"
        "$PY" -m pip install --quiet --upgrade pip setuptools >/dev/null 2>&1 || warn "pip/setuptools upgrade failed for $PY"

        for pkg in "${pip_pkgs[@]}"; do
            local pkg_name="${pkg%%[*}"
            if ! "$PY" -m pip show "$pkg_name" &>/dev/null; then
                log "  Installing for $PY: $pkg"
                "$PY" -m pip install "$pkg" || warn "pip install failed for $PY: $pkg"
            else
                log "  Pip pkg OK ($PY): $pkg"
            fi
        done
    done

    log "Build dependencies check complete"
}

# ──────────────────────────────────────────────────────────────────────────────
# 4. Git 身份同步
# ──────────────────────────────────────────────────────────────────────────────
sync_git_identity() {
    log "Syncing Git identity..."
    local gitconfig="$HOME/.devcontainer-host-gitconfig"
    if [ -f "$gitconfig" ] && [ -s "$gitconfig" ]; then
        local name email
        name=$(git config --file "$gitconfig" --get user.name 2>/dev/null) || true
        email=$(git config --file "$gitconfig" --get user.email 2>/dev/null) || true
        [ -n "$name" ] && git config --global user.name "$name"
        [ -n "$email" ] && git config --global user.email "$email"
        log "Git identity synced from host"
    else
        warn "No host Git config found, skipping identity sync"
    fi
}

# ──────────────────────────────────────────────────────────────────────────────
# 5. 开发命令提示
# ──────────────────────────────────────────────────────────────────────────────
append_dev_hint_once() {
    local marker="# msprof-analyze-dev-hint"
    local rcfile="$HOME/.bashrc"
    if grep -qF "$marker" "$rcfile" 2>/dev/null; then return; fi

    cat >> "$rcfile" <<EOF
$marker
# msprof-analyze development commands:
#   python3 build.py              Build Release (full)
#   python3 build.py local        Build Release (skip deps)
#   python3 build.py test         Build and run unit tests
#   python3 build.py test local   Run unit tests (skip deps)
EOF
    log "Appended dev hints to $rcfile"
}

# ──────────────────────────────────────────────────────────────────────────────
# 6. pre-commit 自动安装
# ──────────────────────────────────────────────────────────────────────────────
install_pre_commit_hook() {
    log "Installing pre-commit hook..."
    export PATH="$HOME/.local/bin:$PATH"

    local pre_commit_cmd=""
    if command -v pre-commit &>/dev/null; then
        pre_commit_cmd="pre-commit"
    elif python3 -m pre_commit --version &>/dev/null 2>&1; then
        pre_commit_cmd="python3 -m pre_commit"
    elif python -m pre_commit --version &>/dev/null 2>&1; then
        pre_commit_cmd="python -m pre_commit"
    else
        warn "pre-commit not found, skipping hook installation"
        return
    fi

    if ! git rev-parse --git-dir &>/dev/null; then
        warn "Not a Git repository, skipping pre-commit hook"
        return
    fi

    $pre_commit_cmd install || warn "pre-commit install failed"
    log "pre-commit hook installed via: $pre_commit_cmd"
}

# ──────────────────────────────────────────────────────────────────────────────
# 7. 忽略本地可修改的文件
# ──────────────────────────────────────────────────────────────────────────────
ignore_local_changes() {
    log "Setting up skip-worktree for local-modifiable files..."
    if [ -f ".vscode/settings.json" ]; then
        git update-index --skip-worktree .vscode/settings.json 2>/dev/null || true
        log "  skip-worktree: .vscode/settings.json"
    fi
}

# ──────────────────────────────────────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────────────────────────────────────
log "Starting container initialization (msprof-analyze)..."

configure_user_bin
configure_python3
install_build_deps
sync_git_identity
append_dev_hint_once
install_pre_commit_hook
ignore_local_changes

log "Container initialization complete!"
