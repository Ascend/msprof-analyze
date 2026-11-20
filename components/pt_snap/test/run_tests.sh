#!/usr/bin/env bash
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


# Use the caller's Python environment; never activate or install an environment.
set -eo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python}"
REPORTS_DIR="test_reports"

show_help() {
    cat <<HELP
Usage: bash test/run_tests.sh [OPTIONS] [all] [-- PYTEST_ARGS...]

Run pytest with the active Python from PATH, or the executable set in PYTHON.
Requires Bash and dependencies already installed in that Python environment.
Paths are resolved from the repository root, regardless of the caller's CWD.

Options:
  -h, --help               Show this help without running Python
  -q, --quick              Omit coverage and report generation (not a CI gate)
  -f, --file FILE          Select a test file/node (repeatable); bare names use test/
  -k, --keyword EXPR       Select tests by pytest keyword expression
  -m, --mark EXPR          Select tests by pytest marker expression
  -x, --stop               Stop after the first failure
      --reports-dir DIR   Coverage output directory (default: test_reports/)
      --                  Forward remaining arguments unchanged to pytest

With no --file selection, run test/. Full mode retains the configured coverage
floor and writes HTML/XML reports under the ignored test_reports/ directory.
Quick mode adds no coverage options and creates no report directory. Arbitrary
pytest options belong after --. Select files/nodes with -f: positional selectors
passed after -- are additive to the default test/ selection. The pytest exit
code is returned unchanged.

Examples:
  bash test/run_tests.sh
  bash test/run_tests.sh --quick -f test_package.py
  bash test/run_tests.sh -m 'not slow and not nightly' -- -q
  PYTHON=/path/to/venv/bin/python bash test/run_tests.sh --quick -- --collect-only
HELP
}

usage_error() {
    printf 'Error: %s\nUse --help for usage.\n' "$1" >&2
    exit 2
}

require_value() {
    if [[ $# -lt 2 || -z "$2" || "$2" == -* ]]; then
        usage_error "$1 requires a value"
    fi
}

normalize_path() {
    # Git Bash accepts native drive/UNC paths when their separators are forward
    # slashes. Leave POSIX filenames (which can contain backslashes) unchanged.
    case "$1" in
        [A-Za-z]:\\*|\\\\*) printf '%s\n' "${1//\\//}" ;;
        *) printf '%s\n' "$1" ;;
    esac
}

quick_mode=false
test_paths=()
pytest_args=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            show_help
            exit 0
            ;;
        -q|--quick)
            quick_mode=true
            shift
            ;;
        -f|--file)
            require_value "$@"
            file_path="$(normalize_path "$2")"
            case "$file_path" in
                /*|[A-Za-z]:/*|test/*|./test/*) test_paths+=("$file_path") ;;
                *) test_paths+=("test/$file_path") ;;
            esac
            shift 2
            ;;
        -k|--keyword)
            require_value "$@"
            pytest_args+=("-k" "$2")
            shift 2
            ;;
        -m|--mark)
            require_value "$@"
            pytest_args+=("-m" "$2")
            shift 2
            ;;
        -x|--stop)
            pytest_args+=("-x")
            shift
            ;;
        --reports-dir)
            require_value "$@"
            REPORTS_DIR="$(normalize_path "$2")"
            shift 2
            ;;
        all)
            shift
            ;;
        --)
            shift
            pytest_args+=("$@")
            break
            ;;
        *)
            usage_error "unknown option or mode: $1"
            ;;
    esac
done

cd "$PROJECT_ROOT"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    printf 'Error: Python executable not found: %s\n' "$PYTHON" >&2
    exit 127
fi

if [[ ${#test_paths[@]} -eq 0 ]]; then
    test_paths=("test/")
fi

coverage_args=()
if [[ "$quick_mode" == false ]]; then
    mkdir -p "$REPORTS_DIR/htmlcov" "$REPORTS_DIR/xml"
    coverage_args=(
        --cov=pt_snap_cli
        "--cov-report=html:$REPORTS_DIR/htmlcov"
        "--cov-report=xml:$REPORTS_DIR/xml/coverage.xml"
        --cov-report=term-missing
    )
    printf 'Coverage reports: %s\n' "$REPORTS_DIR"
fi

# exec preserves pytest's success, failure, interruption and collection exit codes.
exec "$PYTHON" -m pytest "${test_paths[@]}" "${coverage_args[@]}" \
    -v --tb=short "${pytest_args[@]}"
