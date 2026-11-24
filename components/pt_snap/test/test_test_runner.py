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

"""Exercise the real Bash entry point without starting a nested test suite."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _bash() -> str:
    if os.name == "nt":
        # Prefer Git Bash to Windows' WSL launcher. Git-for-Windows supplies the
        # POSIX tools used by the entry point on the Windows compatibility jobs.
        git = shutil.which("git")
        assert git is not None, "Git for Windows is required to test the Bash entry point"
        bash = Path(git).resolve().parents[1] / "bin" / "bash.exe"
        assert bash.is_file(), f"Git Bash not found at {bash}"
        return str(bash)
    bash = shutil.which("bash")
    assert bash is not None, "Bash is required to test the Bash entry point"
    return bash


@pytest.fixture
def shell_runner(tmp_path):
    root = tmp_path / "repository with spaces"
    (root / "test").mkdir(parents=True)
    script = root / "test" / "run_tests.sh"
    shutil.copyfile(ROOT / "test" / "run_tests.sh", script)
    outside = tmp_path / "outside repository"
    outside.mkdir()
    recorder = tmp_path / "isolated modules"
    recorder.mkdir()
    log = tmp_path / "invocation.json"
    # Python really dispatches `-m pytest`, but this isolated module records the
    # call instead of loading pytest/plugins, collecting tests or generating data.
    (recorder / "pytest.py").write_text(
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "Path(os.environ['RUNNER_TEST_LOG']).write_text(json.dumps({\n"
        "    'argv': sys.argv[1:], 'cwd': os.getcwd(), 'executable': sys.executable,\n"
        "}), encoding='utf-8')\n"
        "raise SystemExit(int(os.environ['RUNNER_TEST_EXIT']))\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(
        PYTHONPATH=str(recorder),
        PYTHONUTF8="1",
        PATH=str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", ""),
        RUNNER_TEST_LOG=str(log),
    )

    current_python = Path(sys.executable).as_posix()

    def run(*args, exit_code=0, python=current_python):
        selected_env = dict(env, RUNNER_TEST_EXIT=str(exit_code))
        if python is None:
            selected_env.pop("PYTHON", None)
        else:
            selected_env["PYTHON"] = python
        return subprocess.run(
            [_bash(), "--noprofile", "--norc", script.as_posix(), *args],
            cwd=outside,
            env=selected_env,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )

    def invocation():
        return json.loads(log.read_text(encoding="utf-8"))

    return SimpleNamespace(root=root, log=log, run=run, invocation=invocation)


def test_default_runner_uses_active_python_and_keeps_coverage(shell_runner):
    result = shell_runner.run(python=None)
    assert result.returncode == 0, result.stdout + result.stderr
    call = shell_runner.invocation()
    assert Path(call["cwd"]) == shell_runner.root
    assert Path(call["executable"]).resolve() == Path(sys.executable).resolve()
    assert call["argv"] == [
        "test/",
        "--cov=pt_snap_cli",
        "--cov-report=html:test_reports/htmlcov",
        "--cov-report=xml:test_reports/xml/coverage.xml",
        "--cov-report=term-missing",
        "-v",
        "--tb=short",
    ]
    assert (shell_runner.root / "test_reports" / "htmlcov").is_dir()
    assert (shell_runner.root / "test_reports" / "xml").is_dir()


def test_quick_mode_forwards_selection_and_pytest_arguments_without_reports(shell_runner):
    result = shell_runner.run(
        "--quick",
        "-f",
        "test_package.py::TestPackage::test_version",
        "--file",
        "test/query/test_builder.py",
        "--keyword",
        "version or builder",
        "-m",
        "not slow and not nightly",
        "--stop",
        "--",
        "-q",
        "--maxfail=2",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert shell_runner.invocation()["argv"] == [
        "test/test_package.py::TestPackage::test_version",
        "test/query/test_builder.py",
        "-v",
        "--tb=short",
        "-k",
        "version or builder",
        "-m",
        "not slow and not nightly",
        "-x",
        "-q",
        "--maxfail=2",
    ]
    assert not (shell_runner.root / "test_reports").exists()


def test_short_aliases_and_all_mode_preserve_option_only_invocations(shell_runner):
    result = shell_runner.run("-q", "all", "-k", "test_version", "--mark", "not slow", "-x")
    assert result.returncode == 0, result.stdout + result.stderr
    assert shell_runner.invocation()["argv"] == [
        "test/",
        "-v",
        "--tb=short",
        "-k",
        "test_version",
        "-m",
        "not slow",
        "-x",
    ]
    assert not (shell_runner.root / "test_reports").exists()


def test_explicit_interpreter_and_absolute_test_path_are_respected(shell_runner):
    target = shell_runner.root / "test" / "test with spaces.py"
    result = shell_runner.run("--quick", "--file", target.as_posix())
    assert result.returncode == 0, result.stdout + result.stderr
    call = shell_runner.invocation()
    assert Path(call["executable"]).resolve() == Path(sys.executable).resolve()
    assert Path(call["argv"][0]) == target
    assert call["argv"][1:] == ["-v", "--tb=short"]


def test_custom_report_directory_preserves_spaces_and_repo_relative_paths(shell_runner):
    result = shell_runner.run("--reports-dir", ".tmp/reports with spaces")
    assert result.returncode == 0, result.stdout + result.stderr
    args = shell_runner.invocation()["argv"]
    assert "--cov-report=html:.tmp/reports with spaces/htmlcov" in args
    assert "--cov-report=xml:.tmp/reports with spaces/xml/coverage.xml" in args
    assert (shell_runner.root / ".tmp/reports with spaces/htmlcov").is_dir()
    assert (shell_runner.root / ".tmp/reports with spaces/xml").is_dir()
    assert not (shell_runner.root / "test_reports").exists()


@pytest.mark.parametrize(
    ("supplied", "expected"),
    [
        (r"C:\example tests\test_case.py", "C:/example tests/test_case.py"),
        ("C:/example tests/test_case.py", "C:/example tests/test_case.py"),
        (r"\\server\share\test_case.py", "//server/share/test_case.py"),
        ("//server/share/test_case.py", "//server/share/test_case.py"),
        ("./test/test_package.py", "./test/test_package.py"),
    ],
)
def test_file_selection_accepts_native_drive_and_unc_path_syntax(shell_runner, supplied, expected):
    # These selectors are recorded only; no network share or external file is
    # accessed. Windows Bash may translate forward slashes back to native ones.
    result = shell_runner.run("--quick", "--file", supplied)
    assert result.returncode == 0, result.stdout + result.stderr
    assert shell_runner.invocation()["argv"][0].replace("\\", "/") == expected


@pytest.mark.parametrize("native_separators", [False, True])
def test_report_directory_accepts_absolute_temp_paths(shell_runner, tmp_path, native_separators):
    report = tmp_path / "absolute reports"
    supplied = str(report) if native_separators else report.as_posix()
    result = shell_runner.run("--reports-dir", supplied)
    assert result.returncode == 0, result.stdout + result.stderr
    args = [arg.replace("\\", "/") for arg in shell_runner.invocation()["argv"]]
    assert f"--cov-report=html:{report.as_posix()}/htmlcov" in args
    assert f"--cov-report=xml:{report.as_posix()}/xml/coverage.xml" in args
    assert (report / "htmlcov").is_dir()
    assert (report / "xml").is_dir()
    assert not (shell_runner.root / "test_reports").exists()


def test_quick_mode_does_not_create_custom_reports(shell_runner):
    result = shell_runner.run("--quick", "--reports-dir", "custom reports")
    assert result.returncode == 0, result.stdout + result.stderr
    assert not any(arg.startswith("--cov") for arg in shell_runner.invocation()["argv"])
    assert not (shell_runner.root / "custom reports").exists()
    assert not (shell_runner.root / "test_reports").exists()


@pytest.mark.parametrize("exit_code", [0, 1, 2, 3, 4, 5])
@pytest.mark.parametrize("options", [(), ("--quick",)])
def test_runner_preserves_pytest_exit_codes(shell_runner, exit_code, options):
    result = shell_runner.run(*options, exit_code=exit_code)
    assert result.returncode == exit_code, result.stdout + result.stderr
    assert shell_runner.log.is_file()


@pytest.mark.parametrize("option", ["-h", "--help"])
def test_help_needs_no_python_and_creates_no_reports(shell_runner, option):
    result = shell_runner.run(option, python="missing-python-for-runner-test")
    assert result.returncode == 0
    assert "PYTHON" in result.stdout and "--quick" in result.stdout
    assert "not a CI gate" in result.stdout
    assert not shell_runner.log.exists()
    assert not (shell_runner.root / "test_reports").exists()


@pytest.mark.parametrize(
    "args",
    [
        ("-f",),
        ("--file", ""),
        ("-k",),
        ("--keyword", "--quick"),
        ("-m",),
        ("--mark", ""),
        ("--reports-dir",),
        ("--reports-dir", "--quick"),
        ("--unknown",),
        ("unit",),
        ("integration",),
    ],
)
def test_invalid_options_fail_before_invoking_python(shell_runner, args):
    result = shell_runner.run(*args)
    assert result.returncode == 2
    assert "Error:" in result.stderr
    assert not shell_runner.log.exists()
    assert not (shell_runner.root / "test_reports").exists()


def test_missing_interpreter_is_an_actionable_failure(shell_runner):
    result = shell_runner.run(python="missing-python-for-runner-test")
    assert result.returncode == 127
    assert "Python executable not found: missing-python-for-runner-test" in result.stderr
    assert not shell_runner.log.exists()
    assert not (shell_runner.root / "test_reports").exists()
