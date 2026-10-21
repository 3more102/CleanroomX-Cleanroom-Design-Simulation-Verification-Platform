"""Real process-lifetime checks; these are not simulated OpenFOAM evidence."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from cleanroomx.cfd_process import CFDRunCancelled, run_native_cfd_process

pytestmark=pytest.mark.skipif(os.name!="posix",reason="Native CFD group management requires POSIX")


def _wait_until(predicate, seconds=4):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if predicate():
            return
        time.sleep(.01)
    pytest.fail("Process-lifetime condition did not become true before deadline")


def _stopped(pid):
    stat=Path(f"/proc/{pid}/stat")
    try:
        if stat.is_file() and stat.read_text().rsplit(")",1)[1].split()[0]=="Z":
            return True  # Exited orphan awaiting init reaping; no running solver.
        os.kill(pid,0)
        return False
    except (ProcessLookupError, FileNotFoundError):
        return True


def _tree_command(tmp_path):
    # Both parent and child ignore TERM, forcing the escalation path. The child
    # records readiness only after installing its handler.
    child="""import os,signal,sys,time
from pathlib import Path
signal.signal(signal.SIGTERM,signal.SIG_IGN)
Path(sys.argv[1]).write_text(str(os.getpid()))
time.sleep(60)
"""
    parent="""import os,signal,subprocess,sys,time,json
from pathlib import Path
signal.signal(signal.SIGTERM,signal.SIG_IGN)
child=subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2]])
while not Path(sys.argv[2]).exists(): time.sleep(.01)
marker=Path(sys.argv[3])
temporary=marker.with_suffix('.tmp')
temporary.write_text(json.dumps([os.getpid(),child.pid]))
temporary.rename(marker)
time.sleep(60)
"""
    return [sys.executable,"-c",parent,child,str(tmp_path/"child-ready"),str(tmp_path/"tree-ready")]


@pytest.mark.parametrize("stop",["cancel","timeout"])
def test_cancel_and_timeout_kill_actual_child_group_including_term_resistant_descendant(tmp_path,stop):
    cancel=threading.Event()
    with (tmp_path/"native.log").open("w") as output, ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(
            run_native_cfd_process,_tree_command(tmp_path),cwd=tmp_path,
            output=output,timeout_seconds=2 if stop=="timeout" else 10,cancel_event=cancel)
        try:
            _wait_until(lambda:(tmp_path/"tree-ready").exists())
            pids=json.loads((tmp_path/"tree-ready").read_text())
            assert all(not _stopped(pid) for pid in pids)
            if stop=="cancel":
                cancel.set()
            with pytest.raises(CFDRunCancelled if stop=="cancel" else subprocess.TimeoutExpired):
                future.result(timeout=5)
            _wait_until(lambda:all(_stopped(pid) for pid in pids))
        finally:
            cancel.set()


def test_precancelled_process_never_executes_command(tmp_path):
    cancel=threading.Event()
    cancel.set()
    with (tmp_path/"native.log").open("w") as output:
        with pytest.raises(CFDRunCancelled):
            run_native_cfd_process(
                [sys.executable,"-c","from pathlib import Path; Path('launched').touch()"],
                cwd=tmp_path,output=output,timeout_seconds=3,cancel_event=cancel)
    assert not (tmp_path/"launched").exists()


def test_normal_completion_retains_real_exit_and_literal_arguments(tmp_path):
    with (tmp_path/"native.log").open("w+") as output:
        result=run_native_cfd_process(
            [sys.executable,"-c","import sys; print(sys.argv[1]); sys.exit(23)","a b;$HOME"],
            cwd=tmp_path,output=output,timeout_seconds=3)
        output.seek(0)
        assert output.read().strip()=="a b;$HOME"
    assert result.returncode==23


@pytest.mark.parametrize("timeout",[0,-1,float("nan"),float("inf"),True])
def test_process_timeout_rejects_unbounded_or_invalid_values(tmp_path,timeout):
    with (tmp_path/"native.log").open("w") as output:
        with pytest.raises(ValueError,match="finite and positive"):
            run_native_cfd_process([sys.executable],cwd=tmp_path,output=output,timeout_seconds=timeout)
