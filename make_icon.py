#!/usr/bin/env python3
# Eclipse Dispatch MCP
# Copyright © 2026 Cyan Eclipse Technologies LLC · cetech.ai
# Generate icon-512.png — brand system §6: eclipse motif on the navy

"""Generate icon-512.png — brand system §6: eclipse motif on the navy
field (#0d1b2a), one per-product glyph. Dispatch's glyph is the sent
signal: a crescent eclipse ring with broadcast arcs radiating outward
— a report going out from the field. PIL only; deterministic."""
from PIL import Image, ImageDraw

S = 512
NAVY = (13, 27, 42, 255)
STOPS = [(15, 246, 247), (0, 212, 255), (123, 44, 191)]  # cyan->blue->purple


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)) + (255,)


def grad(t):
    return lerp(STOPS[0], STOPS[1], t * 2) if t < 0.5 else \
        lerp(STOPS[1], STOPS[2], (t - 0.5) * 2)


def main():
    img = Image.new("RGBA", (S, S), NAVY)
    d = ImageDraw.Draw(img)
    # Eclipse ring, center-left: gradient arc segments.
    box = [70, 106, 334, 370]
    for i in range(72):
        t = i / 72
        d.arc(box, start=i * 5, end=i * 5 + 6, fill=grad(t), width=17)
    d.ellipse([134, 170, 270, 306], fill=NAVY)  # occluding body
    # Broadcast arcs: the dispatch leaving the ring, upper-right.
    cx, cy = 202, 238
    for j, r in enumerate((86, 138, 190)):
        arc_box = [cx - r, cy - r, cx + r, cy + r]
        d.arc(arc_box, start=-58, end=38, fill=grad(0.25 + j * 0.3), width=13)
    # One star: the byline point.
    x, y, r = 420, 96, 15
    d.polygon([(x, y - r), (x + r * 0.28, y - r * 0.28), (x + r, y),
               (x + r * 0.28, y + r * 0.28), (x, y + r),
               (x - r * 0.28, y + r * 0.28), (x, y),
               (x - r * 0.28, y - r * 0.28)], fill=grad(0.85))
    img.save("icon-512.png")
    print("wrote icon-512.png", img.size, img.mode)


if __name__ == "__main__":
    main()

# Eclipse Dispatch MCP · © 2026 Cyan Eclipse Technologies LLC · cetech.ai
