"""Contract tests for the opt-in Windows/WSL connected OpenFOAM bridge.

The mocked WSL process tests argument isolation, failures and exit codes;
it does not pretend that OpenFOAM executed in WSL.
"""
from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from cleanroomx import cfd_wsl_bridge as bridge


@pytest.fixture
def repository(tmp_path):
    root=tmp_path/"Repo with spaces"
    (root/"scripts").mkdir(parents=True)
    (root/"src"/"cleanroomx").mkdir(parents=True)
    (root/"scripts"/"with_openfoam10.sh").write_text("#!/bin/bash\n")
    case=tmp_path/"case with $(untrusted text)"
    case.mkdir()
    (case/"manifest.json").write_text('{"schema":"test fixture"}')
    return root,case


@pytest.fixture
def fake_windows(monkeypatch):
    # Patch the module's OS reference, not process-wide os.name; pathlib and
    # pytest must retain their own real platform semantics on Linux CI.
    monkeypatch.setattr(bridge,"os",SimpleNamespace(name="nt"))


def test_probe_uses_fixed_script_and_positional_paths(repository,fake_windows,monkeypatch):
    root,case=repository
    commands=[]
    def mocked_run(args,**kwargs):
        commands.append((args,kwargs))
        if "wslpath" in args:
            assert kwargs["capture_output"] and kwargs["timeout"]==30
            return subprocess.CompletedProcess(args,0,"/mnt/c/repo with spaces\n","")
        return subprocess.CompletedProcess(args,0)
    monkeypatch.setattr(bridge.subprocess,"run",mocked_run)
    assert bridge.run_wsl_bridge(repository=root,mode="probe")==0
    assert len(commands)==2
    assert commands[0][0][:5]==[
        "wsl.exe","--distribution","Ubuntu","--exec","wslpath"]
    command=commands[1][0]
    assert command[:6]==["wsl.exe","--distribution","Ubuntu","--exec","bash","-c"]
    assert command[7:]==[
        "cleanroomx-wsl-bridge","/mnt/c/repo with spaces",
        "/mnt/c/repo with spaces","probe","3600"]
    assert '"$repo/scripts/with_openfoam10.sh"' in command[6]
    assert "python3 -c" in command[6]
    assert '"$case_dir"' in command[6]
    assert str(root) not in command[6]


def test_run_case_path_remains_separate_argument_and_preserves_exit_code(
    repository,fake_windows,monkeypatch,
):
    root,case=repository
    calls=[]
    def mocked_run(args,**kwargs):
        calls.append(args)
        if "wslpath" in args:
            val="/mnt/c/Repo with spaces" if len(calls)==1 else "/mnt/c/case with $(untrusted text)"
            return subprocess.CompletedProcess(args,0,val+"\n","")
        return subprocess.CompletedProcess(args,17)
    monkeypatch.setattr(bridge.subprocess,"run",mocked_run)
    assert bridge.run_wsl_bridge(
        repository=root,mode="run",case_directory=case,timeout_seconds=120
    )==17
    assert len(calls)==3
    code=calls[2][6]
    assert "untrusted text" not in code
    assert calls[2][-4:]==[
        "/mnt/c/Repo with spaces", "/mnt/c/case with $(untrusted text)",
        "run","120"]
    assert 'multizone-run "$case_dir"' in code
    assert '"$timeout"' in code


@pytest.mark.parametrize("bad",["Ubuntu;id","../Ubuntu","Ubuntu\nx","", "a"*65])
def test_distribution_validation_rejects_injection(
    repository,fake_windows,monkeypatch,bad,
):
    monkeypatch.setattr(bridge.subprocess,"run",lambda *a,**k:pytest.fail("WSL was invoked"))
    with pytest.raises(ValueError,match="distribution"):
        bridge.run_wsl_bridge(repository=repository[0],distribution=bad)


def test_missing_case_manifest_and_unsupported_modes_fail_before_wsl(
    repository,fake_windows,monkeypatch,
):
    root,case=repository
    monkeypatch.setattr(bridge.subprocess,"run",lambda *a,**k:pytest.fail("WSL was invoked"))
    (case/"manifest.json").unlink()
    with pytest.raises(ValueError,match="manifest"):
        bridge.run_wsl_bridge(repository=root,case_directory=case,mode="run")
    with pytest.raises(ValueError,match="requires"):
        bridge.run_wsl_bridge(repository=root,mode="run")
    with pytest.raises(ValueError,match="must not"):
        bridge.run_wsl_bridge(repository=root,mode="probe",case_directory=case)
    with pytest.raises(ValueError,match="Mode"):
        bridge.run_wsl_bridge(repository=root,mode="generate")
    with pytest.raises(ValueError,match="timeout"):
        bridge.run_wsl_bridge(repository=root,timeout_seconds=0)


