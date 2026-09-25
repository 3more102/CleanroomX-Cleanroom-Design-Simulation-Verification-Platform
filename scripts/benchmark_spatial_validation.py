from __future__ import annotations

from time import perf_counter

from cleanroomx.spatial import (
    SPATIAL_GEOMETRY_EPSILON_M,
    _room_overlap_records,
    validate_layout,
)


def _grid(side: int) -> list[dict]:
    room_size_m = 4.0
    rooms = []
    for row in range(side):
        for column in range(side):
            index = row * side + column
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
    print("CleanroomX spatial validation benchmark")
    print("layout,rooms,sweep_s,naive_s,full_validate_s,speedup")
    for label, side in (
        ("small", 10),
        ("medium", 25),
        ("large", 40),
        ("stress", 50),
    ):
        rooms = _grid(side)
        layout = {"rooms": rooms, "devices": []}
        sweep_seconds, sweep = _timed(lambda: _room_overlap_records(rooms))
        naive_seconds, naive = _timed(lambda: _naive_overlap_records(rooms))
        full_seconds, issues = _timed(lambda: validate_layout(layout))
        if sweep != naive:
            raise RuntimeError(f"{label} overlap result differs from reference scan")
        if issues:
            raise RuntimeError(f"{label} touching-room grid unexpectedly produced warnings")
        speedup = naive_seconds / max(sweep_seconds, 1e-12)
        print(
            f"{label},{len(rooms)},{sweep_seconds:.6f},{naive_seconds:.6f},"
            f"{full_seconds:.6f},{speedup:.2f}x"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
