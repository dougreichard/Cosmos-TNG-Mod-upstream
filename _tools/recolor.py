"""Remap a cell's uniform to an exact division colour, after generation.

WHY THIS EXISTS. Getting SDXL to honour "crimson red uniform" turned out to be the
single most stubborn thing in this pipeline. Both IPAdapters donate palette as well
as their intended signal, so whatever the references happen to be coloured, the
cells come out: a gold reference made every uniform gold, a Klingon-heavy style
reference made every uniform purple, a greyscale reference made everything grey.
Style weight trades against colour adherence, and the text prompt is the weakest
signal in the stack.

So stop asking. TAS style IS flat colour fill - that is the whole look - which
means the uniform is a small number of large flat regions and can simply be
reassigned afterwards. Deterministic, exact, reviewable, and it turns the style's
defining property into the thing that makes the fix easy.

VALUE IS PRESERVED, HUE AND SATURATION ARE REPLACED. Cel shading is one base tone
plus a darker shadow tone of the same colour; keeping V and rewriting H/S keeps that
two-tone structure intact, so a recoloured uniform still reads as drawn rather than
as a flat sticker. Replacing RGB outright would flatten the shadow and lose it.

WHAT IS PROTECTED. Skin, hair, the black collar/undershirt and the white/grey trim
are excluded by hue and value windows, because they must not follow the division
colour - and a Bolian's blue face or an Orion's green one would otherwise be read as
uniform and repainted.
"""
import argparse
import colorsys
import json
import os

import numpy as np
from PIL import Image

# Division colours, per era. TOS flips: command gold, sciences blue, ops red. TNG S3+
# and later: command red, ops/security gold, sciences/medical teal.
DIVISION = {
    "tos": {"command": "#c8a020", "science": "#4a7fbf", "medical": "#4a7fbf",
            "ops": "#a8302c"},
    "tng": {"command": "#8f1f2b", "science": "#1f6f78", "medical": "#1f6f78",
            "ops": "#b8912a"},
    "ds9": {"command": "#8f1f2b", "science": "#1f6f78", "medical": "#1f6f78",
            "ops": "#b8912a"},
    "voy": {"command": "#8f1f2b", "science": "#1f6f78", "medical": "#1f6f78",
            "ops": "#b8912a"},
}

SKIN_H = (0.02, 0.13)      # hue band that covers human through Ferengi orange-brown
DARK_V = 0.20              # black collar, outlines, pupils
LIGHT_S = 0.12             # white/grey trim and hair highlights


def _hsv(arr):
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    mx, mn = arr[..., :3].max(-1), arr[..., :3].min(-1)
    d = mx - mn
    h = np.zeros_like(mx)
    m = d > 1e-6
    rm, gm, bm = (mx == r) & m, (mx == g) & m, (mx == b) & m
    h[rm] = ((g - b)[rm] / d[rm]) % 6
    h[gm] = ((b - r)[gm] / d[gm]) + 2
    h[bm] = ((r - g)[bm] / d[bm]) + 4
    h = h / 6.0
    s = np.where(mx > 1e-6, d / np.maximum(mx, 1e-6), 0)
    return h, s, mx


def uniform_mask(rgb, alpha, body_from=0.52):
    """Boolean mask of the uniform: the big saturated region low in the cell.

    Anchored on the LOWER part of the bust because that is where the uniform always
    is - the rig guarantees it - and then grown across the whole cell by hue, so
    shoulders and sleeves that reach higher come along too.
    """
    h, s, v = _hsv(rgb)
    solid = alpha > 0.5
    body = np.zeros_like(solid)
    body[int(body_from * rgb.shape[0]):, :] = True

    candidate = (solid & body & (v > DARK_V) & (s > LIGHT_S) &
                 ~((h > SKIN_H[0]) & (h < SKIN_H[1]) & (s < 0.55)))
    if candidate.sum() < 200:
        return np.zeros_like(solid), None

    # Dominant hue among candidates, on the circle so red near 0/1 does not split.
    hh = h[candidate] * 2 * np.pi
    dom = (np.arctan2(np.sin(hh).mean(), np.cos(hh).mean()) / (2 * np.pi)) % 1.0
    dist = np.minimum(np.abs(h - dom), 1 - np.abs(h - dom))
    grown = (solid & (dist < 0.09) & (v > DARK_V) & (s > LIGHT_S) &
             ~((h > SKIN_H[0]) & (h < SKIN_H[1]) & (s < 0.55)))
    return grown, dom


def recolor(img, target_hex, body_from=0.52):
    """Return a copy with the uniform remapped to target_hex."""
    rgba = np.asarray(img.convert("RGBA"), np.float32) / 255.0
    rgb, alpha = rgba[..., :3], rgba[..., 3]
    mask, dom = uniform_mask(rgb, alpha, body_from)
    if dom is None:
        return img, 0.0

    th, ts, tv = colorsys.rgb_to_hsv(*[int(target_hex[i:i + 2], 16) / 255.0
                                       for i in (1, 3, 5)])
    h, s, v = _hsv(rgb)
    # Keep V (the cel shading) but rescale it around the target's value, so a light
    # target does not come out as dark as the tone it replaced.
    src_mean = v[mask].mean() if mask.any() else tv
    nv = np.clip(v + (tv - src_mean), 0.04, 1.0)
    ns = np.clip(s * (ts / max(s[mask].mean(), 1e-3)), 0, 1)

    out = rgb.copy()
    idx = np.nonzero(mask)
    for y, x in zip(*idx):
        out[y, x] = colorsys.hsv_to_rgb(th, float(ns[y, x]), float(nv[y, x]))
    res = np.dstack([np.clip(out, 0, 1), alpha])
    return Image.fromarray((res * 255).astype(np.uint8), "RGBA"), mask.mean()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", help="a cell png, or a directory of them")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--roster", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "face_roster.json"))
    ap.add_argument("--color", help="explicit target hex, overrides the roster lookup")
    a = ap.parse_args()

    cells = {c["key"]: c for c in json.load(open(a.roster))["cells"]}
    files = ([a.src] if a.src.lower().endswith(".png")
             else [os.path.join(a.src, f) for f in sorted(os.listdir(a.src))
                   if f.endswith(".png")])
    os.makedirs(a.out, exist_ok=True)

    for f in files:
        key = os.path.splitext(os.path.basename(f))[0].split("_c")[0]
        c = cells.get(key)
        target = a.color
        if not target and c:
            # Only Starfleet cells have a division colour; a Klingon or a civilian
            # wears their own clothes and must be left alone.
            if c.get("role") in ("command", "ops", "science", "medical") and \
                    c.get("era") in DIVISION and c.get("race") not in ("breen",):
                target = DIVISION[c["era"]].get(c["role"])
        if not target:
            print("%-24s skipped (no division colour)" % key)
            continue
        img, frac = recolor(Image.open(f), target)
        img.save(os.path.join(a.out, os.path.basename(f)))
        print("%-24s -> %s  (%.0f%% of the cell)" % (key, target, frac * 100))


if __name__ == "__main__":
    main()
