"""Cut generated 1024 busts down to 512 face cells with a real alpha channel.

Face cells are cutouts - the stock and TNG atlas cells run 50-61% opaque - and
SDXL cannot emit an alpha channel, so the matte has to be recovered afterwards.

WHY MATTING AND NOT A CHROMA KEY. The original plan was to generate on flat
magenta and flood-fill inward from the border. Two measured failures killed that:

  1. A colour named in the prompt is a colour SDXL paints the SUBJECT with. Asking
     for a magenta background returned a magenta face.
  2. Backgrounds are not reliably flat and cannot be made so from the prompt.
     "comic book illustration" pulls in comic COVER conventions, and even with
     radial-burst/halo/interior negatives in place the measured border variance was
     still 29-57 - bursts merely became gradients and bridge sets. A flood fill
     needs a flat border; it was never going to get one.

So the background is matted out instead, which means the generator no longer has
to fight for a flat background at all - facegen.py's BG phrase is now cosmetic.

u2net does the matting. The weights are already on this machine at ~/.u2net/
(167MB, from a previous rembg install) and onnxruntime is already in the comfyui
env, so this needs no download and no new package. onnxruntime offers CUDA here;
it falls back to CPU, which costs about a second a cell.

The rig is used as a SANITY CHECK, not as the matte: every bust is generated
against the same depth rig, so a matte that misses the rig's core region or
sprawls far outside it means the cell is bad and should be re-rolled. Using the
rig silhouette AS the matte would clip hair, which routinely extends well past
the skull - measured at ~9% of the silhouette across the existing 190 cells.
"""
import argparse
import glob
import os

import cv2
import numpy as np
import onnxruntime as ort
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
U2NET = os.path.expanduser("~/.u2net/u2net.onnx")
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)

_session = None


def session():
    """u2net session, CUDA if it actually loads, else CPU.

    onnxruntime ADVERTISES CUDAExecutionProvider here but fails to load it - this
    build wants CUDA 13 / cuDNN 9 and the env has neither - so asking for it just
    prints a wall of red. Try it, keep quiet, fall back. CPU is about a second a
    cell, which is nothing next to the ~8s SDXL spends generating one.
    """
    global _session
    if _session is None:
        ort.set_default_logger_severity(3)          # errors only, no EP warnings
        try:
            _session = ort.InferenceSession(U2NET, providers=["CUDAExecutionProvider"])
        except Exception:
            _session = None
        if _session is None or "CUDAExecutionProvider" not in _session.get_providers():
            _session = ort.InferenceSession(U2NET, providers=["CPUExecutionProvider"])
    return _session


def matte(img):
    """u2net saliency matte for a PIL RGB image, returned at the image's size."""
    s = session()
    x = np.asarray(img.convert("RGB").resize((320, 320), Image.LANCZOS), np.float32) / 255.0
    # u2net's own normalisation: scale to max, then imagenet mean/std.
    x = x / max(x.max(), 1e-6)
    x = (x - MEAN) / STD
    x = np.transpose(x, (2, 0, 1))[None].astype(np.float32)
    d = s.run(None, {s.get_inputs()[0].name: x})[0][0, 0]
    d = (d - d.min()) / max(d.max() - d.min(), 1e-6)
    return Image.fromarray((d * 255).astype(np.uint8), "L").resize(img.size, Image.LANCZOS)


