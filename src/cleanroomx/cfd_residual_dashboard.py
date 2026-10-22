"""Interactive, provenance-linked numerical residual plot from actual log samples.

No fake solver data, physical time inference, or compliance claims.
"""
from __future__ import annotations

from html import escape
import json
import math
import re

_AXIS = "linear_solver_log_order_not_simple_iterations"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def render_residual_dashboard(report: dict) -> str:
    """Build one self-contained browser dashboard; never reread the source log."""
    if not isinstance(report, dict) or report.get("completed_log_marker") is not True:
        raise ValueError("A terminal, recorded solver log is required")
    if report.get("fatal_or_nonfinite_marker") is not False:
        raise ValueError("Fatal/nonfinite solver logs cannot create a dashboard")
    if (report.get("residual_sample_axis") != _AXIS or
        report.get("plot_series_max_samples") != 1000):
        raise ValueError("A bounded recorded residual series is required")
    digest = report.get("log_sha256")
    if type(digest) is not str or _SHA256.fullmatch(digest) is None:
        raise ValueError("The original solver-log SHA-256 is required")
    if report.get("status") not in ("numerically_screened", "incomplete_or_failed"):
        raise ValueError("Invalid numeric audit classification")
    fields = report.get("fields")
    criteria = report.get("criteria")
    if (type(fields) is not dict or not 1 <= len(fields) <= 20 or
        type(criteria) is not dict or type(criteria.get("fields")) is not list or
        set(fields) != set(criteria["fields"])):
        raise ValueError("Plot fields do not match numerical audit criteria")
    displayed = {}
    for name, row in sorted(fields.items()):
        if (type(name) is not str or re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name) is None
            or type(row) is not dict):
            raise ValueError("Invalid field identity or residual data")
        count = row.get("sample_count")
        start = row.get("plot_first_sample_index")
        a = row.get("plot_initial_residual_samples")
        b = row.get("plot_final_residual_samples")
        recent_a = row.get("recent_initial_residual_samples")
        recent_b = row.get("recent_final_residual_samples")
        if (type(count) is not int or count < 1 or type(start) is not int or
            type(a) is not list or type(b) is not list or
            not 1 <= len(a) <= 1000 or len(a) != len(b) or
            start != count - len(a) + 1 or
            type(recent_a) is not list or not recent_a or
            type(recent_b) is not list or not recent_b or
            a[-len(recent_a):] != recent_a or b[-len(recent_b):] != recent_b or
            row.get("worst_recent_initial_residual") != max(recent_a) or
            row.get("worst_recent_final_residual") != max(recent_b)):
            raise ValueError("Plot series disagrees with audited tail residuals")
        for value in a + b:
            if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
                raise ValueError("Nonfinite or negative residual plot data")
        displayed[name] = {"total": count, "start": start,
                           "initial": a, "final": b}
    packed = {"fields": displayed, "status": report["status"]}
    data = (json.dumps(packed, allow_nan=False, ensure_ascii=True)
            .replace("<", "\\u003c").replace(">", "\\u003e")
            .replace("&", "\\u0026"))
    return (_HTML.replace("__DATA__", data)
            .replace("__HASH__", escape(digest))
            .replace("__STATUS__", escape(report["status"])))


