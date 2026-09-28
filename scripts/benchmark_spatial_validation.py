from __future__ import annotations

from math import ceil, sqrt
from time import perf_counter

from cleanroomx.spatial import (
    SPATIAL_GEOMETRY_EPSILON_M,
    _room_overlap_records,
    _validate_normalized_layout,
    normalize_layout,
    validate_layout,
)


CASES = (
    ("small", 100, 250),
    ("medium", 500, 1_250),
    ("large", 1_000, 2_500),
)


def _grid(count: int) -> list[dict]:
    room_size_m = 4.0
    columns = max(1, ceil(sqrt(count)))
    rooms = []
    for index in range(count):
        row, column = divmod(index, columns)
        rooms.append(
            {
                "id": f"room-{index}",
                "name": f"Room {index}",
                "x_m": column * room_size_m,
                "y_m": row * room_size_m,
                "length_m": room_size_m,
                "width_m": room_size_m,
                "height_m": 3.0,
            }
        )
    return rooms


def _devices(rooms: list[dict], count: int) -> list[dict]:
    devices = []
    for index in range(count):
        room = rooms[index % len(rooms)]
        devices.append(
            {
                "id": f"device-{index}",
                "type": "sensor" if index % 2 == 0 else "equipment",
                "name": f"Device {index}",
                "room_id": room["id"],
                "x_m": room["x_m"] + room["length_m"] / 2,
                "y_m": room["y_m"] + room["width_m"] / 2,
                "z_m": min(1.5, room["height_m"]),
            }
        )
    return devices


def _naive_overlap_records(rooms: list[dict]) -> list[tuple[int, int, list[float]]]:
    overlaps = []
    for left_index, left in enumerate(rooms):
        left_x1 = left["x_m"] + left["length_m"]
        left_y1 = left["y_m"] + left["width_m"]
        for right_index in range(left_index + 1, len(rooms)):
            right = rooms[right_index]
            right_x1 = right["x_m"] + right["length_m"]
            right_y1 = right["y_m"] + right["width_m"]
            x0 = max(left["x_m"], right["x_m"])
            y0 = max(left["y_m"], right["y_m"])
            x1 = min(left_x1, right_x1)
            y1 = min(left_y1, right_y1)
            if (
                x1 > x0 + SPATIAL_GEOMETRY_EPSILON_M
                and y1 > y0 + SPATIAL_GEOMETRY_EPSILON_M
            ):
                overlaps.append((left_index, right_index, [x0, y0, x1, y1]))
    return overlaps


def _timed(callable_):
    started = perf_counter()
    result = callable_()
    return perf_counter() - started, result


def main() -> int:
    print("CleanroomX Release 2 spatial validation benchmark")
    print(
        "layout,rooms,devices,sweep_s,naive_s,normalized_validate_s,"
        "public_validate_s,overlap_speedup"
    )
    for label, room_count, device_count in CASES:
        rooms = _grid(room_count)
        devices = _devices(rooms, device_count)
        layout = {"rooms": rooms, "devices": devices}
        normalized_layout = normalize_layout(layout)
        sweep_seconds, sweep = _timed(lambda: _room_overlap_records(rooms))
        naive_seconds, naive = _timed(lambda: _naive_overlap_records(rooms))
        normalized_seconds, normalized_issues = _timed(
            lambda: _validate_normalized_layout(normalized_layout)
        )
        full_seconds, issues = _timed(lambda: validate_layout(layout))
        if sweep != naive:
            raise RuntimeError(f"{label} overlap result differs from reference scan")
        if normalized_issues != issues:
            raise RuntimeError(
                f"{label} normalized/public validation results differ"
            )
        if issues:
            raise RuntimeError(
                f"{label} valid synthetic project unexpectedly produced warnings: "
                f"{issues[:3]!r}"
            )
        speedup = naive_seconds / max(sweep_seconds, 1e-12)
        print(
            f"{label},{len(rooms)},{len(devices)},{sweep_seconds:.6f},"
            f"{naive_seconds:.6f},{normalized_seconds:.6f},"
            f"{full_seconds:.6f},{speedup:.2f}x"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
