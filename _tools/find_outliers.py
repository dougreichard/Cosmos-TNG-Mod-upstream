"""Find the cells on a sheet that are NOT the species the sheet is meant to be.

Gemini mixes species into a sheet even when asked for one. The `kaonz` sheet came
back as 63 Klingons and a single Kazon; other sheets carry a few humans among the
aliens. Labelling by filename is therefore wrong everywhere, not just there - but
reviewing ~950 cells by hand is not reasonable either.

The useful asymmetry: MOST of a sheet is the intended species, so the intruders are
the cells farthest from that sheet's own centre. This ranks them so a human reviews a
handful per sheet instead of the lot. It does not name the intruder - it only says
"this one is unlike its neighbours", which is exactly the question a reviewer can
answer at a glance and this tool cannot.

FEATURES, chosen because they track species rather than pose or palette:

  skin tone     median Lab of a patch inside the detected face. Separates Orion
                (green), Andorian (blue), Jem'Hadar (grey), Vorta (pale), Klingon
                (brown) - most of the distinctions here are literally colour.
  brow texture  edge density across the forehead. This is what tells a Klingon or
                Cardassian from a human when the skin tone is nearly the same: a
                ridged crest is dense hard edges where a human brow is smooth. Skin
                tone alone put humans and Klingons in the same place.
  saturation    separates the vivid aliens from naturalistic human colouring.

Scored as a robust z-distance from the per-sheet MEDIAN (not the mean, which the
intruders themselves would drag), using the median absolute deviation for scale.
"""
import argparse
import json
import os

import cv2
import numpy as np


def features(img):
    h, w = img.shape[:2]
    # Face box: use the detector when it finds one, else the centre of the frame -
    # these busts are consistently framed, so the fallback is close.
    try:
        from crop_refs import detect
        box, _ = detect(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    except Exception:
        box = None
    if box is None:
        box = (int(w * .28), int(h * .18), int(w * .44), int(h * .44))
    x, y, fw, fh = box
    cheek = img[y + int(fh * .45):y + int(fh * .70), x + int(fw * .22):x + int(fw * .78)]
    brow = img[y + int(fh * .02):y + int(fh * .34), x + int(fw * .12):x + int(fw * .88)]
    if cheek.size == 0 or brow.size == 0:
        cheek = brow = img[h // 3:2 * h // 3, w // 3:2 * w // 3]
    lab = cv2.cvtColor(cheek, cv2.COLOR_BGR2LAB).reshape(-1, 3)
    skin = np.median(lab, axis=0)
    g = cv2.cvtColor(brow, cv2.COLOR_BGR2GRAY)
    edges = float((cv2.Canny(g, 60, 160) > 0).mean())
    sat = float(cv2.cvtColor(cheek, cv2.COLOR_BGR2HSV)[..., 1].mean())
    return np.array([skin[0], skin[1], skin[2], edges * 255.0, sat], np.float32)


def outliers(folder, stem, floor=None):
    """Rank a sheet's cells by how unlike the rest of that sheet they are.

    `floor` is the per-feature scale below which a sheet's own spread is not to be
    trusted, and it matters more than it looks. A sheet can be near-uniform in one
    feature - every Romulan has the same black hair, so the brow-texture spread is
    almost zero - and dividing by that spread turned a trivial difference into a
    distance of 18000, which both swamped the real intruders on that sheet and made
    scores meaningless between sheets. Flooring against the spread measured across
    ALL cells keeps a sheet from declaring a feature infinitely significant just
    because it happens not to vary locally.
    """
    files = sorted(f for f in os.listdir(folder)
                   if f.startswith(stem + "_") and f.endswith(".png"))
    F = np.array([features(cv2.imread(os.path.join(folder, f))) for f in files])
    med = np.median(F, axis=0)
    mad = np.median(np.abs(F - med), axis=0)
    if floor is not None:
        mad = np.maximum(mad, floor)
    mad[mad < 1e-3] = 1e-3
    d = np.abs((F - med) / mad).max(axis=1)          # worst single feature
    order = np.argsort(-d)
    return [(files[i], float(d[i])) for i in order]


def global_floor(folder, frac=0.35):
    """A fraction of the spread of each feature over every cell in the folder."""
    files = [f for f in os.listdir(folder) if f.endswith(".png") and not f.startswith("_")]
    F = np.array([features(cv2.imread(os.path.join(folder, f))) for f in files])
    med = np.median(F, axis=0)
    return np.median(np.abs(F - med), axis=0) * frac


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--top", type=int, default=8, help="cells to surface per sheet")
    ap.add_argument("--sheets", help="comma-separated stems; default all")
    ap.add_argument("-o", "--out", default=None)
    a = ap.parse_args()
    stems = sorted({f[:-4].rsplit("_", 1)[0] for f in os.listdir(a.folder)
                    if f.endswith(".png") and not f.startswith("_")})
    if a.sheets:
        stems = [s for s in stems if s in a.sheets.split(",")]
    floor = global_floor(a.folder)
    rep = {}
    for s in stems:
        ranked = outliers(a.folder, s, floor)
        rep[s] = ranked[:a.top]
        print("%-12s %s" % (s, "  ".join("%s(%.1f)" % (f[:-4].rsplit("_", 1)[1], d)
                                         for f, d in ranked[:a.top])))
    if a.out:
        json.dump(rep, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