_HTML = r"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CleanroomX — Recorded solver residuals</title>
<style>
:root{font:15px system-ui,sans-serif;color-scheme:dark;color:#eaf0f8;background:#101b2b}
body{margin:auto;max-width:1100px;padding:24px;line-height:1.5}
h1{font-size:1.6rem}small{color:#bdcce0}
.controls{display:flex;gap:12px;flex-wrap:wrap;margin:22px 0}
label{display:grid;gap:5px}select{padding:9px;border:1px solid #8295ac;border-radius:6px;background:#21364f;color:#fff}
svg{width:100%;height:auto;border-radius:8px;border:1px solid #60748e;background:#142237}
.axis{stroke:#8497aa;stroke-width:1}.tick{fill:#cbd8e9;font:13px system-ui}
.line{fill:none;stroke:#48d6bb;stroke-width:2;stroke-linejoin:round}
#detail{border:1px solid #536a82;border-radius:8px;padding:12px;margin:12px 0;min-height:28px}
code{overflow-wrap:anywhere}
</style></head><body>
<h1>CleanroomX · Recorded solver residuals</h1>
<p><strong>Numerical status: __STATUS__.</strong> This interactive view plots actual
parsed linear-solver residual entries, not saved SIMPLE iterations or physical time.
It does not establish OpenFOAM convergence, cleanroom performance or certification.</p>
<div class="controls">
<label>Field<select id="field"></select></label>
<label>Residual<select id="kind"><option value="initial">Initial</option>
<option value="final">Final</option></select></label>
<label>Y scale<select id="scale"><option value="log">log10</option>
<option value="linear">linear</option></select></label>
<label>Samples<select id="last"><option value="1000">Last 1000 available</option>
<option value="100">Last 100</option><option value="250">Last 250</option>
<option value="500">Last 500</option></select></label>
</div>
<svg id="chart" role="img" aria-label="Numerical residual by per-field log sample index"
viewBox="0 0 1000 485"><g id="axes"></g>
<polyline id="trace" class="line"></polyline>
<circle id="cursor" r="5" fill="#ffd77b" visibility="hidden"></circle></svg>
<div id="detail" aria-live="polite">Select a field and hover over the chart.</div>
<p><small>Only the most recent 1000 recorded samples per field are retained.
Indexing is 1-based within each field's linear-solver log records.
log10 displays exact zero at a visual floor of 1e-30; hover retains the true value.
Lines join recorded samples for viewing and do not reconstruct intermediate solver states.</small></p>
<p><small>Solver log SHA-256: <code>__HASH__</code>. This is a change-detection
fingerprint, not a signed third-party attestation.</small></p>
<script id="audit-json" type="application/json">__DATA__</script>
<script>
"use strict";
const data=JSON.parse(document.getElementById("audit-json").textContent);
const names=Object.keys(data.fields);
const field=document.getElementById("field");
const kind=document.getElementById("kind");
const scale=document.getElementById("scale");
const last=document.getElementById("last");
const svg=document.getElementById("chart");
const axes=document.getElementById("axes");
const trace=document.getElementById("trace");
const cursor=document.getElementById("cursor");
const detail=document.getElementById("detail");
const NS="http://www.w3.org/2000/svg";
const L=75,R=973,T=28,B=410;
let points=[],ids=[],yTransform,minimum,maximum;
names.forEach(name=>{
  const option=document.createElement("option");
  option.value=name;option.textContent=name;field.appendChild(option);
});
function el(tag,attributes,label){
  const n=document.createElementNS(NS,tag);
  for(const key in attributes)n.setAttribute(key,String(attributes[key]));
  if(label!==undefined)n.textContent=label;
  axes.appendChild(n);
}
function render(){
  const f=data.fields[field.value];
  const series=f[kind.value];
  const count=Math.min(series.length,Number(last.value));
  points=series.slice(-count);
  ids=points.map((_,i)=>f.total-count+i+1);
  const isLog=scale.value==="log";
  yTransform=v=>isLog?Math.log10(Math.max(v,1e-30)):v;
  const ys=points.map(yTransform);
  minimum=Math.min(...ys);maximum=Math.max(...ys);
  if(maximum===minimum){maximum+=1;minimum-=1}
  else{const pad=(maximum-minimum)*0.06;maximum+=pad;minimum-=pad}
  const xx=i=>L+(R-L)*(count===1?0.5:i/(count-1));
  const yy=v=>B-(yTransform(v)-minimum)/(maximum-minimum)*(B-T);
  while(axes.firstChild)axes.removeChild(axes.firstChild);
  el("line",{x1:L,y1:B,x2:R,y2:B,class:"axis"});
  el("line",{x1:L,y1:T,x2:L,y2:B,class:"axis"});
  for(let n=0;n<=4;n++){
    const ypos=T+(B-T)*n/4;
    const value=maximum-(maximum-minimum)*n/4;
    el("text",{x:L-8,y:ypos+4,"text-anchor":"end",class:"tick"},
       isLog?"10^"+value.toFixed(1):Number(value.toPrecision(3)).toString());
    const idx=Math.min(count-1,Math.round((count-1)*n/4));
    el("text",{x:xx(idx),y:B+22,"text-anchor":"middle",class:"tick"},String(ids[idx]));
  }
  el("text",{x:(L+R)/2,y:B+54,"text-anchor":"middle",class:"tick"},
     "Linear-solver per-field log index (not SIMPLE time)");
  el("text",{x:(L+R)/2,y:16,"text-anchor":"middle",class:"tick"},
     field.value+" · "+kind.value+" residual");
  trace.setAttribute("points",points.map((v,i)=>xx(i).toFixed(2)+","+yy(v).toFixed(2)).join(" "));
  cursor.setAttribute("visibility","hidden");
  detail.textContent="Showing "+count+" recorded samples out of "+f.total+" for "+field.value+
    ". Status: "+data.status+".";
}
svg.addEventListener("mousemove",event=>{
  if(!points.length)return;
  const p=svg.createSVGPoint();p.x=event.clientX;p.y=event.clientY;
  const matrix=svg.getScreenCTM();if(!matrix)return;
  const pos=p.matrixTransform(matrix.inverse());
  const index=Math.max(0,Math.min(points.length-1,
    Math.round((pos.x-L)/(R-L)*(points.length-1))));
  const x=L+(R-L)*(points.length===1?0.5:index/(points.length-1));
  const y=B-(yTransform(points[index])-minimum)/(maximum-minimum)*(B-T);
  cursor.setAttribute("cx",x);cursor.setAttribute("cy",y);
  cursor.setAttribute("visibility","visible");
  detail.textContent=field.value+" / log sample "+ids[index]+" / "+kind.value+
    " residual = "+points[index]+". This is not a physical time sample.";
});
svg.addEventListener("mouseleave",()=>cursor.setAttribute("visibility","hidden"));
[field,kind,scale,last].forEach(control=>control.addEventListener("change",render));
render();
</script>
</body></html>
"""