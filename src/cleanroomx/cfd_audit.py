"""Conservative, user-thresholded OpenFOAM log residual screening.

A solver can satisfy linear residuals yet still be physically wrong; this
module never upgrades numerical screening to CFD/model validation.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import re

_NUMBER=r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_RESIDUAL=re.compile(
    rf"Solving for\s+([A-Za-z][A-Za-z0-9_]*)\s*,\s*"
    rf"Initial residual\s*=\s*({_NUMBER})\s*,\s*Final residual\s*=\s*({_NUMBER})",
    re.I,
)
_CONTINUITY=re.compile(
    rf"time step continuity errors\s*:\s*sum local\s*=\s*({_NUMBER})\s*,\s*global\s*=\s*({_NUMBER})",
    re.I,
)
_FATAL=re.compile(r"FOAM FATAL|floating point exception|segmentation fault|nan\b|inf(?:inity)?\b",re.I)
MAX_LOG_BYTES=32*1024*1024


def _threshold(value,name):
    if type(value) not in (int,float) or not math.isfinite(value) or value<=0:
        raise ValueError(name+" must be finite and strictly positive")
    return float(value)


def audit_openfoam_log(
    path, *, fields, max_initial_residual, max_final_residual,
    window=3, max_global_continuity=None
):
    """Fail closed for absent fields, incomplete logs, or out-of-bound samples.

    Numeric criteria are supplied by the project; they are NOT ISO thresholds.
    max_global_continuity checks reported absolute global step error when
    provided, but is not an independent mass-conservation calculation.
    """
    if type(fields) not in (tuple,list) or not fields or any(
        type(f) is not str or not re.fullmatch("[A-Za-z][A-Za-z0-9_]*",f) for f in fields
    ) or len(set(fields))!=len(fields):
        raise ValueError("fields must be a nonempty, unique sequence of solver field names")
    if type(window) is not int or not 1 <= window <= 100:
        raise ValueError("window must be integer 1..100")
    a=_threshold(max_initial_residual,"max_initial_residual")
    b=_threshold(max_final_residual,"max_final_residual")
    c=None if max_global_continuity is None else _threshold(max_global_continuity,"max_global_continuity")
    source=Path(path)
    if source.is_symlink() or not source.is_file():
        raise ValueError("Log must be a regular file, not a symlink")
    if source.stat().st_size>MAX_LOG_BYTES: raise ValueError("Log exceeds 32 MiB")
    data=source.read_bytes()
    if len(data)>MAX_LOG_BYTES: raise ValueError("Log exceeds 32 MiB")
    try:
        content=data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Log must be UTF-8") from exc
    after=source.stat()
    if after.st_size!=len(data): raise ValueError("Log changed during reading")
    fatal=bool(_FATAL.search(content))
    complete=bool(re.search(r"(?m)^\s*End\s*$",content))
    measurements={f:[] for f in fields}
    anomalies=[]
    for match in _RESIDUAL.finditer(content):
        name=match.group(1)
        if name not in measurements: continue
        initial=float(match.group(2));final=float(match.group(3))
        if not math.isfinite(initial) or not math.isfinite(final) or initial<0 or final<0:
            anomalies.append(f"{name}: nonfinite/negative residual")
        else: measurements[name].append((initial,final))
    summary={}
    for name,values in measurements.items():
        recent=values[-window:]
        if len(recent)<window:
            anomalies.append(f"{name}: required {window} residual samples, observed {len(recent)}")
        worst_initial=max((v[0] for v in recent),default=None)
        worst_final=max((v[1] for v in recent),default=None)
        if worst_initial is not None and worst_initial>a:
            anomalies.append(f"{name}: recent initial residual exceeds project threshold")
        if worst_final is not None and worst_final>b:
            anomalies.append(f"{name}: recent final residual exceeds project threshold")
        summary[name]={
            "sample_count":len(values),
            "recent_window_count":len(recent),
            "worst_recent_initial_residual":worst_initial,
            "worst_recent_final_residual":worst_final,
        }
    continuity=[]
    for m in _CONTINUITY.finditer(content):
        local=float(m.group(1));global_error=float(m.group(2))
        if not math.isfinite(local) or not math.isfinite(global_error):
            anomalies.append("nonfinite continuity value")
        else: continuity.append({"local":local,"global":global_error})
    if c is not None:
        if len(continuity)<window:
            anomalies.append("missing requested global-continuity evidence")
        elif any(abs(entry["global"])>c for entry in continuity[-window:]):
            anomalies.append("reported global continuity exceeds project threshold")
    if not complete: anomalies.append("solver log has no terminal End marker")
    if fatal: anomalies.append("fatal/nonfinite marker in solver output")
    if not any(measurements.values()):
        anomalies.append("no recognized field-residual evidence")
    return {
        "status":"numerically_screened" if not anomalies else "incomplete_or_failed",
        "completed_log_marker":complete,
        "fatal_or_nonfinite_marker":fatal,
        "criteria":{
            "fields":list(fields),
            "max_initial_residual":a,"max_final_residual":b,
            "window":window,"max_global_continuity":c,
        },
        "fields":summary,
        "continuity_samples":len(continuity),
        "recent_max_abs_global_continuity":max((abs(e["global"]) for e in continuity[-window:]),default=None),
        "violations":anomalies,
        "log_sha256":hashlib.sha256(data).hexdigest(),
        "boundary":"Numerical log screening only; not mass-balance integration, mesh convergence, cleanroom validation or certification",
    }