def flat_bg_matte(img, tol=40, feather=0.8):
    """Matte a panel whose background is a single flat colour.

    The opposite case to the SDXL cells. A generated cast panel has a deliberately
    flat coloured square behind the bust, and u2net treats that square as part of
    the subject - measured across 77 panels: coverage 1.00, spill 0.33, i.e. it kept
    everything including the background. A colour key is right here, and it is right
    for the reason it was WRONG for SDXL: this background really is flat.

    Flood-filled inward from the corners rather than keyed globally, so a colour that
    also appears on the subject (a red tunic on a red panel) is not punched out of
    the middle of it. Tolerance has to be generous - these arrive as JPEG, and the
    ringing around the hard outlines pushes background pixels well off the flat
    value; at tol=34 the fill stopped short and left a speckled halo.
    """
    a = np.asarray(img.convert("RGB"), np.uint8)
    h, w = a.shape[:2]
    flood = a.copy()
    mask = np.zeros((h + 2, w + 2), np.uint8)
    lo = (tol,) * 3
    up = (tol,) * 3
    # FIXED_RANGE compares every candidate against the SEED colour. Without it
    # OpenCV compares against the NEIGHBOUR, so the fill walks across the gradual
    # shading of a face and swallows the whole panel - measured: 100% transparent.
    flags = (4 | cv2.FLOODFILL_MASK_ONLY | cv2.FLOODFILL_FIXED_RANGE | (255 << 8))
    # CORNERS ONLY. Seeding the edge midpoints as well flooded the whole panel:
    # in a tight headshot the middle of the top edge is hair, not background.
    for sx, sy in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        cv2.floodFill(flood, mask, (int(sx), int(sy)), 0, lo, up, flags)
    bg = mask[1:-1, 1:-1] > 0
    # Close pinholes the fill left inside the background (JPEG speckle).
    bg = cv2.morphologyEx(bg.astype(np.uint8), cv2.MORPH_CLOSE,
                          np.ones((5, 5), np.uint8)) > 0
    alpha = Image.fromarray(((~bg) * 255).astype(np.uint8), "L")
    return alpha.filter(ImageFilter.GaussianBlur(feather)) if feather else alpha


def clean(alpha, lo=0.30, hi=0.72, feather=1.2):
    """Push the soft saliency ramp toward a decisive matte.

    u2net returns a broad gradient at the edge. Left alone that reads as a halo
    once the cell is composited on the atlas, because the atlas has no background
    behind it to hide a soft edge. The window is applied first and the feather
    after, so the edge lands in one or two pixels instead of thirty.
    """
    a = np.asarray(alpha, np.float32) / 255.0
    a = np.clip((a - lo) / max(hi - lo, 1e-6), 0, 1)
    out = Image.fromarray((a * 255).astype(np.uint8), "L")
    return out.filter(ImageFilter.GaussianBlur(feather)) if feather else out


def rig_check(alpha, rig, core=0.75):
    """Compare the matte against the rig. Returns (coverage, spill).

    coverage - fraction of the rig's solid core the matte kept. Low means the
               matte ate part of the head or shoulders.
    spill    - fraction of the matte lying outside a generous dilation of the rig.
               High means it kept background furniture.
    """
    r = np.asarray(rig.convert("L").resize(alpha.size), np.float32) / 255.0
    a = np.asarray(alpha, np.float32) / 255.0
    solid = r > core
    generous = np.asarray(
        rig.convert("L").resize(alpha.size).filter(ImageFilter.MaxFilter(9)),
        np.float32) / 255.0 > 0.05
    keep = a > 0.5
    coverage = float((keep & solid).sum()) / max(solid.sum(), 1)
    spill = float((keep & ~generous).sum()) / max(keep.sum(), 1)
    return coverage, spill


def _opaque(alpha):
    return float((np.asarray(alpha, np.float32) / 255.0 > 0.5).mean())


def _corners_opaque(alpha, frac=0.08):
    """Are the corners still solid? Then the background was not removed.

    A bust cutout ALWAYS has empty corners - the stock atlas cells do, and so does
    every good cell here. Opaque-fraction alone missed this: a panel that keeps its
    flat background square can still land near 50% opaque and look sane by that
    measure while being, visibly, a square with a face on it (Worf on green, Kim on
    gold). The corner test names the failure directly.
    """
    a = np.asarray(alpha, np.float32) / 255.0 > 0.5
    h, w = a.shape
    k = max(3, int(min(h, w) * frac))
    return min(a[:k, :k].mean(), a[:k, -k:].mean(),
               a[-k:, :k].mean(), a[-k:, -k:].mean()) > 0.6