def test_wsl_translation_failure_is_not_interpreted_as_solver_success(
    repository,fake_windows,monkeypatch,
):
    def fail(args,**kwargs):
        return subprocess.CompletedProcess(args,1,"","WSL distro not installed")
    monkeypatch.setattr(bridge.subprocess,"run",fail)
    with pytest.raises(RuntimeError,match="not installed"):
        bridge.run_wsl_bridge(repository=repository[0])


@pytest.mark.parametrize("invalid",[
    "", "relative/path\n", "/valid\n/injected\n", "/mnt/c/has\x00null\n",
])
def test_malformed_wsl_path_rejected(repository,fake_windows,monkeypatch,invalid):
    monkeypatch.setattr(
        bridge.subprocess,"run",
        lambda args,**k:subprocess.CompletedProcess(args,0,invalid,""),
    )
    with pytest.raises(RuntimeError,match="invalid Unix path"):
        bridge.run_wsl_bridge(repository=repository[0])


def test_rejects_nonwindows(repository):
    if bridge.os.name=="nt":
        pytest.skip("Native Windows host")
    with pytest.raises(RuntimeError,match="on Windows"):
        bridge.run_wsl_bridge(repository=repository[0])


def test_custom_mounted_drive_runtime_is_an_isolated_argument(repository, fake_windows, monkeypatch):
    calls = []
    bashrc = "/mnt/d/CFD with $(literal text)/OpenFOAM-10/etc/bashrc"
    def run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "/mnt/c/repo\n" if "wslpath" in args else "", "")
    monkeypatch.setattr(bridge.subprocess, "run", run)
    assert bridge.run_wsl_bridge(repository=repository[0], openfoam_bashrc=bashrc) == 0
    assert calls[-1][-1] == bashrc
    assert bashrc not in calls[-1][6]
    assert 'export CLEANROOMX_OPENFOAM_BASHRC="$foam_bashrc"' in calls[-1][6]


@pytest.mark.parametrize("path", ["D:\\OpenFOAM\\etc\\bashrc", "../etc/bashrc", "/etc/bashrc\n", ""])
def test_custom_runtime_requires_an_absolute_linux_path(repository, fake_windows, monkeypatch, path):
    monkeypatch.setattr(bridge.subprocess, "run", lambda *a, **k: pytest.fail("WSL invoked"))
    with pytest.raises(ValueError, match="absolute Linux path"):
        bridge.run_wsl_bridge(repository=repository[0], openfoam_bashrc=path)


@pytest.mark.parametrize("timed_out", [False, True])
def test_real_process_diagnostics_are_bounded_and_retained_on_failure(repository, fake_windows, monkeypatch, timed_out):
    messages = []
    def run(args, **kwargs):
        if "wslpath" in args:
            return subprocess.CompletedProcess(args, 0, "/mnt/c/repo\n", "")
        kwargs["stdout"].write(b"x" * 70000 + b"\nActual runtime missing: fixture diagnostic\n")
        if timed_out:
            raise subprocess.TimeoutExpired(args, 180)
        return subprocess.CompletedProcess(args, 2)
    monkeypatch.setattr(bridge.subprocess, "run", run)
    if timed_out:
        with pytest.raises(subprocess.TimeoutExpired):
            bridge.run_wsl_bridge(repository=repository[0], diagnostic_callback=messages.append)
    else:
        assert bridge.run_wsl_bridge(repository=repository[0], diagnostic_callback=messages.append) == 2
    assert len(messages) == 1 and len(messages[0]) < 66000
    assert messages[0].startswith("[Earlier diagnostics truncated]")
    assert "Actual runtime missing" in messages[0]


def test_bash_entrypoint_syntax_when_bash_is_installed():
    if os.name=="nt":
        pytest.skip("Windows bash.exe can be an unconfigured WSL stub; Bash syntax is tested on Linux CI")
    if not shutil.which("bash"):
        pytest.skip("Bash not installed")
    result=subprocess.run(
        ["bash","-n","-c",bridge._WSL_ENTRYPOINT],
        capture_output=True,text=True,check=False,
    )
    assert result.returncode==0,result.stderr
