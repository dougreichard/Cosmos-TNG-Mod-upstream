"""Cut a REGULAR mosaic grid into cells - the Gemini "race sheet" layout.

A different problem from cut_grid.py, needing a different method. Those sheets were
islands of colour in a starfield, so a contour finder could pick each panel out as a
shape. These are TIGHT MOSAICS: 64 portraits butted edge to edge under a title bar,
separated only by a hairline. Canny merges a whole row into one blob, and the contour
finder returned 1-2 "panels" for a sheet that plainly has 64.

So fit the LATTICE instead of finding the shapes. Three things had to be right, and
each was a wrong answer first:

  BANNERS are bounded by a black RULE, not by darkness. The banner is white title
  text on black, so its text rows are only 50-68% dark; a "trim mostly-dark rows"
  scan stopped at the first line of lettering and took 5px off a 30px banner, leaving
  every row of the lattice a fraction of a panel low and clipping the bottom row of
  faces. The hairline enclosing the banner IS ~100% black across the full width,
  which no row of portraits ever is, so that is what to look for.

  EDGE ENERGY, not darkness, locates the gutters. Plenty of these panels have a
  near-black backdrop of their own, so a line through a face can be darker than a
  real gutter, and two neighbours in similar colours butt together with no dark rule
  at all. What is always true at a panel edge is that the picture CHANGES.

  FIT A PHASE, not just a period. Some sheets sit flush with the image; the titled
  ones put their column edges at 97, 225, 353 ... 865 - a clean 128px period with a
  phase of -31 - so the outer column is a partial panel running off the edge.
  Assuming lines at k*L/n cannot express that, and it is exactly why those four
  sheets scored NEGATIVE on columns while being visibly 8 across.

Partial edge panels are DROPPED, not padded: two-thirds of a face is not usable art.

RESOLUTION. These land at ~128px against the 512 an atlas cell wants. That is a 4x
upscale - worse than the 2.67x that made the mod's original faces look soft - so this
tool reports the native size and never silently upscales. Run the ESRGAN pass
(--upscale) or ask for fewer faces per sheet.
"""
import argparse
import os

import cv2
import numpy as np


def trim_bars(img, dark=70, rule=0.97, zone=0.15):
    """Drop the title/footer banner, by finding the black rule that bounds it."""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h = g.shape[0]
    solid = (g < dark).mean(axis=1) >= rule
    z = max(4, int(h * zone))
    top = max([y for y in range(z) if solid[y]], default=-1) + 1
    bot = min([y for y in range(h - z, h) if solid[y]], default=h)
    return img[top:bot], top


def _edges(img, axis, thresh=26):
    """Profile of how much of the line is a real boundary - a COVERAGE, not a sum.

    Summing |difference| along the line was the obvious measure and it is the wrong
    one: a few very strong local edges - the dark line of a mouth, a jaw against a
    pale background, epaulettes - outweigh a genuine gutter, so the row fit locked
    onto facial features and sliced sheets straight across every face.

    What distinguishes a panel boundary is that EVERY panel changes there at once, so
    the change spans the full width. Measuring the FRACTION of positions along the
    line whose change exceeds a threshold rewards that and is nearly blind to a
    handful of strong local edges, however strong they are. Same idea as before -
    discontinuity, not darkness - but counted rather than added.
    """
    a = img.astype(np.int16)
    d = np.abs(np.diff(a, axis=axis)).max(axis=2)      # per-pixel change, any channel
    e = (d > thresh).mean(axis=1 - axis)               # fraction of the line that moved
    return (e - e.mean()) / (e.std() + 1e-6)


def bounds(L, P, ph, tol=0.90):
    """Panel spans from a fitted lattice, keeping only COMPLETE panels."""
    cuts = sorted({0} | {x for x in range(ph % P, L + 1, P)} | {L})
    return [(a, b) for a, b in zip(cuts, cuts[1:]) if b - a >= P * tol]


def margin_strip(img, xs, frac=0.10):
    """The columns that fall in each panel's left/right MARGIN, stacked together.

    Solving the row phase off the whole image never became reliable, because a face
    fills the middle of every panel and its brow, eyes, mouth and shoulders are all
    strong full-ish-width horizontal edges. Each metric I tried fixed some sheets and
    broke others - the signal simply is not cleanly separable there.

    The margins are. A bust is centred, so the first and last tenth of every panel is
    the flat backdrop, top to bottom - no face in it at all. Restricting the row fit
    to those columns means the only thing that can change vertically is the backdrop
    itself, which changes exactly at a panel boundary and nowhere else. Columns are
    already solved at this point (they fit cleanly off the full image), so their
    bounds are available to say where the margins are.
    """
    keep = []
    for x0, x1 in xs:
        m = max(2, int((x1 - x0) * frac))
        keep.extend(range(x0, x0 + m))
        keep.extend(range(max(x0, x1 - m), x1))
    return img[:, sorted(set(keep))]


