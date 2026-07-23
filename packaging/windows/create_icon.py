from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert Tubby's PNG logo to a Windows icon.")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(arguments.source) as image:
        image.convert("RGBA").save(
            arguments.output,
            format="ICO",
            sizes=[(size, size) for size in ICON_SIZES],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
