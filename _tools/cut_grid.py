"""Cut a cast grid (a Gemini "TAS cast" image) into individual face cells.

Gemini produces these in exactly the style and with exactly the division colours
that SDXL kept fighting - Sisko red, O'Brien gold, Bashir blue, Dax teal, all in
one shot with no rig and no adapter. So the named cast comes from grids like these
and local SDXL fills the generic archetype and race-pool cells.

PANELS ARE FOUND, NOT ASSUMED. The layout looks like a 3x3 but is not: the
starship artwork pushes the right-hand column out of alignment and the gaps are
uneven, so slicing the image into equal thirds cuts heads in half. Instead the
panels are located by contour - each is a flat-coloured rectangle with a dark
border sitting on a starfield, which is about as findable as a shape gets - and
then filtered to the ones that are roughly square and roughly the same size as
each other. The starship, the title text and the background survive none of those
tests.

Panels come back in READING ORDER (top-to-bottom within left-to-right columns is
NOT what these use - it is row-major across the visual rows), and keys are
assigned in that order, so the caller passes the cast list as it reads on screen.

THE CUT PANEL IS THE FINISHED CELL. These land as opaque tiles - a bust on its own
flat backdrop - which is what the atlas wants, so nothing else is done to them. An
earlier version pushed them through the u2net matting stage as well and it was pure
loss: the background key failed on the panels whose backdrop is close to the subject
(Worf on green), u2net was used as a fallback and mis-cut him, and the result was
then composited back onto the very colour it started from. Damage, no benefit. Only
OVERLAY cells need matting, and those are generated, not cut from a grid.

RESOLUTION. A 3x3 grid on a ~1024 image gives ~130px panels against the 512 a cell
needs. That is the same upscale trap the current mod fell into, so this tool
reports the native panel size and refuses to pretend: use --upscale to run the
ESRGAN model through ComfyUI, or generate 2x2 grids instead. Flat cel art upscales
far better than photographs - hard edges and flat regions are what those models are
good at - but "better" is not "free", and the whole point of this rebuild was that
the last set was upscaled 2.67x.
"""
import argparse
import json
import os

import cv2
import numpy as np


def find_panels_lattice(img, min_side=90, square_tol=0.35):
    """Locate panels as cells of a LATTICE, for grids whose panels touch.

    The contour method below only works when every panel is an island in the
    starfield. Several of these sheets are tight mosaics instead - neighbouring
    panels share an edge - and Canny then merges a whole row into one blob that the
    size filter throws away (measured: 11 of 21 panels found on the DS9 expanded
    sheet).

    Panels are axis-aligned and separated by thin dark rules, so the rules show up as
    peaks when the edge map is projected onto each axis. Split on the peaks, then
    keep only the lattice cells that actually contain artwork: a panel has a flat,
    reasonably bright background, whereas the starfield is dark and speckled, and the
    title band is nearly black.
    """
    h, w = img.shape[:2]
    g = cv2.GaussianBlur(img, (3, 3), 0).astype(np.float32)

    # A separator is a line that runs the WHOLE way across, so score each candidate
    # by the FRACTION of rows (or columns) that change colour there - not by how many
    # edge pixels it has. Summing edge pixels counts a jawline and a panel border
    # alike, which over-split the DS9 sheet into 42 cells where there are 21.
    def frac_profile(arr, axis, thresh=26.0):
        d = np.abs(np.diff(arr, axis=axis)).max(axis=2)
        return (d > thresh).mean(axis=1 - axis)

    def seps(prof, n, min_gap, need=0.55):
        idx = [i for i, v in enumerate(prof) if v > need]
        if not idx:
            return [0, n]
        groups, cur = [], [idx[0]]
        for i in idx[1:]:
            if i - cur[-1] <= 4:
                cur.append(i)
            else:
                groups.append(int(np.mean(cur))); cur = [i]
        groups.append(int(np.mean(cur)))
        out = [0]
        for gx in groups:
            if gx - out[-1] >= min_gap:
                out.append(gx)
        if n - out[-1] >= min_gap:
            out.append(n)
        return out

    xs = seps(frac_profile(g, 1), w, min_side)
    ys = seps(frac_profile(g, 0), h, min_side)

    boxes = []
    for yi in range(len(ys) - 1):
        for xi in range(len(xs) - 1):
            x0, x1, y0, y1 = xs[xi], xs[xi + 1], ys[yi], ys[yi + 1]
            bw, bh = x1 - x0, y1 - y0
            if bw < min_side or bh < min_side:
                continue
            if abs(bw - bh) / float(max(bw, bh)) > square_tol:
                continue
            cell = img[y0:y1, x0:x1]
            inner = cell[int(bh*0.12):int(bh*0.88), int(bw*0.12):int(bw*0.88)]
            if inner.size == 0:
                continue
            hsv = cv2.cvtColor(inner, cv2.COLOR_BGR2HSV)
            v_mean = hsv[..., 2].mean()
            # Starfield: dark overall. Title band: dark and almost unsaturated.
            if v_mean < 55:
                continue
            boxes.append((x0, y0, bw, bh))
    return boxes


