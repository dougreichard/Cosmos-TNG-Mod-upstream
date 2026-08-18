"""Convert a foreign cubemap cross (space-3d, Spacescape, Blender, ...) into a Cosmos one.

WHY THIS EXISTS. tools.wwwtyro.net/space-3d generates exactly the look Cosmos ships -
`sky1.png` appears to have come from it - and it downloads a 4x3 cross. But a cross is not
a format, it is an UNFOLDING, and different tools unfold the cube differently. Cosmos puts
`up` in the centre of the middle row with `front` above it and `back` below; most tools put
`front` in the middle row with `up` above. Same six cells, different faces in them, and
several of them rotated. Drop a foreign cross in unconverted and it is wrong in a way that
looks almost right.

THE CONVENTION IS DETECTED, NOT ASSUMED, AND THE CHECK IS THE POINT. For each candidate
unfolding this resamples the input into Cosmos's own frames, then scores the RESULT by
sampling either side of all TWELVE cube edges and measuring colour discontinuity. The
winner is the one that is actually continuous.

That last detail is what makes this safe. VenusClouds-Mod/_gen_skybox.py records the trap:
fitting per-face rotations to minimise mismatch along the cross's INTERNAL borders scored
better than stock and still seamed in game, because a 4x3 cross exposes only five of the
cube's twelve edges and the fitted answer mirrored three faces, tearing the seven hidden
ones. Scoring all twelve on the assembled result cannot be fooled that way - a mirrored
face breaks edges the cross does not show, and those are exactly the ones measured here.

MEASURED 2026-08-18: SPACE-3D IS ALREADY IN COSMOS'S CONVENTION. A real download scored
1.72 as `cosmos` against 12.0 as `standard` - a seven-fold margin - and the same file
scored 2.71 on VenusClouds-Mod/_calibrate_cross.py's independent visible-border check,
against stock sky1.png at 1.01 and a scrambled face at 21. So a space-3d cross needs NO
conversion: rename it and drop it in. That is also decent evidence that sky1.png came from
that tool, since this unfolding is not the common one to match by accident.

This importer therefore earns its keep on OTHER tools - Spacescape and anything Blender
exports are likelier to be `standard` - and on proving, rather than hoping, that a given
download is right before it ships.

Usage:
    python import_cross.py --selftest
    python import_cross.py cubemap.png --install tng_border_run   # detect + drop in
    python import_cross.py in.png --out out.png
    python import_cross.py in.png --convention standard --out out.png   # skip detection
"""
import argparse
import os

import numpy as np
from PIL import Image

from gen_skybox_tng import CROSS_CELLS, CELL_FRAMES, _face_dirs


def _frames(d):
    """Normalise a frame table to float arrays and assert it is a real unfolding."""
    out = {}
    for k, (n, r, dn) in d.items():
        n, r, dn = (np.array(x, np.float64) for x in (n, r, dn))
        if not np.allclose(np.cross(r, dn), -n, atol=1e-9):
            raise AssertionError("convention face %r is mirrored (cross(r,d) != -n)" % k)
        out[k] = (n, r, dn)
    return out


# Cosmos's own unfolding - the target, and also a candidate in case the input is already
# in this convention.
COSMOS = {
    "cells": dict(CROSS_CELLS),
    "frames": _frames(CELL_FRAMES),
}

# The common horizontal cross: up above front, then left front right back across the
# middle, down below front. Derived, not fitted - every frame satisfies cross(r,d) == -n.
STANDARD = {
    "cells": {"up": (0, 1), "left": (1, 0), "front": (1, 1),
              "right": (1, 2), "back": (1, 3), "down": (2, 1)},
    "frames": _frames({
        "front": ((0, 0, -1), (1, 0, 0),  (0, 1, 0)),
        "left":  ((-1, 0, 0), (0, 0, -1), (0, 1, 0)),
        "right": ((1, 0, 0),  (0, 0, 1),  (0, 1, 0)),
        "back":  ((0, 0, 1),  (-1, 0, 0), (0, 1, 0)),
        "up":    ((0, 1, 0),  (1, 0, 0),  (0, 0, 1)),
        "down":  ((0, -1, 0), (1, 0, 0),  (0, 0, -1)),
    }),
}


def _yflip(conv):
    """Same unfolding with world Y negated - covers tools that treat Z as up. Negating one
    axis would mirror every face, so the right-vector is negated too, which restores
    handedness and leaves a genuine unfolding."""
    f = {}
    for k, (n, r, d) in conv["frames"].items():
        m = np.array([1.0, -1.0, 1.0])
        f[k] = (n * m, -(r * m), d * m)
    return {"cells": dict(conv["cells"]), "frames": _frames(f)}


