from __future__ import annotations

import argparse
from pathlib import Path
import struct


ICON_SIZES = (16, 24, 32, 48, 64, 128)


def _pixel_bgra(x: int, y: int, size: int) -> bytes:
    """Render a deterministic CleanroomX CX mark as one opaque BGRA pixel."""
    scale = size / 64.0
    border = max(1, round(3 * scale))
    stroke = max(1, round(5 * scale))
    margin = max(2, round(8 * scale))

    # Deep workstation background with a restrained cyan/white CX mark.
    background = (38, 31, 22, 255)  # BGRA
    accent = (238, 188, 73, 255)
    foreground = (246, 246, 246, 255)

    if x < border or y < border or x >= size - border or y >= size - border:
        return bytes(accent)

    cx = size * 0.32
    cy = size * 0.50
    radius = size * 0.23
    distance = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
    c_ring = abs(distance - radius) <= stroke * 0.52
    c_opening = x > cx + radius * 0.35 and abs(y - cy) < radius * 0.62

    x_center = size * 0.70
    x_half = size * 0.15
    in_x_box = abs(x - x_center) <= x_half and margin <= y < size - margin
    diagonal_a = abs((x - x_center) - (y - cy) * 0.43) <= stroke * 0.55
    diagonal_b = abs((x - x_center) + (y - cy) * 0.43) <= stroke * 0.55
    x_mark = in_x_box and (diagonal_a or diagonal_b)

    if c_ring and not c_opening:
        return bytes(foreground)
    if x_mark:
        return bytes(accent)
    return bytes(background)


def _dib_image(size: int) -> bytes:
    row_bytes = size * 4
    xor_bitmap = bytearray()
    for y in range(size - 1, -1, -1):
        for x in range(size):
            xor_bitmap.extend(_pixel_bgra(x, y, size))

    mask_row_bytes = ((size + 31) // 32) * 4
    and_mask = bytes(mask_row_bytes * size)
    header = struct.pack(
        "<IIIHHIIIIII",
        40,
        size,
        size * 2,
        1,
        32,
        0,
        row_bytes * size,
        0,
        0,
        0,
        0,
    )
    return header + bytes(xor_bitmap) + and_mask


def render_icon() -> bytes:
    images = [(size, _dib_image(size)) for size in ICON_SIZES]
    directory_size = 6 + 16 * len(images)
    offset = directory_size
    entries = bytearray()
    payload = bytearray()

    for size, image in images:
        entries.extend(
            struct.pack(
                "<BBBBHHII",
                0 if size == 256 else size,
                0 if size == 256 else size,
                0,
                0,
                1,
                32,
                len(image),
                offset,
            )
        )
        payload.extend(image)
        offset += len(image)

    return struct.pack("<HHH", 0, 1, len(images)) + bytes(entries) + bytes(payload)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Write the deterministic multi-resolution CleanroomX Windows icon."
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(render_icon())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
