from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "images"
TARGET = ROOT / "reports" / "_tmp_hcmc_contact_sheets"
COLS = 8
ROWS = 8
CELL = (240, 170)
PER_SHEET = COLS * ROWS


def sort_key(path: Path) -> int:
    return int(path.stem.split("_", 1)[0])


def main() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    files = sorted(SOURCE.glob("*.jpg"), key=sort_key)
    font = ImageFont.load_default(size=16)

    for start in range(0, len(files), PER_SHEET):
        canvas = Image.new("RGB", (COLS * CELL[0], ROWS * CELL[1]), "black")
        draw = ImageDraw.Draw(canvas)
        for slot, path in enumerate(files[start : start + PER_SHEET]):
            index = start + slot
            x = (slot % COLS) * CELL[0]
            y = (slot // COLS) * CELL[1]
            with Image.open(path) as raw:
                image = ImageOps.exif_transpose(raw).convert("RGB")
                image.thumbnail((CELL[0] - 8, CELL[1] - 30))
                dx = x + (CELL[0] - image.width) // 2
                dy = y + (CELL[1] - 30 - image.height) // 2
                canvas.paste(image, (dx, dy))
            draw.text(
                (x + 4, y + CELL[1] - 24),
                f"{index:04d} {path.stem[:13]}",
                fill="white",
                font=font,
            )
        end = min(start + PER_SHEET - 1, len(files) - 1)
        output = TARGET / f"sheet-{start // PER_SHEET + 1:02d}-{start:04d}-{end:04d}.jpg"
        if output.exists():
            continue
        canvas.save(output, quality=88)

    print(f"source_count={len(files)} sheet_count={len(list(TARGET.glob('*.jpg')))}")


if __name__ == "__main__":
    main()
