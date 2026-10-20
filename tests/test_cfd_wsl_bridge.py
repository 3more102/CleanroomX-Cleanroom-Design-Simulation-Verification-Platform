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
