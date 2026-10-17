"""Vector screenshot tests; no GUI display or CFD solver required."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
import xml.etree.ElementTree as ET

import pytest

from cleanroomx.spatial_3d_export import (
    SVG_NS, save_3d_svg, svg_from_3d_canvas,
)

S = "{" + SVG_NS + "}"


class SnapshotCanvas:
    def __init__(self):
        self.width, self.height = 860, 510
        self.items = [
            ("polygon", (8, 12, 180, 13, 180, 120, 8, 120),
             {"fill": "#38bdf8", "outline": "#f8fafc",
              "width": "2", "stipple": "gray50"}),
            ("line", (180, 80, 290, 120),
             {"fill": "#fb7185", "width": "2", "dash": "4 2",
              "arrow": "last"}),
            ("rectangle", (12, 17, 102, 40),
             {"fill": "#101d30", "outline": "#4e6c8c"}),
            ("oval", (65, 75, 80, 90),
             {"fill": "#fbbf24", "outline": "#ffffff"}),
            ("text", (25, 32),
             {"text": "Room <A> & B\nDesign only", "fill": "#eef7ff",
              "anchor": "nw", "font": "TkDefaultFont 9 bold"}),
            ("text", (25, 32),
             {"text": "hidden private text", "fill": "#eef7ff",
              "state": "hidden"}),
        ]

    def winfo_width(self):
        return self.width

    def winfo_height(self):
        return self.height

    def find_all(self):
        return tuple(range(1, len(self.items) + 1))

    def type(self, item_id):
        return self.items[item_id - 1][0]

    def coords(self, item_id):
        return self.items[item_id - 1][1]

    def itemcget(self, item_id, option):
        data = self.items[item_id - 1][2]
        if option not in data:
            raise tk.TclError("unknown Tk option")
        return data[option]

    def cget(self, option):
        assert option == "background"
        return "#0b1526"

    def winfo_rgb(self, color):
        if color == "white":
            return (65535, 65535, 65535)
        raise tk.TclError("unknown color")


def test_svg_preserves_shape_order_labels_arrows_and_metadata():
    canvas = SnapshotCanvas()
    text = svg_from_3d_canvas(canvas)
    root = ET.fromstring(text)
    assert root.attrib["viewBox"] == "0 0 860 510"
    assert "not CFD measurements" in root.find(S + "desc").text
    group = root.find(S + "g")
    kinds = [child.tag for child in group]
    assert kinds == [
        S + "polygon", S + "polyline", S + "rect",
        S + "ellipse", S + "text",
    ]
    assert group[0].attrib["fill-opacity"] == "0.5"
    assert group[1].attrib["stroke-dasharray"] == "4,2"
    assert group[1].attrib["marker-end"] == "url(#cx-arrowhead)"
    assert group[1].attrib["fill"] == "none"
    assert group[4].findall(S + "tspan")[0].text == "Room <A> & B"
    assert "hidden private text" not in text
    assert not root.findall(".//" + S + "script")


def test_export_is_atomic_and_does_not_change_canvas(tmp_path):
    canvas = SnapshotCanvas()
    original = list(canvas.items)
    path = tmp_path / "design-3d.svg"
    assert save_3d_svg(canvas, path) == path
    assert ET.parse(path).getroot().find(S + "title").text.startswith("CleanroomX")
    assert list(canvas.items) == original
    assert not list(tmp_path.glob(".cleanroomx-view-*.tmp"))

    bad = SnapshotCanvas()
    bad.items[0] = ("image", (8, 12), {})
    baseline = path.read_bytes()
    with pytest.raises(ValueError, match="unsupported"):
        save_3d_svg(bad, path)
    assert path.read_bytes() == baseline


def test_invalid_viewport_and_coordinates_fail_closed():
    canvas = SnapshotCanvas()
    canvas.width = 45
    with pytest.raises(ValueError, match="expand"):
        svg_from_3d_canvas(canvas)
    canvas.width = 860
    canvas.items[0] = ("line", (0, 0, float("nan"), 2),
                       {"fill": "#ffffff"})
    with pytest.raises(ValueError, match="Non-finite"):
        svg_from_3d_canvas(canvas)


def test_named_colors_are_normalized_and_xml_text_escaped():
    canvas = SnapshotCanvas()
    canvas.items = [("text", (20, 30), {
        "text": 'A <tag> & "x"', "fill": "white", "anchor": "center"
    })]
    result = svg_from_3d_canvas(canvas)
    assert "&lt;tag&gt;" in result
    assert "&amp;" in result
    assert 'fill="#ffffff"' in result
    assert ET.fromstring(result).find(".//" + S + "text").text == 'A <tag> & "x"'


def test_save_failure_keeps_previously_saved_file(tmp_path):
    canvas = SnapshotCanvas()
    destination = tmp_path / "design.svg"
    destination.write_text("previous good output", encoding="utf-8")
    canvas.items[0] = ("polygon", (1, 2, 3), {
        "fill": "#abcdef", "outline": "#123456",
    })
    with pytest.raises(ValueError, match="Invalid 3D polygon"):
        save_3d_svg(canvas, destination)
    assert destination.read_text(encoding="utf-8") == "previous good output"
