"""Export the *visible* Tk 3D CAD viewport as a standalone vector SVG.

This is a presentation export of the existing 3D canvas, not a CFD render,
mesh, measured pressure distribution, or independent engineering evidence.
No additional runtime dependencies are required.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import re
import tempfile
import xml.etree.ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)
MAX_CANVAS_ITEMS = 25000
SUPPORTED_ITEMS = frozenset(("line", "polygon", "rectangle", "oval", "text"))
NUMBER_DASH = re.compile(r"^\s*\d+(?:\.\d+)?(?:\s+\d+(?:\.\d+)?)*\s*$")


def _tag(name: str) -> str:
    return "{" + SVG_NS + "}" + name


def _option(canvas: object, item_id: int, key: str, default: str = "") -> str:
    try:
        return str(canvas.itemcget(item_id, key))
    except (ValueError, KeyError, AttributeError):
        return default


def _coord(value: float) -> str:
    number = float(value)
    if not math.isfinite(number) or abs(number) > 100000000:
        raise ValueError("3D canvas has non-finite or implausible coordinates")
    return f"{number:.3f}".rstrip("0").rstrip(".") or "0"


def _color(canvas: object, raw: str, *, default: str = "none") -> str:
    value = str(raw).strip()
    if not value:
        return default
    if re.fullmatch(r"#[0-9a-fA-F]{3,4}|#[0-9a-fA-F]{6}|#[0-9a-fA-F]{8}", value):
        return value
    # Resolve Tk's named colors to values rather than allowing arbitrary
    # CSS strings from an untrusted project to become SVG attributes.
    try:
        red, green, blue = canvas.winfo_rgb(value)
    except Exception as exc:
        raise ValueError(f"Canvas color cannot be exported: {value!r}") from exc
    return f"#{red // 257:02x}{green // 257:02x}{blue // 257:02x}"


def _stroke(canvas: object, item_id: int, attrs: dict[str, str],
            *, fill_key: str = "fill", stroke_key: str = "outline") -> None:
    attrs["fill"] = (
        "none" if fill_key == "none"
        else _color(canvas, _option(canvas, item_id, fill_key))
    )
    attrs["stroke"] = _color(canvas, _option(canvas, item_id, stroke_key))
    if attrs["stroke"] != "none":
        attrs["stroke-width"] = _coord(float(_option(canvas, item_id, "width", "1") or 1))
    dash = _option(canvas, item_id, "dash").strip()
    if dash:
        if not NUMBER_DASH.fullmatch(dash):
            raise ValueError("Unsupported Tk line-dash specification")
        attrs["stroke-dasharray"] = ",".join(dash.split())
    stipple = _option(canvas, item_id, "stipple")
    if stipple in {"gray12", "gray25", "gray50", "gray75"}:
        attrs["fill-opacity"] = {
            "gray12": "0.12", "gray25": "0.25",
            "gray50": "0.5", "gray75": "0.75",
        }[stipple]
    elif stipple:
        raise ValueError("Unsupported Tk stipple: cannot silently drop pattern")


def svg_from_3d_canvas(canvas: object) -> str:
    """Serialize current rendered shapes with no project or canvas mutation."""
    width = int(canvas.winfo_width())
    height = int(canvas.winfo_height())
    if width < 100 or height < 100 or width > 16000 or height > 16000:
        raise ValueError("Open and expand the 3D viewport before exporting")
    ids = list(canvas.find_all())
    if not ids:
        raise ValueError("3D viewport has no visible objects to export")
    if len(ids) > MAX_CANVAS_ITEMS:
        raise ValueError("Too many 3D canvas objects for a safe SVG export")

    root = ET.Element(_tag("svg"), {
        "width": str(width), "height": str(height),
        "viewBox": f"0 0 {width} {height}", "version": "1.1",
    })
    ET.SubElement(root, _tag("title")).text = "CleanroomX 3D design viewport"
    ET.SubElement(root, _tag("desc")).text = (
        "Presentation snapshot of the current CAD viewport. Design-zone "
        "colors and annotations are not CFD measurements, solver validation "
        "or evidence of ISO/GMP compliance. Fonts and Tk stipple are "
        "approximated by SVG rendering."
    )
    definitions = ET.SubElement(root, _tag("defs"))
    marker = ET.SubElement(definitions, _tag("marker"), {
        "id": "cx-arrowhead", "markerWidth": "6", "markerHeight": "6",
        "refX": "5", "refY": "3", "orient": "auto-start-reverse",
        "markerUnits": "strokeWidth",
    })
    ET.SubElement(marker, _tag("path"), {
        "d": "M0,0 L6,3 L0,6 Z", "fill": "context-stroke",
    })
    clip = ET.SubElement(definitions, _tag("clipPath"), {"id": "cx-viewbox"})
    ET.SubElement(clip, _tag("rect"), {
        "width": str(width), "height": str(height),
    })
    ET.SubElement(root, _tag("rect"), {
        "width": str(width), "height": str(height),
        "fill": _color(canvas, str(canvas.cget("background"))),
    })
    group = ET.SubElement(root, _tag("g"), {"clip-path": "url(#cx-viewbox)"})
    rendered = 0

    for item_id in ids:
        if _option(canvas, item_id, "state") == "hidden":
            continue
        kind = str(canvas.type(item_id))
        if kind not in SUPPORTED_ITEMS:
            raise ValueError(f"Cannot faithfully export unsupported canvas item: {kind}")
        coords = list(canvas.coords(item_id))
        if not all(math.isfinite(float(n)) for n in coords):
            raise ValueError("Non-finite 3D canvas geometry")
        if kind == "line":
            if len(coords) < 4 or len(coords) % 2:
                raise ValueError("Invalid 3D polyline")
            attrs = {
                "points": " ".join(
                    ",".join((_coord(coords[i]), _coord(coords[i + 1])))
                    for i in range(0, len(coords), 2)
                ),
                "stroke-linejoin": "round", "stroke-linecap": "round",
            }
            _stroke(canvas, item_id, attrs, fill_key="none", stroke_key="fill")
            # Tk line fill is its stroke; SVG polyline interior is empty.
            arrow = _option(canvas, item_id, "arrow")
            if arrow in ("first", "both"):
                attrs["marker-start"] = "url(#cx-arrowhead)"
            if arrow in ("last", "both"):
                attrs["marker-end"] = "url(#cx-arrowhead)"
            ET.SubElement(group, _tag("polyline"), attrs)
        elif kind in {"polygon", "rectangle", "oval"}:
            if kind == "polygon":
                if len(coords) < 6 or len(coords) % 2:
                    raise ValueError("Invalid 3D polygon")
                attrs = {
                    "points": " ".join(
                        ",".join((_coord(coords[i]), _coord(coords[i + 1])))
                        for i in range(0, len(coords), 2)
                    ),
                }
                shape = "polygon"
            else:
                if len(coords) != 4:
                    raise ValueError("Invalid rectangle/ellipse coordinates")
                x0, y0, x1, y1 = map(float, coords)
                if kind == "rectangle":
                    attrs = {
                        "x": _coord(min(x0, x1)), "y": _coord(min(y0, y1)),
                        "width": _coord(abs(x1 - x0)),
                        "height": _coord(abs(y1 - y0)),
                    }
                    shape = "rect"
                else:
                    attrs = {
                        "cx": _coord((x0 + x1) / 2),
                        "cy": _coord((y0 + y1) / 2),
                        "rx": _coord(abs(x1 - x0) / 2),
                        "ry": _coord(abs(y1 - y0) / 2),
                    }
                    shape = "ellipse"
            _stroke(canvas, item_id, attrs)
            ET.SubElement(group, _tag(shape), attrs)
        else:
            if len(coords) != 2:
                raise ValueError("Invalid 3D text anchor")
            value = _option(canvas, item_id, "text")
            anchor = _option(canvas, item_id, "anchor", "center")
            h_align = "start" if "w" in anchor else (
                "end" if "e" in anchor else "middle"
            )
            v_align = "hanging" if "n" in anchor else (
                "text-after-edge" if "s" in anchor else "central"
            )
            attrs = {
                "x": _coord(coords[0]), "y": _coord(coords[1]),
                "fill": _color(canvas, _option(canvas, item_id, "fill")),
                "text-anchor": h_align, "dominant-baseline": v_align,
                "font-family": "sans-serif", "font-size": "10",
            }
            if "bold" in _option(canvas, item_id, "font").lower():
                attrs["font-weight"] = "bold"
            item = ET.SubElement(group, _tag("text"), attrs)
            lines = value.split("\n")
            if len(lines) == 1:
                item.text = value
            else:
                for index, line in enumerate(lines):
                    ET.SubElement(item, _tag("tspan"), {
                        "x": attrs["x"], "dy": "0" if index == 0 else "1.25em",
                    }).text = line
        rendered += 1

    if not rendered:
        raise ValueError("3D viewport has no visible objects to export")
    return ET.tostring(root, encoding="unicode", xml_declaration=True) + "\n"


def save_3d_svg(canvas: object, destination: str | Path) -> Path:
    """Write complete SVG atomically. Do not leave a partial output on errors."""
    path = Path(destination)
    content = svg_from_3d_canvas(canvas)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n",
            dir=path.parent, prefix=".cleanroomx-view-", suffix=".tmp",
            delete=False,
        ) as handle:
            temp_name = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if temp_name is not None:
            Path(temp_name).unlink(missing_ok=True)
    return path