def panel_bg_color(img):
    """The flat colour behind a cast-grid bust (corner median)."""
    a = np.asarray(img.convert("RGB"), np.uint8)
    h, w = a.shape[:2]
    k = max(4, min(h, w) // 40)
    corners = np.concatenate([a[:k, :k].reshape(-1, 3), a[:k, -k:].reshape(-1, 3),
                              a[-k:, :k].reshape(-1, 3), a[-k:, -k:].reshape(-1, 3)])
    return tuple(int(v) for v in np.median(corners, axis=0))


def cut(src, size=512, rig=None, flat_bg=False, bg_fill=None):
    im = Image.open(src).convert("RGB")
    if flat_bg:
        # Try the colour key, then SANITY CHECK it. One fixed tolerance cannot serve
        # every panel: where the background colour is close to the subject's own the
        # key either stops early (Worf on green, Data on blue) or runs away and eats
        # the face (McCoy came back almost entirely transparent). A cell cut from a
        # bust should end up roughly half opaque - the stock atlas cells run
        # 0.50-0.61 - so anything far outside that is a failed key, and u2net gets
        # the panel instead. Neither method is reliable alone; the check is what
        # makes the pair reliable.
        a = flat_bg_matte(im)
        frac = _opaque(a)
        if frac < 0.28 or frac > 0.88 or _corners_opaque(a):
            a2 = clean(matte(im))
            if abs(_opaque(a2) - 0.55) < abs(frac - 0.55):
                a = a2
    else:
        a = clean(matte(im))
    stats = rig_check(a, rig) if rig is not None else None
    out = im.convert("RGBA")
    out.putalpha(a)
    if bg_fill is not None:
        # An opaque cell is fine for a BASE: layering composites over it, and only an
        # OVERLAY (implants, a VISOR) actually needs to be a cutout. Filling is also
        # what makes the set uniform - a few cells whose key failed would otherwise be
        # coloured squares among cutouts, which reads as a bug rather than a style.
        fill = panel_bg_color(im) if bg_fill == "panel" else bg_fill
        flat = Image.new("RGBA", out.size, tuple(fill) + (255,))
        flat.alpha_composite(out)
        out = flat
    # Downsample AFTER matting so the edge supersamples: a 1024 matte reduced to
    # 512 gives a genuinely antialiased boundary, where matting at 512 would not.
    return out.resize((size, size), Image.LANCZOS), stats


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", help="dir of generated 1024 pngs (or a single png)")
    ap.add_argument("-o", "--out", default=os.path.join(HERE, "out", "cells"))
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--rig", default=os.path.join(HERE, "rig_depth.png"))
    ap.add_argument("--min-coverage", type=float, default=0.90)
    ap.add_argument("--max-spill", type=float, default=0.12)
    ap.add_argument("--bg-fill", default=None,
                    help="'panel' keeps each cell's own flat backdrop, or a hex colour "
                         "for a uniform one. Omit for cutouts. Bases may be opaque; "
                         "OVERLAY cells must not be, so never fill those.")
    ap.add_argument("--flat-bg", action="store_true",
                    help="key a flat background colour instead of running u2net. Use "
                         "for cut cast-grid panels, whose background is a flat square.")
    a = ap.parse_args()

    if a.flat_bg:
        # These come from cast grids, which frame a HEAD where the rig frames a
        # BUST. The rig comparison is meaningless against that, so relax it rather
        # than have it cry wolf on all 77.
        a.min_coverage, a.max_spill = 0.0, 1.0
    files = [a.src] if a.src.lower().endswith(".png") else sorted(
        glob.glob(os.path.join(a.src, "*.png")))
    os.makedirs(a.out, exist_ok=True)
    rig = Image.open(a.rig) if os.path.exists(a.rig) else None

    flagged = []
    for f in files:
        fill = a.bg_fill
        if fill and fill != "panel":
            fill = tuple(int(fill.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
        img, st = cut(f, a.size, rig, a.flat_bg, fill)
        dest = os.path.join(a.out, os.path.basename(f))
        img.save(dest)
        if st:
            cov, spill = st
            bad = cov < a.min_coverage or spill > a.max_spill
            print("%-40s coverage %.2f  spill %.2f %s"
                  % (os.path.basename(f), cov, spill, "  <-- REROLL" if bad else ""))
            if bad:
                flagged.append(os.path.basename(f))
        else:
            print(os.path.basename(f))
    print("\n%d cells -> %s" % (len(files), a.out))
    if flagged:
        print("%d flagged for re-roll: %s" % (len(flagged), ", ".join(flagged)))


if __name__ == "__main__":
    main()
