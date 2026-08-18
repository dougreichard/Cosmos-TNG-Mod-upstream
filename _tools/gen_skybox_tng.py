"""Generate the TNG skyboxes as Cosmos 4x3 cross PNGs.

WHAT IS BORROWED AND WHAT IS NEW. The cube geometry here - CROSS_CELLS, CELL_FRAMES,
_face_dirs, build_cross, and the noise kit - is copied from VenusClouds-Mod/_gen_skybox.py
because it is SOLVED, and re-deriving it is how the seams come back. That file's docstring
records two regenerations lost to exactly that. What is new is `shade()`: Venus is a banded
cloud sea with an altitude ramp that tells the player which way is down, and none of that
means anything in open space.

WHY PROCEDURAL AND NOT GENERATIVE, restated because it keeps coming up. A skybox must be
seamless across all twelve cube edges and both poles. A diffusion model does not know the
cube exists; six independently generated faces join visibly on every edge, which is the one
defect nobody can unsee once the ship turns. Here every pixel is a pure function of its 3D
direction, so two faces sharing an edge sample the same directions and produce the same
pixels. Continuity is not repaired afterwards - it cannot fail.

THE LOOK IS DELIBERATELY SPARSE. Real TNG space is close to black: a fine, cold starfield,
and at most a faint wash of colour somewhere off-axis. The temptation with a nebula
generator is to fill the sky, and a filled sky reads as a 90s screensaver, drowns the ship
models, and makes every trial look the same. So `neb_amp` is low everywhere, the nebula is
MASKED to one region of sky rather than spread evenly, and the default variant has almost
none at all. If a sky looks impressive on its own it is probably too loud to fly in.

GEOMETRY IS ASSERTED AT IMPORT, not trusted. `_assert_geometry()` checks the handedness
invariant per face and walks all twelve cube edges numerically. The 4x3 cross only exposes
five of those twelve, so a border-comparison score cannot catch a mirrored face - that is
the trap the Venus module documents, and this is the check that closes it.

Usage:
    python gen_skybox_tng.py --list
    python gen_skybox_tng.py --only tng_deep --size 256 --equirect   # fast look
    python gen_skybox_tng.py --size 1024 --out ../media/skybox       # ship it
"""
import argparse
import math
import os

import numpy as np
from PIL import Image

# ---------------------------------------------------------------- geometry ----
# Copied from VenusClouds-Mod/_gen_skybox.py. Measured against a sky known to work in
# Cosmos; do not "improve" without re-running the twelve-edge check below.
CROSS_CELLS = {
    "front": (0, 1),
    "left":  (1, 0),
    "up":    (1, 1),
    "right": (1, 2),
    "down":  (1, 3),
    "back":  (2, 1),
}

# (normal, image-right, image-down). A pixel at (u, v) in -1..1 looks along n + u*r + v*d.
# Every frame satisfies cross(r, d) == -n; break that on one face and it mirrors, and the
# seven edges the cross does not expose will tear.
CELL_FRAMES = {
    "up":    ((0, 1, 0),  (1, 0, 0),  (0, 0, 1)),
    "front": ((0, 0, -1), (1, 0, 0),  (0, 1, 0)),
    "left":  ((-1, 0, 0), (0, 1, 0),  (0, 0, 1)),
    "right": ((1, 0, 0),  (0, -1, 0), (0, 0, 1)),
    "back":  ((0, 0, 1),  (1, 0, 0),  (0, -1, 0)),
    "down":  ((0, -1, 0), (-1, 0, 0), (0, 0, 1)),
}