def find_panels(img, min_frac=0.02, max_frac=0.35, square_tol=0.28):
    """Locate the portrait panels. Returns boxes in reading order."""
    h, w = img.shape[:2]
    area = float(h * w)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # The panels have hard borders; Canny plus a dilate closes the corners so each
    # panel becomes one closed contour rather than four separate edges.
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 40, 140)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)
    cnts, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes = []
    for c in cnts:
        x, y, bw, bh = cv2.boundingRect(c)
        a = bw * bh / area
        if a < min_frac or a > max_frac:
            continue
        if abs(bw - bh) / float(max(bw, bh)) > square_tol:      # panels are square-ish
            continue
        boxes.append((x, y, bw, bh))
    if not boxes:
        return []

    # Keep only boxes close to the MEDIAN size: the title block and the starship
    # occasionally survive the shape test, but never the size test.
    med = np.median([b[2] * b[3] for b in boxes])
    boxes = [b for b in boxes if 0.45 * med <= b[2] * b[3] <= 2.0 * med]

    # De-duplicate nested contours (inner border vs outer border of one panel).
    boxes.sort(key=lambda b: -b[2] * b[3])
    kept = []
    for b in boxes:
        bx, by, bw, bh = b
        cx, cy = bx + bw / 2, by + bh / 2
        if any(abs(cx - (k[0] + k[2] / 2)) < k[2] * 0.5 and
               abs(cy - (k[1] + k[3] / 2)) < k[3] * 0.5 for k in kept):
            continue
        kept.append(b)

    # Reading order: group into rows by y, then sort each row by x.
    if not kept:
        return []
    hgt = np.median([b[3] for b in kept])
    kept.sort(key=lambda b: b[1])
    rows, cur = [], [kept[0]]
    for b in kept[1:]:
        if abs(b[1] - cur[-1][1]) <= hgt * 0.6:
            cur.append(b)
        else:
            rows.append(cur)
            cur = [b]
    rows.append(cur)
    out = []
    for r in rows:
        out.extend(sorted(r, key=lambda b: b[0]))
    return out