def fit_lattice(img, axis, pmin=95, pmax=200, need=5, period=None, near=0.70):
    """Fit (score, period, phase) of the panel lattice along `axis`.

    Pass `period` to fit the PHASE ONLY against a known period. That is how rows are
    solved: the vertical signal is much weaker than the horizontal one, because eyes,
    mouths and shoulder lines are strong horizontal edges INSIDE a panel and compete
    with the real gutters. The panels are square, so the column period - measured off
    a clean signal - is the row period too, and constraining it removes the ambiguity
    rather than trying to out-tune it.

    `near` DECIDES TIES BY COVERAGE, and it matters as much as the score. A phase that
    is a fraction of a panel out still lands most of its lines near real edges, so it
    can win by a hair while throwing a whole row or column of art away as "partial":
    the ferengi and android sheets both scored phase 97 at 1.59 against phase 0 at
    1.20, and cut 7 columns out of 8, slicing every remaining face 31px off centre.
    Discarding a column of finished art should need real evidence, not a 0.4
    difference - so among phases scoring within `near` of the best, the one yielding
    the most COMPLETE panels wins.

    This cannot disturb a sheet where a partial row is genuine. On the banner sheets
    the first row really is clipped by the title bar, and there the correct phase
    scores 5.0-7.6 while phase 0 scores NEGATIVE - nowhere near the threshold.
    """
    e = _edges(img, axis)
    L = len(e) + 1
    cands = []
    for P in ([period] if period else range(pmin, pmax + 1)):
        for ph in range(P):
            xs = [x - 1 for x in range(ph, L, P) if 0 < x < L]
            if len(xs) < need:
                continue
            sc = min(e[max(0, x - 1):x + 2].max() for x in xs)
            cands.append((sc, P, ph))
    if not cands:
        return (0.0, period or pmin, 0)
    best = max(c[0] for c in cands)
    if best > 0:
        close = [c for c in cands if c[0] >= best * near]
        # most complete panels first, then best score
        close.sort(key=lambda c: (len(bounds(L, c[1], c[2])), c[0]), reverse=True)
        return close[0]
    return max(cands)


def cut(img, inset=0.05):
    """Trim banners, fit both lattices, return (cells, cols, rows, report)."""
    img, top = trim_bars(img)
    h, w = img.shape[:2]
    scx, Px, phx = fit_lattice(img, 1)
    xs = bounds(w, Px, phx)
    scy, Py, phy = fit_lattice(margin_strip(img, xs), 0, period=Px)
    ys = bounds(h, Py, phy)
    cells = []
    for y0, y1 in ys:
        for x0, x1 in xs:
            dx, dy = int((x1 - x0) * inset), int((y1 - y0) * inset)
            cells.append(img[y0 + dy:y1 - dy, x0 + dx:x1 - dx])
    rep = dict(trimmed=top, period=(Px, Py), phase=(phx, phy),
               score=(round(scx, 2), round(scy, 2)))
    return cells, len(xs), len(ys), rep


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("-o", "--out", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "out", "regular"))
    ap.add_argument("--prefix", default=None)
    ap.add_argument("--inset", type=float, default=0.05)
    ap.add_argument("--preview", action="store_true")
    a = ap.parse_args()

    img = cv2.imread(a.image)
    if img is None:
        raise SystemExit("cannot read " + a.image)
    cells, cols, rows, rep = cut(img, a.inset)
    ph, pw = cells[0].shape[:2]
    print("%s: %dx%d = %d panels of %dx%d  %s"
          % (os.path.basename(a.image), cols, rows, len(cells), pw, ph, rep))

    os.makedirs(a.out, exist_ok=True)
    stem = a.prefix or os.path.splitext(os.path.basename(a.image))[0].lower()
    for i, cel in enumerate(cells):
        cv2.imwrite(os.path.join(a.out, "%s_%02d.png" % (stem, i)), cel)
    if a.preview:
        p, _ = trim_bars(img)
        h, w = p.shape[:2]
        for x0, x1 in bounds(w, *fit_lattice(p, 1)[1:]):
            cv2.line(p, (x0, 0), (x0, h), (0, 0, 255), 2)
            cv2.line(p, (x1 - 1, 0), (x1 - 1, h), (0, 0, 255), 2)
        for y0, y1 in bounds(h, *fit_lattice(p, 0)[1:]):
            cv2.line(p, (0, y0), (w, y0), (0, 255, 0), 2)
            cv2.line(p, (0, y1 - 1), (w, y1 - 1), (0, 255, 0), 2)
        cv2.imwrite(os.path.join(a.out, stem + "_PREVIEW.png"), p)


if __name__ == "__main__":
    main()