CONVENTIONS = {
    "cosmos": COSMOS,
    "standard": STANDARD,
    "cosmos_yflip": _yflip(COSMOS),
    "standard_yflip": _yflip(STANDARD),
}


def _sample(img, conv, dirs):
    """Bilinearly sample a foreign cross for an array of directions.

    A direction belongs to the face whose frame gives |u|,|v| <= 1 with a positive
    component along the normal - the ordinary cubemap face test, written against the same
    frame representation the generator uses so there is only one idea here, not two.
    """
    h, w = img.shape[:2]
    fs = w // 4
    out = np.zeros(dirs.shape[:-1] + (3,), np.float32)
    filled = np.zeros(dirs.shape[:-1], bool)

    for face, (n, r, d) in conv["frames"].items():
        row, col = conv["cells"][face]
        dn = dirs @ n
        with np.errstate(divide="ignore", invalid="ignore"):
            u = (dirs @ r) / dn
            v = (dirs @ d) / dn
        hit = (dn > 1e-9) & (np.abs(u) <= 1.0 + 1e-6) & (np.abs(v) <= 1.0 + 1e-6) & (~filled)
        if not hit.any():
            continue
        # -1..1 -> pixel centres inside this cell
        px = (np.clip(u[hit], -1, 1) * 0.5 + 0.5) * (fs - 1) + col * fs
        py = (np.clip(v[hit], -1, 1) * 0.5 + 0.5) * (fs - 1) + row * fs
        x0 = np.floor(px).astype(np.int64); y0 = np.floor(py).astype(np.int64)
        x1 = np.clip(x0 + 1, 0, w - 1);     y1 = np.clip(y0 + 1, 0, h - 1)
        fx = (px - x0)[..., None];          fy = (py - y0)[..., None]
        x0 = np.clip(x0, 0, w - 1);         y0 = np.clip(y0, 0, h - 1)
        top = img[y0, x0] * (1 - fx) + img[y0, x1] * fx
        bot = img[y1, x0] * (1 - fx) + img[y1, x1] * fx
        out[hit] = top * (1 - fy) + bot * fy
        filled |= hit
    return out, filled


def convert(img, conv, face_size):
    """Resample a foreign cross into a Cosmos cross of the requested face size."""
    dst = np.zeros((face_size * 3, face_size * 4, 3), np.float32)
    for face, (row, col) in CROSS_CELLS.items():
        d = _face_dirs(face, face_size).astype(np.float64)
        px, _ = _sample(img, conv, d)
        dst[row * face_size:(row + 1) * face_size, col * face_size:(col + 1) * face_size] = px
    return dst


# The twelve cube edges, as the pair of faces meeting at each.
EDGES = [("up", "front"), ("up", "back"), ("up", "left"), ("up", "right"),
         ("down", "front"), ("down", "back"), ("down", "left"), ("down", "right"),
         ("front", "left"), ("front", "right"), ("back", "left"), ("back", "right")]


def edge_score(img, conv, samples=192, eps=6e-3):
    """Mean colour discontinuity across all TWELVE cube edges of the assembled result.

    For each edge, walk points along it and step a hair to either side - into each of the
    two faces - then compare what the convention returns. A correct unfolding is continuous
    everywhere; a wrong one tears, including on the seven edges a cross never shows.
    """
    total, n = 0.0, 0
    for fa, fb in EDGES:
        na, nb = conv["frames"][fa][0], conv["frames"][fb][0]
        # The edge direction is perpendicular to both face normals.
        axis = np.cross(na, nb)
        axis = axis / np.linalg.norm(axis)
        base = (na + nb)
        base = base / np.linalg.norm(base)
        t = np.linspace(-0.92, 0.92, samples)[:, None]
        along = base[None, :] + t * axis[None, :]
        along = along / np.linalg.norm(along, axis=-1, keepdims=True)
        a = along + eps * na[None, :]
        b = along + eps * nb[None, :]
        a = a / np.linalg.norm(a, axis=-1, keepdims=True)
        b = b / np.linalg.norm(b, axis=-1, keepdims=True)
        ca, oka = _sample(img, conv, a)
        cb, okb = _sample(img, conv, b)
        ok = oka & okb
        if ok.any():
            total += float(np.abs(ca[ok] - cb[ok]).mean())
            n += 1
    return total / max(1, n)


def detect(img):
    """Score every candidate convention; return (name, score, ranked list)."""
    ranked = sorted(((edge_score(img, c), k) for k, c in CONVENTIONS.items()))
    return ranked[0][1], ranked[0][0], ranked