def _assert_geometry():
    """Handedness per face, then all twelve cube edges. Cheap; runs at import."""
    for face, (n, r, d) in CELL_FRAMES.items():
        n, r, d = (np.array(x, np.float64) for x in (n, r, d))
        if not np.allclose(np.cross(r, d), -n, atol=1e-9):
            raise AssertionError("face %r is mirrored: cross(r,d) != -n" % face)

    # Walk each face's four boundaries. Every boundary direction must also be produced by
    # exactly one other face, which is what makes an edge continuous.
    def dirs_on_edge(face, which, ts):
        n, r, d = (np.array(x, np.float64) for x in CELL_FRAMES[face])
        out = []
        for t in ts:
            u, v = {"l": (-1.0, t), "r": (1.0, t), "t": (t, -1.0), "b": (t, 1.0)}[which]
            vec = n + u * r + v * d
            out.append(vec / np.linalg.norm(vec))
        return np.array(out)

    ts = np.linspace(-1.0, 1.0, 33)
    faces = list(CELL_FRAMES)
    matched = 0
    for f in faces:
        for w in ("l", "r", "t", "b"):
            a = dirs_on_edge(f, w, ts)
            hit = False
            for g in faces:
                if g == f:
                    continue
                for w2 in ("l", "r", "t", "b"):
                    b = dirs_on_edge(g, w2, ts)
                    if np.allclose(a, b, atol=1e-9) or np.allclose(a, b[::-1], atol=1e-9):
                        hit = True
            if hit:
                matched += 1
    if matched != 24:
        raise AssertionError("only %d of 24 face boundaries pair up - the unfolding is wrong" % matched)


_assert_geometry()


# ---------------------------------------------------------------- noise ----
def _hash3(ix, iy, iz, seed):
    n = (ix * 374761393 + iy * 668265263 + iz * 2147483647 + seed * 971) & 0xFFFFFFFF
    n = (n ^ (n >> 13)) * 1274126177 & 0xFFFFFFFF
    return (n & 0xFFFFFF).astype(np.float32) / float(0xFFFFFF)


def _value_noise(p, seed):
    """Trilinear value noise. p is (..., 3) in lattice units."""
    i = np.floor(p).astype(np.int64)
    f = (p - i).astype(np.float32)
    f = f * f * (3.0 - 2.0 * f)
    ix, iy, iz = i[..., 0], i[..., 1], i[..., 2]
    fx, fy, fz = f[..., 0], f[..., 1], f[..., 2]

    def h(dx, dy, dz):
        return _hash3(ix + dx, iy + dy, iz + dz, seed)

    x00 = h(0, 0, 0) + (h(1, 0, 0) - h(0, 0, 0)) * fx
    x10 = h(0, 1, 0) + (h(1, 1, 0) - h(0, 1, 0)) * fx
    x01 = h(0, 0, 1) + (h(1, 0, 1) - h(0, 0, 1)) * fx
    x11 = h(0, 1, 1) + (h(1, 1, 1) - h(0, 1, 1)) * fx
    y0 = x00 + (x10 - x00) * fy
    y1 = x01 + (x11 - x01) * fy
    return y0 + (y1 - y0) * fz


def _fbm(p, seed, octaves=5, lacunarity=2.0, gain=0.5):
    total = np.zeros(p.shape[:-1], np.float32)
    amp, freq, norm = 1.0, 1.0, 0.0
    for o in range(octaves):
        total += amp * _value_noise(p * freq, seed + o * 17)
        norm += amp
        amp *= gain
        freq *= lacunarity
    return total / norm


