from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def build_icon(path: Path) -> None:
    image = Image.new("RGBA", (256, 256), (20, 28, 40, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (8, 8, 248, 248),
        radius=38,
        fill=(20, 28, 40, 255),
        outline=(70, 180, 220, 255),
        width=8,
    )
    draw.rectangle((42, 48, 214, 68), fill=(72, 190, 225, 255))
    draw.rectangle((42, 188, 214, 208), fill=(72, 190, 225, 255))
    for x in (58, 104, 150, 196):
        draw.rounded_rectangle(
            (x, 76, x + 20, 180),
            radius=8,
            fill=(235, 242, 248, 255),
        )
    draw.rounded_rectangle(
        (82, 92, 174, 164),
        radius=18,
        fill=(30, 53, 72, 255),
        outline=(72, 190, 225, 255),
        width=4,
    )
    try:
        font = ImageFont.truetype("arialbd.ttf", 38)
    except OSError:
        font = ImageFont.load_default()
    label = "CX"
    box = draw.textbbox((0, 0), label, font=font)
    width = box[2] - box[0]
    height = box[3] - box[1]
    draw.text(
        ((256 - width) / 2, (256 - height) / 2 - 3),
        label,
        font=font,
        fill=(255, 255, 255, 255),
    )
    image.save(
        path,
        format="ICO",
        sizes=[
            (16, 16),
            (24, 24),
            (32, 32),
            (48, 48),
            (64, 64),
            (128, 128),
            (256, 256),
        ],
    )


if __name__ == "__main__":
    build_icon(Path(__file__).with_name("cleanroomx.ico"))
