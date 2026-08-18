"""PROTOTYPE: can layered face PARTS be extracted from whole-bust panels?

The stock races ship layered sheets - separate eyes, mouth and hair cells that
register against a common head - which is what makes their character builder
possible. Our cells are complete busts, so a builder needs parts we do not have.

The idea under test: ask for the SAME character with one feature changed, then
recover the part by differencing the variants. Your Picard variant sheet is exactly
that shape, so the technique can be tried on art that already exists.

THE OBSTACLE, MEASURED FIRST. The panels are hand-composed, so the head lands in a
different place and at a different size in each one. Across the 19 Picard variants
with a detectable face:

    face centre X   std 13.2 px, spread 47 px
    face centre Y   std 10.4 px, spread 36 px
    face width      std 24.3 px, spread 88 px

A part has to land within about 2-3px on a 512 cell to look attached rather than
pasted, so differencing the panels as they are cannot work. Everything here rests
on whether an alignment pass can close a 47px gap to under 3px.

ALIGNMENT USES THE EYES, NOT THE FACE BOX. A Haar face box is jittery by several
pixels and gives only position and scale. Two eye centres give position, scale AND
roll from a similarity transform, and eyes are the feature a viewer actually checks
for registration - a hairline that is two pixels out reads as fine, eyes that are
two pixels out read as broken.

Run:
    python partextract.py --keys picard,picard_alt,tng_command_12 --out out/parts
"""
import argparse
import glob
import json
import os

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SIZE = 512
# Where the eyes should sit in a canonical cell. Taken from the measured mean of the
# variant set, so aligning moves panels the shortest distance rather than to an
# arbitrary target.
CANON_L = (0.385, 0.415)
CANON_R = (0.615, 0.415)


def eyes(img):
    """(left, right) eye centres, or None. Searched inside the detected face box so
    a background highlight cannot pose as an eye."""
    from crop_refs import detect
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    box, _ = detect(gray)
    if box is None:
        return None
    x, y, w, h = box
    roi = gray[y:y + int(h * 0.6), x:x + w]
    cas = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades,
                                             "haarcascade_eye.xml"))
    found = cas.detectMultiScale(roi, 1.05, 4, minSize=(int(w * 0.08), int(w * 0.08)))
    if len(found) < 2:
        return None
    found = sorted(found, key=lambda r: -r[2] * r[3])[:2]
    pts = sorted([(x + ex + ew / 2.0, y + ey + eh / 2.0) for ex, ey, ew, eh in found])
    return pts[0], pts[1]


def align(img, size=SIZE):
    """Warp so the eyes land on the canonical points. None if eyes were not found."""
    e = eyes(img)
    if e is None:
        return None
    src = np.float32([e[0], e[1]])
    dst = np.float32([(CANON_L[0] * size, CANON_L[1] * size),
                      (CANON_R[0] * size, CANON_R[1] * size)])
    # Similarity from two point pairs: scale+rotation+translation, no shear - a
    # sheared face would register at the eyes and be wrong everywhere else.
    (sx, sy), (dx, dy) = src, dst
    v_src = src[1] - src[0]
    v_dst = dst[1] - dst[0]
    scale = np.linalg.norm(v_dst) / max(np.linalg.norm(v_src), 1e-6)
    ang = np.arctan2(v_dst[1], v_dst[0]) - np.arctan2(v_src[1], v_src[0])
    ca, sa = np.cos(ang) * scale, np.sin(ang) * scale
    M = np.float32([[ca, -sa, 0], [sa, ca, 0]])
    centred = M[:, :2] @ src[0]
    M[0, 2] = dst[0][0] - centred[0]
    M[1, 2] = dst[0][1] - centred[1]
    return cv2.warpAffine(img, M, (size, size), flags=cv2.INTER_LANCZOS4,
                          borderMode=cv2.BORDER_REPLICATE)


def residual(a, b):
    """How far apart two aligned panels' eyes still are, in pixels."""
    ea, eb = eyes(a), eyes(b)
    if ea is None or eb is None:
        return None
    return max(np.linalg.norm(np.float32(ea[i]) - np.float32(eb[i])) for i in (0, 1))


def diff_part(base, variant, thresh=26, min_blob=180):
    """The region where `variant` differs from `base` - the candidate part layer."""
    d = np.abs(base.astype(np.int16) - variant.astype(np.int16)).max(axis=2)
    m = (d > thresh).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    keep = np.zeros_like(m)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= min_blob:
            keep[lab == i] = 1
    rgba = np.dstack([variant, (keep * 255).astype(np.uint8)])
    return rgba, float(keep.mean())


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cells", default=os.path.join(HERE, "out", "cells_named"))
    ap.add_argument("--keys", help="comma-separated; first is the BASE")
    ap.add_argument("-o", "--out", default=os.path.join(HERE, "out", "parts"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    keys = [k.strip() for k in a.keys.split(",")]
    imgs, failed = {}, []
    for k in keys:
        p = os.path.join(a.cells, k + ".png")
        img = cv2.imread(p)
        if img is None:
            failed.append((k, "no file"))
            continue
        w = align(img)
        if w is None:
            failed.append((k, "eyes not found"))
            continue
        imgs[k] = w
        cv2.imwrite(os.path.join(a.out, "aligned_" + k + ".png"), w)

    print("aligned %d of %d" % (len(imgs), len(keys)))
    for k, why in failed:
        print("   FAILED %-20s %s" % (k, why))
    if len(imgs) < 2:
        print("\nnot enough aligned panels to difference")
        return

    base_key = keys[0] if keys[0] in imgs else list(imgs)[0]
    base = imgs[base_key]
    print("\nbase: %s" % base_key)
    print("%-22s %-14s %s" % ("variant", "eye residual", "part area"))
    for k, im in imgs.items():
        if k == base_key:
            continue
        r = residual(base, im)
        rgba, area = diff_part(base, im)
        cv2.imwrite(os.path.join(a.out, "part_%s.png" % k), rgba)
        verdict = "" if (r is not None and r <= 3) else "   <-- too far to register"
        print("%-22s %-14s %5.1f%%%s"
              % (k, ("%.1f px" % r) if r is not None else "n/a", area * 100, verdict))


if __name__ == "__main__":
    main()