def complete_lattice(boxes, img, tol=0.45):
    """Add panels the detector missed because something overlaps them.

    On the cast grids the starship artwork crosses the right-hand column, breaking
    those panels' contours so they merge with the ship and get discarded - measured
    as 7 of 9 found, with Troi and Crusher missing every time. The panels are on a
    regular lattice though, so their positions can be inferred from the ones that
    WERE found and then confirmed by looking at the pixels.
    """
    if len(boxes) < 3:
        return boxes
    w = int(np.median([b[2] for b in boxes]))
    h = int(np.median([b[3] for b in boxes]))

    def axis_positions(vals, span):
        vals = sorted(vals)
        groups, cur = [], [vals[0]]
        for v in vals[1:]:
            if v - cur[-1] < span * tol:
                cur.append(v)
            else:
                groups.append(int(np.mean(cur))); cur = [v]
        groups.append(int(np.mean(cur)))
        return groups

    cols = axis_positions([b[0] for b in boxes], w)
    rows = axis_positions([b[1] for b in boxes], h)
    have = {(min(range(len(cols)), key=lambda i: abs(cols[i]-b[0])),
             min(range(len(rows)), key=lambda i: abs(rows[i]-b[1]))) for b in boxes}

    H, W = img.shape[:2]
    added = []
    for ci, x in enumerate(cols):
        for ri, y in enumerate(rows):
            if (ci, ri) in have:
                continue
            if x < 0 or y < 0 or x + w > W or y + h > H:
                continue
            inner = img[y + h//6: y + 5*h//6, x + w//6: x + 5*w//6]
            if inner.size == 0:
                continue
            hsv = cv2.cvtColor(inner, cv2.COLOR_BGR2HSV)
            # A panel is bright and fairly uniform; starfield is dark, and the
            # nebula is bright but wildly varied in hue.
            if hsv[..., 2].mean() < 60 or hsv[..., 0].std() > 55:
                continue
            added.append((x, y, w, h))
    if added:
        print("  lattice completion recovered %d overlapped panel(s)" % len(added))
    return boxes + added


def inset(box, frac=0.045):
    """Trim the panel border so the cell is artwork, not a dark frame line."""
    x, y, w, h = box
    dx, dy = int(w * frac), int(h * frac)
    return x + dx, y + dy, w - 2 * dx, h - 2 * dy


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("--keys", help="comma-separated cell keys in reading order")
    ap.add_argument("-o", "--out", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "out", "grid"))
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--preview", action="store_true",
                    help="write a marked-up copy showing what was detected")
    a = ap.parse_args()

    img = cv2.imread(a.image)
    if img is None:
        raise SystemExit("cannot read " + a.image)
    os.makedirs(a.out, exist_ok=True)

    boxes = find_panels_lattice(img)
    contour = find_panels(img)
    # Whichever finds more: isolated-panel sheets favour the contour method,
    # tight-mosaic sheets favour the lattice.
    if len(contour) > len(boxes):
        boxes = contour
        print("(contour detector)")
    else:
        print("(lattice detector)")
    boxes = complete_lattice(boxes, img)
    # re-sort into reading order after completion
    if boxes:
        hgt = np.median([b[3] for b in boxes])
        boxes.sort(key=lambda b: b[1])
        rws, cur = [], [boxes[0]]
        for b in boxes[1:]:
            if abs(b[1] - cur[-1][1]) <= hgt * 0.6:
                cur.append(b)
            else:
                rws.append(cur); cur = [b]
        rws.append(cur)
        boxes = [b for r in rws for b in sorted(r, key=lambda z: z[0])]
    print("%d panels found in %s (%dx%d)" % (len(boxes), os.path.basename(a.image),
                                             img.shape[1], img.shape[0]))
    if not boxes:
        raise SystemExit("no panels detected - run with --preview and check the image")

    native = int(np.median([b[2] for b in boxes]))
    print("native panel size ~%dpx  ->  cell is %dpx" % (native, a.size))
    if native < a.size:
        print("WARNING: upscaling %.2fx. The existing mod's softness came from a "
              "2.67x upscale; anything near that should be regenerated larger "
              "instead (2x2 grids give ~512 natively)." % (a.size / float(native)))

    keys = [k.strip() for k in a.keys.split(",")] if a.keys else []

    def to_square(cell):
        """PAD to square with the panel's own backdrop, never CROP to square.

        Panels are not exactly square (210x217 is typical), and centre-cropping to
        the short side quietly shaved up to 7px off the top of a head or the bottom
        of a shoulder. Padding with the corner colour keeps every pixel of the
        artwork and is invisible, because that colour IS the backdrop.
        """
        h, w = cell.shape[:2]
        if h == w:
            return cell
        side = max(h, w)
        k = max(3, min(h, w) // 20)
        bg = np.median(np.concatenate([cell[:k, :k].reshape(-1, 3),
                                       cell[:k, -k:].reshape(-1, 3),
                                       cell[-k:, :k].reshape(-1, 3),
                                       cell[-k:, -k:].reshape(-1, 3)]), axis=0)
        out = np.full((side, side, 3), bg, np.uint8)
        y0, x0 = (side - h) // 2, (side - w) // 2
        out[y0:y0 + h, x0:x0 + w] = cell
        return out
    written = {}
    for i, b in enumerate(boxes):
        x, y, w, h = inset(b)
        cell = to_square(img[y:y + h, x:x + w])
        cell = cv2.resize(cell, (a.size, a.size), interpolation=cv2.INTER_LANCZOS4)
        name = keys[i] if i < len(keys) else "panel_%02d" % (i + 1)
        dest = os.path.join(a.out, name + ".png")
        cv2.imwrite(dest, cell)
        written[name] = os.path.basename(dest)
        print("  %2d  %-18s %dx%d native" % (i + 1, name, b[2], b[3]))

    if a.preview:
        vis = img.copy()
        for i, b in enumerate(boxes):
            x, y, w, h = b
            cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(vis, str(i + 1), (x + 4, y + 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        p = os.path.join(a.out, "_preview.png")
        cv2.imwrite(p, vis)
        print("preview ->", p)

    with open(os.path.join(a.out, "index.json"), "w") as f:
        json.dump(written, f, indent=1, sort_keys=True)
    print("%d cells -> %s" % (len(written), a.out))


if __name__ == "__main__":
    main()
