"""Require complete desktop coverage, retrying only native Tcl startup skips."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET


TCL_STARTUP = re.compile(
    r'^Tk display unavailable: (?:Can\'t find a usable (?:init|tk)\.tcl|'
    r'invalid command name "tcl_findLibrary")'
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junitxml", type=Path, required=True)
    parser.add_argument("--retry-tk-startup", action="store_true")
    parser.add_argument("tests", nargs="+")
    args = parser.parse_args()
    args.junitxml.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-m", "pytest", "-q", "-rs"]
    initial = subprocess.run(command + args.tests + [f"--junitxml={args.junitxml}"])
    if initial.returncode:
        return initial.returncode
    cases = list(ET.parse(args.junitxml).getroot().iter("testcase"))
    if not cases:
        print("Desktop coverage report contains no test cases.", file=sys.stderr)
        return 1
    skipped = [case for case in cases if case.find("skipped") is not None]
    modules = {Path(path).with_suffix("").as_posix().replace("/", "."): path
               for path in args.tests}
    retries = []
    for index, case in enumerate(skipped, 1):
        reason = case.find("skipped").get("message", "")
        if not args.retry_tk_startup or not TCL_STARTUP.match(reason):
            print(f"Required desktop case skipped: {case.get('name')}: {reason}", file=sys.stderr)
            return 1
        classname = case.get("classname", "")
        module = next((name for name in modules
                       if classname == name or classname.startswith(name + ".")), None)
        if module is None:
            print(f"Cannot resolve skipped desktop case: {classname}", file=sys.stderr)
            return 1
        classes = classname[len(module):].strip(".").replace(".", "::")
        node = "::".join(part for part in (modules[module], classes, case.get("name")) if part)
        report = args.junitxml.with_name(f"{args.junitxml.stem}.retry-{index}.xml")
        print(f"Retrying Tcl startup in a fresh process: {node}", flush=True)
        result = subprocess.run(
            command + [node, f"--junitxml={report}"],
            env={**os.environ, "CLEANROOMX_GUI_STARTUP_RETRY": "1"},
        )
        retried = list(ET.parse(report).getroot().iter("testcase")) if report.is_file() else []
        if (result.returncode or len(retried) != 1
                or any(retried[0].find(tag) is not None for tag in ("skipped", "failure", "error"))):
            print(f"Desktop case did not pass its isolated retry: {node}", file=sys.stderr)
            return 1
        retries.append({"nodeid": node, "initial_skip": reason, "report": report.name})
    receipt = {
        "git_commit": os.environ.get("GITHUB_SHA"),
        "tests": len(cases),
        "initial_passed": len(cases) - len(skipped),
        "initial_skipped": len(skipped),
        "tcl_startup_retries": retries,
        "passed": len(cases),
        "skipped": 0,
        "failed": 0,
    }
    args.junitxml.with_suffix(".coverage.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"Complete desktop coverage: {len(cases)} passed, 0 skipped; {len(retries)} Tcl startup retries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
