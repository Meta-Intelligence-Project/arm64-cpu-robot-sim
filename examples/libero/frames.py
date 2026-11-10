"""Export the saved initial/final agentview frames as a labeled PNG."""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path, help="episode *_first_last_agentview.npy")
    p.add_argument("output", type=Path, help="new PNG path")
    a = p.parse_args()
    frames = np.load(a.input, allow_pickle=False)
    if frames.ndim != 4 or frames.shape[0] != 2 or frames.shape[-1] != 3:
        p.error("expected two H x W x RGB frames")
    if frames.dtype != np.uint8:
        p.error("expected uint8 RGB frames")
    images = [Image.fromarray(frame).resize((512, 512), Image.Resampling.NEAREST) for frame in frames]
    canvas = Image.new("RGB", (1036, 544), "white")
    draw = ImageDraw.Draw(canvas)
    for i, im in enumerate(images):
        x = i * 524
        canvas.paste(im, (x, 32))
        draw.text((x + 8, 8), ["Initial observation", "Final observation"][i], fill="black")
    with a.output.open("xb") as f:
        canvas.save(f, format="PNG")


if __name__ == "__main__":
    main()
