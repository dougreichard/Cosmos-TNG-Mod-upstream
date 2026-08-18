"""Upscale a whole Gemini race sheet 4x through ComfyUI, then re-cut it.

WHY THE WHOLE SHEET, NOT EACH CELL. The panels are ~128px native against the 512 an
atlas cell wants, so they have to be upscaled - that is the same trap the mod's
original faces fell into (192x256 art stretched 2.67x, which is what made them look
soft). Doing it per cell would mean ~900 uploads and ~900 jobs, and would hand the
model a 128px image with no context. Upscaling the 1024px sheet ONCE gives the model
the whole mosaic to work with, costs one job per sheet, and lands the lattice exactly:
1024 -> 4096 turns a 128px period into a 512px one, which is the atlas cell size on
the nose. The cut then runs on the upscaled image with period and phase scaled by 4.

MODEL. RealESRGAN_x4plus_anime_6B is trained on cel art - hard outlines and flat fills,
which is precisely what these are - and is the default. 4x-UltraSharp is available for
comparison; --model picks it.

Run ComfyUI on 8188 first (the model tree is shared with 8189 but the nodes are not).
"""
import argparse
import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from facegen import _api, Graph                      # noqa: E402
from cut_regular import trim_bars, fit_lattice, bounds, margin_strip   # noqa: E402

ANIME = "RealESRGAN_x4plus_anime_6B.pth"


def upscale(path, server, model=ANIME, out_dir=None):
    """Send one image through the ESRGAN node; return the upscaled BGR image."""
    get, post, upload, view = _api(server)
    oi = get("/object_info")
    name = upload(path)
    g = Graph(oi)
    img = g.add("LoadImage", image=name)
    mdl = g.add("UpscaleModelLoader", model_name=model)
    up = g.add("ImageUpscaleWithModel", upscale_model=[mdl, 0], image=[img, 0])
    g.add("SaveImage", images=[up, 0], filename_prefix="upscale_sheet")
    pid = post("/prompt", {"prompt": g.g, "client_id": "upscale_sheets"})["prompt_id"]
    while True:
        h = get("/history/" + pid).get(pid, {})
        if h.get("status", {}).get("completed"):
            break
        if h.get("status", {}).get("status_str") == "error":
            raise SystemExit("ComfyUI error on " + path)
        time.sleep(1.0)
    outs = [o for n in h["outputs"].values() for o in n.get("images", [])]
    if not outs:
        raise SystemExit("no image returned for " + path)
    o = outs[0]
    dest = os.path.join(out_dir or ".", "_up_" + os.path.basename(path) + ".png")
    view(o["filename"], o.get("subfolder", ""), o.get("type", "output"), dest)
    return cv2.imread(dest), dest


def cut_upscaled(big, native, inset=0.05, size=512):
    """Cut the upscaled sheet using the lattice fitted on the NATIVE one.

    Fitting on the native image and scaling the result is deliberate: the lattice is
    a property of the source art, and re-fitting on a 4096px upscale would just be
    the same measurement through more pixels - slower, and free to disagree.
    """
    s = big.shape[1] / float(native.shape[1])
    trimmed, top = trim_bars(native)
    _, Px, phx = fit_lattice(trimmed, 1)
    xs = bounds(trimmed.shape[1], Px, phx)
    _, Py, phy = fit_lattice(margin_strip(trimmed, xs), 0, period=Px)
    ys = bounds(trimmed.shape[0], Py, phy)
    cells = []
    for y0, y1 in ys:
        for x0, x1 in xs:
            X0, X1 = int((x0) * s), int((x1) * s)
            Y0, Y1 = int((y0 + top) * s), int((y1 + top) * s)
            dx, dy = int((X1 - X0) * inset), int((Y1 - Y0) * inset)
            cel = big[Y0 + dy:Y1 - dy, X0 + dx:X1 - dx]
            cells.append(cv2.resize(cel, (size, size), interpolation=cv2.INTER_LANCZOS4))
    return cells, len(xs), len(ys)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("images", nargs="+")
    ap.add_argument("--server", default="127.0.0.1:8188")
    ap.add_argument("--model", default=ANIME)
    ap.add_argument("-o", "--out", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "out", "races_512"))
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--inset", type=float, default=0.05)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    tmp = os.path.join(a.out, "_tmp")
    os.makedirs(tmp, exist_ok=True)
    for p in a.images:
        native = cv2.imread(p)
        big, _ = upscale(p, a.server, a.model, tmp)
        cells, c, r = cut_upscaled(big, native, a.inset, a.size)
        stem = os.path.splitext(os.path.basename(p))[0].lower()
        for i, cel in enumerate(cells):
            cv2.imwrite(os.path.join(a.out, "%s_%02d.png" % (stem, i)), cel)
        print("%-16s %s -> %dx%d = %d cells at %d" %
              (os.path.basename(p), "x".join(map(str, big.shape[1::-1])),
               c, r, len(cells), a.size))


if __name__ == "__main__":
    main()
