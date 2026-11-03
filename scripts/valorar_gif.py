"""Assemble the README's Valorar GIF from the frames `screens/valorar-flow.spec.ts` writes.

Usage (from the repository root, after recording the frames):
    uv run python scripts/valorar_gif.py frontend/screens-out/valorar-flow docs/design/valorar.gif

Each frame is shown for 120 ms. The output is scaled to 880 px wide and reduced to a
shared 128-colour palette, which keeps it well under the README's 5 MB budget.
"""

import sys
from pathlib import Path

from PIL import Image

FRAME_MS = 120
WIDTH = 880
BUDGET_BYTES = 5 * 1024 * 1024


def main(frames_dir: str, output: str) -> int:
    """Write the GIF and return 0, or 1 with no frames and 2 when it exceeds the budget.

    Args:
        frames_dir: Directory of PNG frames, assembled in name order.
        output: Path of the GIF to write.

    Returns:
        The process exit code.
    """
    paths = sorted(Path(frames_dir).glob("*.png"))
    if not paths:
        sys.stderr.write(f"no frames in {frames_dir}\n")
        return 1
    frames = []
    for path in paths:
        image = Image.open(path).convert("RGB")
        height = round(image.height * WIDTH / image.width)
        frames.append(image.resize((WIDTH, height), Image.Resampling.LANCZOS))
    palette = frames[len(frames) // 2].quantize(colors=128, method=Image.Quantize.MEDIANCUT)
    quantised = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    quantised[0].save(
        out,
        save_all=True,
        append_images=quantised[1:],
        duration=FRAME_MS,
        loop=0,
        optimize=True,
        disposal=1,
    )
    size = out.stat().st_size
    sys.stdout.write(f"{out}: {len(frames)} frames, {size / 1e6:.2f} MB\n")
    return 0 if size <= BUDGET_BYTES else 2


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