def _selftest():
    """Round-trip a known-good Cosmos cross through a foreign unfolding and back.

    This is the honest check, and it needs no downloaded art: re-encode one of our own
    skies into STANDARD, hand it to the detector, and require both that it names STANDARD
    and that the recovered cross matches the original.
    """
    src_path = os.path.join(os.path.dirname(__file__), "..", "media", "skybox", "tng_delta.png")
    src = np.asarray(Image.open(src_path).convert("RGB"), np.float32)
    fs = src.shape[1] // 4
    small = fs // 4                      # quarter size keeps the self-test quick

    # Re-encode our sky into the STANDARD unfolding, i.e. fake a foreign download.
    foreign = np.zeros((small * 3, small * 4, 3), np.float32)
    for face, (row, col) in STANDARD["cells"].items():
        n, r, d = STANDARD["frames"][face]
        t = (np.arange(small) + 0.5) / small * 2.0 - 1.0
        u, v = np.meshgrid(t, t)
        vec = n[None, None, :] + u[..., None] * r[None, None, :] + v[..., None] * d[None, None, :]
        vec = vec / np.linalg.norm(vec, axis=-1, keepdims=True)
        px, _ = _sample(src, COSMOS, vec)
        foreign[row * small:(row + 1) * small, col * small:(col + 1) * small] = px

    name, score, ranked = detect(foreign)
    print("  detected: %-16s score %.3f" % (name, score))
    for s, k in ranked:
        print("      %-16s %.3f" % (k, s))
    ok_name = (name == "standard")

    back = convert(foreign, STANDARD, small)
    ref = convert(src, COSMOS, small)
    err = float(np.abs(back - ref).mean())
    print("  round-trip mean abs error: %.2f / 255" % err)

    # Resampling twice through bilinear costs a little sharpness on a starfield, so this
    # is a "recovered the same sky" threshold, not a bit-exactness one.
    ok_err = err < 6.0
    print("  %s" % ("PASS" if (ok_name and ok_err) else "FAIL"))
    return 0 if (ok_name and ok_err) else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", nargs="?", help="foreign 4x3 cross PNG")
    ap.add_argument("--out")
    ap.add_argument("--convention", choices=sorted(CONVENTIONS), help="skip detection")
    ap.add_argument("--size", type=int, help="output face size (default: same as input)")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--install", metavar="NAME",
                    help="write straight into ../media/skybox/NAME.png and print its label")
    a = ap.parse_args()

    if a.selftest:
        raise SystemExit(_selftest())
    if not a.src:
        ap.error("need a source cross, or --selftest")

    img = np.asarray(Image.open(a.src).convert("RGB"), np.float32)
    if img.shape[1] // 4 != img.shape[0] // 3:
        raise SystemExit("not a 4x3 cross: %dx%d" % (img.shape[1], img.shape[0]))

    if a.convention:
        name, score = a.convention, edge_score(img, CONVENTIONS[a.convention])
        print("convention: %s (forced)  edge score %.3f" % (name, score))
    else:
        name, score, ranked = detect(img)
        print("convention: %s  edge score %.3f" % (name, score))
        for s, k in ranked:
            print("    %-16s %.3f" % (k, s))
        runner = ranked[1][0] if len(ranked) > 1 else float("inf")
        if runner < score * 1.35:
            print("  WARNING: the runner-up is close. Eyeball the result before shipping it.")

    fs = a.size or (img.shape[1] // 4)
    if name == "cosmos" and not a.size:
        # Already Cosmos's unfolding - which is what space-3d downloads. Resampling would
        # only cost a generation of bilinear softness on a starfield for no gain, so the
        # pixels are passed through untouched and only the mode is normalised.
        out = img
        print("  (already Cosmos - passing pixels through, no resample)")
    else:
        out = convert(img, CONVENTIONS[name], fs)

    dest = a.out or (os.path.splitext(a.src)[0] + "_cosmos.png")
    if a.install:
        dest = os.path.join(os.path.dirname(__file__), "..", "media", "skybox", a.install + ".png")
    Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB").save(
        dest, optimize=True, compress_level=9)
    print("wrote %s  %dx%d  %.1f MB" % (
        os.path.abspath(dest), out.shape[1], out.shape[0], os.path.getsize(dest) / 1e6))
    if a.install:
        print()
        print("Add to tng_races/tng_media.mast, then rebuild the pack:")
        print('    @media/skybox/%s "%s"' % (a.install, a.install.replace("_", " ").strip().title()))
        print("    python ../../sbs.pyz lib Cosmos-TNG-Mod")


if __name__ == "__main__":
    main()
