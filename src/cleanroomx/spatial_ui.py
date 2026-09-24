from __future__ import annotations

import copy
from typing import Any

import tkinter as tk
from tkinter import messagebox, ttk

from .layout import (
    Floor,
    LayoutObject,
    Room,
    SpatialLayout,
    dimension_conflicts,
    sync_room_geometry_to_analysis,
    validate_layout,
)


class SpatialWorkspace:
    """Shared controller for the canonical layout used by both 2D and 3D views."""

    def __init__(self, app: Any, notebook: ttk.Notebook):
        from .layout_2d import Layout2DFrame
        from .viewer_3d import Layout3DFrame

        self.app = app
        self.notebook = notebook
        self.selected_id: str | None = None
        self.undo_stack: list[dict] = []
        self.redo_stack: list[dict] = []
        self.clipboard: tuple[str, dict] | None = None
        self._refresh_pending = False

        self.layout_2d = Layout2DFrame(notebook, self)
        self.viewer_3d = Layout3DFrame(notebook, self)
        notebook.insert(1, self.layout_2d, text="2D Layout")
        notebook.insert(2, self.viewer_3d, text="3D View")
        notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed, add="+")

    @property
    def layout(self) -> SpatialLayout:
        return self.app.project.layout

    def current_floor(self, *, create: bool = False) -> Floor | None:
        floor = self.layout.active_floor()
        if floor is None and create:
            before = self.begin_change()
            floor = self.layout.ensure_floor()
            self.commit_change(before)
        return floor

    def begin_change(self) -> dict:
        return copy.deepcopy(self.layout.to_dict())

    def commit_change(self, before: dict, *, select_id: str | None = None) -> None:
        after = self.layout.to_dict()
        if before == after:
            return
        self.undo_stack.append(before)
        if len(self.undo_stack) > 100:
            del self.undo_stack[0]
        self.redo_stack.clear()
        if select_id is not None:
            self.selected_id = select_id
        self.mark_changed()

    def _restore(self, state: dict) -> None:
        self.app.project.layout = SpatialLayout.from_dict(copy.deepcopy(state))
        floor = self.app.project.layout.active_floor()
        if floor is None or self.selected_id is None:
            self.selected_id = None
        else:
            try:
                floor.entity_by_id(self.selected_id)
            except KeyError:
                self.selected_id = None
        self.refresh_all()
        self.app._update_title()

    def undo(self) -> None:
        if not self.undo_stack:
            return
        current = copy.deepcopy(self.layout.to_dict())
        state = self.undo_stack.pop()
        self.redo_stack.append(current)
        self._restore(state)

    def redo(self) -> None:
        if not self.redo_stack:
            return
        current = copy.deepcopy(self.layout.to_dict())
        state = self.redo_stack.pop()
        self.undo_stack.append(current)
        self._restore(state)

    def mark_changed(self) -> None:
        self.app._update_title()
        if self._refresh_pending:
            return
        self._refresh_pending = True
        try:
            self.app.root.after_idle(self._flush_refresh)
        except Exception:
            self._flush_refresh()

    def _flush_refresh(self) -> None:
        self._refresh_pending = False
        self.refresh_all()

    def refresh_all(self) -> None:
        self.layout_2d.refresh()
        self.viewer_3d.refresh()

    def on_project_changed(self) -> None:
        self.selected_id = None
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.clipboard = None
        self.refresh_all()

    def set_selection(self, entity_id: str | None) -> None:
        self.selected_id = entity_id
        self.layout_2d.refresh_selection_only()
        self.viewer_3d.refresh()

    def selected_entity(self) -> Room | LayoutObject | None:
        floor = self.current_floor()
        if floor is None or self.selected_id is None:
            return None
        try:
            return floor.entity_by_id(self.selected_id)
        except KeyError:
            return None

    def delete_selected(self) -> None:
        floor = self.current_floor()
        if floor is None or self.selected_id is None:
            return
        before = self.begin_change()
        if floor.remove_entity(self.selected_id):
            self.selected_id = None
            self.commit_change(before)

    def duplicate_selected(self, *, offset_m: float = 0.5) -> None:
        floor = self.current_floor()
        entity = self.selected_entity()
        if floor is None or entity is None:
            return
        before = self.begin_change()
        if isinstance(entity, Room):
            clone = Room.create(
                f"{entity.name} Copy",
                entity.x_m + offset_m,
                entity.y_m + offset_m,
                entity.width_m,
                entity.depth_m,
                height_m=entity.height_m,
                floor_elevation_m=entity.floor_elevation_m,
                pressure_pa=entity.pressure_pa,
                pressure_source=entity.pressure_source,
                classification=copy.deepcopy(entity.classification),
                analysis_room_ref=None,
            )
            floor.rooms.append(clone)
        else:
            clone = LayoutObject.create(
                entity.kind,
                entity.x_m + offset_m,
                entity.y_m + offset_m,
                name=f"{entity.name} Copy",
                room_id=entity.room_id,
                z_m=entity.z_m,
                width_m=entity.width_m,
                depth_m=entity.depth_m,
                height_m=entity.height_m,
                orientation_deg=entity.orientation_deg,
                properties=copy.deepcopy(entity.properties),
            )
            floor.objects.append(clone)
        self.commit_change(before, select_id=clone.id)

    def copy_selected(self) -> None:
        entity = self.selected_entity()
        if entity is None:
            return
        self.clipboard = (
            "room" if isinstance(entity, Room) else "object",
            copy.deepcopy(entity.to_dict()),
        )

    def paste(self) -> None:
        if self.clipboard is None:
            return
        floor = self.current_floor(create=True)
        if floor is None:
            return
        kind, data = self.clipboard
        before = self.begin_change()
        if kind == "room":
            original = Room.from_dict(data)
            clone = Room.create(
                f"{original.name} Copy",
                original.x_m + 0.5,
                original.y_m + 0.5,
                original.width_m,
                original.depth_m,
                height_m=original.height_m,
                floor_elevation_m=original.floor_elevation_m,
                pressure_pa=original.pressure_pa,
                pressure_source=original.pressure_source,
                classification=copy.deepcopy(original.classification),
            )
            floor.rooms.append(clone)
        else:
            original = LayoutObject.from_dict(data)
            clone = LayoutObject.create(
                original.kind,
                original.x_m + 0.5,
                original.y_m + 0.5,
                name=f"{original.name} Copy",
                room_id=original.room_id,
                z_m=original.z_m,
                width_m=original.width_m,
                depth_m=original.depth_m,
                height_m=original.height_m,
                orientation_deg=original.orientation_deg,
                properties=copy.deepcopy(original.properties),
            )
            floor.objects.append(clone)
        self.commit_change(before, select_id=clone.id)

    def validate(self, *, show_dialog: bool = True) -> list:
        issues = validate_layout(self.layout)
        if show_dialog:
            if not issues:
                messagebox.showinfo(
                    "Layout validation",
                    "Layout validation: no issues.",
                    parent=self.app.root,
                )
            else:
                lines = [f"{item.severity}: {item.message}" for item in issues[:20]]
                if len(issues) > 20:
                    lines.append(f"… {len(issues) - 20} more")
                messagebox.showinfo(
                    "Layout validation",
                    "\n".join(lines),
                    parent=self.app.root,
                )
        return issues

    def sync_selected_room_to_analysis(self) -> None:
        entity = self.selected_entity()
        if not isinstance(entity, Room):
            messagebox.showinfo(
                "Geometry sync", "Select a room first.", parent=self.app.root
            )
            return
        analysis = self.app._current_analysis()
        if analysis is None:
            messagebox.showinfo(
                "Geometry sync", "Select an analysis first.", parent=self.app.root
            )
            return
        try:
            self.app._commit_editor(analysis)
        except Exception as exc:
            messagebox.showerror("Geometry sync", str(exc), parent=self.app.root)
            return

        conflicts = dimension_conflicts(self.app.project, entity, analysis.id)
        details = "\n".join(
            f"{c.field}: analysis={c.analysis_value!r}, layout={c.geometry_value!r}"
            for c in conflicts
        ) or "No differing existing dimension values were found."
        if not messagebox.askyesno(
            "Sync geometry to analysis",
            f"Map layout width→length, depth→width, and height→height for "
            f"{entity.name!r}.\n\n{details}\n\nApply this explicit update?",
            parent=self.app.root,
        ):
            return

        before = self.begin_change()
        try:
            evidence = sync_room_geometry_to_analysis(
                self.app.project, entity, analysis.id
            )
        except Exception as exc:
            messagebox.showerror("Geometry sync", str(exc), parent=self.app.root)
            return
        self.commit_change(before)
        self.app._invalidate_last_run_for(analysis.id)
        self.app._load_analysis_into_editor(analysis)
        self.app.status_var.set(
            f"Geometry synced to {evidence['analysis_name']} / "
            f"{evidence['room_name']}"
        )

    def _on_tab_changed(self, event=None) -> None:
        selected = self.notebook.select()
        if selected in {str(self.layout_2d), str(self.viewer_3d)}:
            self.refresh_all()