def _smoothstep(a, b, x):
    t = np.clip((x - a) / max(1e-6, (b - a)), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _face_dirs(face, size):
    n, r, d = (np.array(x, np.float32) for x in CELL_FRAMES[face])
    t = (np.arange(size, dtype=np.float32) + 0.5) / size * 2.0 - 1.0
    u, v = np.meshgrid(t, t)
    vec = n + u[..., None] * r + v[..., None] * d
    return vec / np.linalg.norm(vec, axis=-1, keepdims=True)


# ---------------------------------------------------------------- shading ----
def _stars(d, seed, scale, thresh, gain, warm):
    """One layer of stars: thresholded high-frequency noise.

    Stars are points, so the layer is a hard smoothstep near the top of the noise range -
    a gentle threshold gives fuzzy blobs that read as dirt on the lens. `warm` biases the
    layer's colour temperature; a field of identically white stars looks printed.
    """
    n = _value_noise(d * scale, seed)
    s = _smoothstep(thresh, 1.0, n) ** 2.0 * gain
    # A second, decorrelated field decides each star's colour temperature.
    t = _value_noise(d * scale + 91.7, seed + 313)
    r = 0.78 + 0.30 * t
    g = 0.86 + 0.12 * np.abs(t - 0.5)
    b = 1.06 - 0.34 * t
    rgb = np.stack([r, g, b], -1).astype(np.float32)
    rgb = rgb * (1.0 - warm) + np.stack([r * 1.12, g, b * 0.80], -1) * warm
    return s[..., None] * rgb


def shade(d, p):
    """RGB uint8 for an array of unit directions. Pure function of direction."""
    out = np.zeros(d.shape[:-1] + (3,), np.float32)

    # 1. Ground. Space is not pure black on a screen - a hair of tint keeps the ship from
    #    looking like it is cut out of the sky.
    out += np.array(p["base"], np.float32)

    # 2. The galactic band: a soft great circle, mottled so it is not an airbrushed stripe.
    if p["band_amp"] > 0:
        axis = np.array(p["band_axis"], np.float32)
        axis = axis / np.linalg.norm(axis)
        c = np.abs(np.sum(d * axis, -1))
        band = np.exp(-(c * c) / max(1e-6, 2.0 * p["band_width"] ** 2))
        mottle = 0.55 + 0.45 * _fbm(d * p["band_grain"], p["seed"] + 41, octaves=4)
        v = (band * mottle * p["band_amp"])[..., None]
        out += v * np.array(p["band_color"], np.float32)

    # 3. Nebula. Domain-warped fBm, then MASKED by a large-scale field so the colour lives
    #    in one part of the sky instead of fogging all of it.
    if p["neb_amp"] > 0:
        warp = _fbm(d * p["neb_warp_scale"], p["seed"] + 7, octaves=3)[..., None]
        q = d * p["neb_scale"] + warp * p["neb_warp"]
        n = _fbm(q, p["seed"] + 13, octaves=6)
        mask = _smoothstep(p["neb_mask_lo"], p["neb_mask_hi"],
                           _fbm(d * p["neb_mask_scale"], p["seed"] + 29, octaves=3))
        amt = np.clip((n - p["neb_floor"]) / max(1e-6, 1.0 - p["neb_floor"]), 0, 1) * mask
        amt = amt ** p["neb_gamma"]
        a = amt[..., None]
        col = (np.array(p["neb_lo"], np.float32) * (1.0 - a)
               + np.array(p["neb_hi"], np.float32) * a)
        out += a * col * p["neb_amp"]

    # 4. Stars, three layers: a few bright ones, a working field, and fine grain.
    out += _stars(d, p["seed"] + 101, p["star_big_scale"], p["star_big_thresh"],
                  p["star_big_gain"], p["star_warm"])
    out += _stars(d, p["seed"] + 211, p["star_mid_scale"], p["star_mid_thresh"],
                  p["star_mid_gain"], p["star_warm"])
    out += _stars(d, p["seed"] + 337, p["star_fine_scale"], p["star_fine_thresh"],
                  p["star_fine_gain"], p["star_warm"])

    # 5. A distant sun, if this sky has one. Not a lens flare - just a soft presence.
    if p["sun_amp"] > 0:
        sd = np.array(p["sun_dir"], np.float32)
        sd = sd / np.linalg.norm(sd)
        c = np.clip(np.sum(d * sd, -1), 0, 1)
        glow = c ** p["sun_tight"]
        core = c ** (p["sun_tight"] * 26.0)
        v = ((glow * 0.5 + core) * p["sun_amp"])[..., None]
        out += v * np.array(p["sun_color"], np.float32)

    return np.clip(out * 255.0, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------- build ----
def build_cross(p, face_size):
    img = np.zeros((face_size * 3, face_size * 4, 3), dtype=np.uint8)
    for face, (r, c) in CROSS_CELLS.items():
        img[r * face_size:(r + 1) * face_size, c * face_size:(c + 1) * face_size] = \
            shade(_face_dirs(face, face_size), p)
    return Image.fromarray(img, "RGB")


def build_equirect(p, width=1024):
    """Flat panorama. The fastest way to judge a sky without opening the game."""
    h = width // 2
    lon = (np.arange(width, dtype=np.float32) + 0.5) / width * 2.0 * math.pi - math.pi
    lat = math.pi / 2.0 - (np.arange(h, dtype=np.float32) + 0.5) / h * math.pi
    lo, la = np.meshgrid(lon, lat)
    d = np.stack([np.cos(la) * np.sin(lo), np.sin(la), -np.cos(la) * np.cos(lo)], -1)
    return Image.fromarray(shade(d.astype(np.float32), p), "RGB")


# ---------------------------------------------------------------- variants ----
DEFAULTS = dict(
    seed=1,
    base=(0.012, 0.014, 0.021),
    band_axis=(0.2, 1.0, 0.35), band_width=0.30, band_amp=0.10,
    band_color=(0.42, 0.48, 0.62), band_grain=6.0,
    neb_scale=2.1, neb_warp=0.55, neb_warp_scale=1.1,
    neb_mask_scale=0.85, neb_mask_lo=0.50, neb_mask_hi=0.78,
    neb_floor=0.42, neb_gamma=1.6, neb_amp=0.55,
    neb_lo=(0.10, 0.14, 0.30), neb_hi=(0.35, 0.45, 0.75),
    # Thresholds set the DENSITY of each layer and gains the brightness. The first pass
    # here was far too tight - a sky can be sparse and still need to look populated, and
    # at 0.97 the field read as unfinished rather than restrained.
    star_big_scale=150.0, star_big_thresh=0.940, star_big_gain=1.45,
    star_mid_scale=360.0, star_mid_thresh=0.925, star_mid_gain=0.85,
    star_fine_scale=780.0, star_fine_thresh=0.912, star_fine_gain=0.42,
    star_warm=0.25,
    sun_dir=(1.0, 0.2, -0.4), sun_tight=90.0, sun_amp=0.0,
    sun_color=(1.0, 0.95, 0.85),
)


def _v(**kw):
    p = dict(DEFAULTS)
    p.update(kw)
    return p


# Display names are what the operator's picker shows. Keys are the label paths.
VARIANTS = {
    # The house sky. Almost nothing but stars - this is what TNG actually looks like, and
    # it is the one that should come up most often.
    "tng_deep": ("TNG Deep Space", _v(
        seed=11, neb_amp=0.16, band_amp=0.07,
        neb_lo=(0.06, 0.09, 0.20), neb_hi=(0.16, 0.22, 0.42),
        neb_mask_lo=0.62, neb_mask_hi=0.86,
    )),

    # Klingon border. Cold iron with a low red wash - used for the Kobayashi Maru and the
    # war timeline of Yesterday's Enterprise.
    "tng_klingon_border": ("Klingon Border", _v(
        seed=23, base=(0.017, 0.011, 0.012),
        band_axis=(0.4, 1.0, -0.2), band_amp=0.09, band_color=(0.50, 0.36, 0.34),
        neb_amp=0.50, neb_scale=1.8, neb_gamma=1.8,
        neb_lo=(0.20, 0.05, 0.05), neb_hi=(0.62, 0.20, 0.14),
        neb_mask_lo=0.54, neb_mask_hi=0.80,
        star_warm=0.55,
    )),

    # The Bajoran system: warm gold off one shoulder, the Denorios belt feel, a real sun.
    "tng_bajor": ("Bajoran System", _v(
        seed=37, base=(0.014, 0.014, 0.019),
        band_axis=(-0.3, 1.0, 0.5), band_amp=0.11, band_color=(0.52, 0.46, 0.40),
        neb_amp=0.44, neb_scale=1.6,
        neb_lo=(0.24, 0.14, 0.05), neb_hi=(0.66, 0.44, 0.16),
        neb_mask_lo=0.52, neb_mask_hi=0.78,
        sun_amp=0.55, sun_dir=(-0.6, 0.25, 0.5), sun_tight=70.0,
        sun_color=(1.0, 0.90, 0.72),
        star_warm=0.40,
    )),

    # Romulan side of the line. Cold, green-blue, and emptier than anywhere else - the sky
    # for a trial about not being able to see what is out there.
    "tng_neutral_zone": ("Romulan Neutral Zone", _v(
        seed=53, base=(0.010, 0.015, 0.016),
        band_axis=(0.1, 1.0, 0.7), band_amp=0.06, band_color=(0.33, 0.50, 0.46),
        neb_amp=0.26, neb_scale=1.4, neb_gamma=2.1,
        neb_lo=(0.05, 0.16, 0.13), neb_hi=(0.14, 0.42, 0.34),
        neb_mask_lo=0.60, neb_mask_hi=0.88,
        star_big_gain=0.95, star_warm=0.10,
    )),

    # Delta Quadrant. Busier and stranger - nobody here has seen a Federation uniform.
    "tng_delta": ("Delta Quadrant", _v(
        seed=71, base=(0.012, 0.017, 0.018),
        band_axis=(0.8, 1.0, 0.1), band_amp=0.13, band_color=(0.36, 0.54, 0.50),
        neb_amp=0.72, neb_scale=2.6, neb_warp=0.75, neb_gamma=1.4,
        neb_lo=(0.06, 0.22, 0.20), neb_hi=(0.30, 0.66, 0.52),
        neb_mask_lo=0.44, neb_mask_hi=0.72,
        star_warm=0.20,
    )),

    # Wolf 359. Steel blue, a cold distant sun, and nothing warm anywhere in it.
    "tng_wolf359": ("Wolf 359", _v(
        seed=97, base=(0.011, 0.013, 0.020),
        band_axis=(-0.5, 1.0, -0.3), band_amp=0.08, band_color=(0.34, 0.42, 0.60),
        neb_amp=0.22, neb_scale=1.9, neb_gamma=2.2,
        neb_lo=(0.05, 0.08, 0.18), neb_hi=(0.14, 0.20, 0.40),
        neb_mask_lo=0.62, neb_mask_hi=0.90,
        sun_amp=0.30, sun_dir=(0.3, -0.15, 0.9), sun_tight=140.0,
        sun_color=(0.78, 0.86, 1.0),
        star_warm=0.05,
    )),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "media", "skybox"))
    ap.add_argument("--size", type=int, default=1024, help="face size in px (cross is 4x by 3x)")
    ap.add_argument("--only", help="build just this variant key")
    ap.add_argument("--equirect", action="store_true", help="also write a flat preview")
    ap.add_argument("--equirect-only", action="store_true", help="preview only, no cross")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    if a.list:
        for k, (title, _p) in VARIANTS.items():
            print("%-22s %s" % (k, title))
        return

    keys = [a.only] if a.only else list(VARIANTS)
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)

    for k in keys:
        title, p = VARIANTS[k]
        if not a.equirect_only:
            img = build_cross(p, a.size)
            dest = os.path.join(out, k + ".png")
            img.save(dest, optimize=True, compress_level=9)
            print("%-22s %s  %dx%d  %.1f MB" % (
                k, dest, img.size[0], img.size[1], os.path.getsize(dest) / 1e6))
        if a.equirect or a.equirect_only:
            pv = build_equirect(p, width=max(512, a.size * 2))
            pdest = os.path.join(out, "_preview_" + k + ".png")
            pv.save(pdest, optimize=True, compress_level=9)
            print("%-22s preview -> %s" % ("", pdest))


if __name__ == "__main__":
    main()
