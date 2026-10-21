"""GUI scroll contracts: chart routing, native controls, and local binding."""
import tkinter as tk
from tkinter import ttk
import pytest
from cleanroomx.gui_scrollable import _owns_wheel, create_scrollable_content


def test_scrollable_tabs_are_independent():
    root = tk.Tk()
    try:
        root.geometry("500x340")
        tabs = ttk.Notebook(root)
        tabs.pack(fill="both", expand=True)
        hosts = [ttk.Frame(tabs), ttk.Frame(tabs)]
        for number, host in enumerate(hosts):
            tabs.add(host, text=str(number))
            panel = create_scrollable_content(host)
            for i in range(80):
                ttk.Label(panel, text=f"row {number} - {i}").pack()
        root.update()
        c0 = hosts[0]._cleanroomx_scroll_canvas
        c1 = hosts[1]._cleanroomx_scroll_canvas
        c0.event_generate("<MouseWheel>", delta=-120)
        root.update()
        assert c0.yview()[0] > 0
        assert c1.yview()[0] == 0
    finally:
        root.destroy()


def test_native_scroll_controls_keep_ownership():
    root = tk.Tk()
    try:
        host = ttk.Frame(root)
        host.pack()
        body = create_scrollable_content(host)
        label = ttk.Label(body, text="ordinary label")
        label.pack()
        text = tk.Text(body)
        text.pack()
        table = ttk.Treeview(body)
        table.pack()
        custom_canvas = tk.Canvas(body, yscrollcommand=lambda *args: None)
        custom_canvas.pack()
        plain_chart = tk.Canvas(body)
        plain_chart.pack()
        root.update()
        assert _owns_wheel(text)
        assert _owns_wheel(table)
        assert _owns_wheel(custom_canvas)
        assert not _owns_wheel(plain_chart)
        assert not _owns_wheel(label)
    finally:
        root.destroy()
