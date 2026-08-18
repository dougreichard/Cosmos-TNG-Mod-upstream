"""Quality pass over freshly cut race cells: blanks, duplicates, caption bars.

Three faults are worth catching automatically, and each was seen in the Gemini race
sheets rather than imagined:

  BLANK      a sheet that ran out of subjects fills the tail with flat colour (the
             vorta/gorn sheet ends on a black square). Caught as near-zero colour
             variance.
  DUPLICATE  ATTEMPTED AND ABANDONED - the check reports a distance but never a
             verdict. The generator does repeat a subject with only a background
             change (four near-identical Deanna panels in a row), but no image
             distance tried here separates that from two DIFFERENT members of the
             same species: measured on the centre crop, same-subject pairs span
             18.2-28.8 while genuinely distinct pairs reach down to 17.5, so the
             distributions overlap with no threshold between them. Every threshold
             that caught all six known repeats also false-flagged a quarter of the
             distinct pairs. Within one race sheet that is unsurprising - same
             species, same style, same framing, same palette.

             So near-duplicates are KEPT. There are ~960 cells against a few hundred
             needed, which makes a repeat a cosmetic cost and a wrongly-dropped
             character a real one. `dup_nearest` is recorded for a human to sort by;
             nothing is dropped on it.
  CAPTION    some panels carry a baked-in label bar ("DEANNA (MEDITATION)") across
             the bottom. Caught as a dark, low-saturation, full-width band in the
             bottom eighth.

Nothing is deleted here - the pass writes a verdict per cell so the packing step can
choose, and so a wrong call is visible rather than silent.
"""
import argparse
import json
import os

import cv2
import numpy as np


def centre(img):
    """The bust, minus the backdrop - what a similarity check should look at."""
    h, w = img.shape[:2]
    c = img[int(h * .12):int(h * .82), int(w * .20):int(w * .80)]
    return cv2.cvtColor(cv2.resize(c, (64, 64)), cv2.COLOR_BGR2GRAY).astype(np.float32)


def is_blank(img, tol=8.0):
    return float(img.reshape(-1, 3).std(axis=0).mean()) < tol


def caption_band(img, frac=0.14, ink=200, ink_min=0.012, dark=70, dark_min=0.15):
    """True when the bottom of the cell carries a baked-in label bar.

    Detect the LETTERING, not the bar. The obvious test - "a dark full-width band
    across the bottom" - fails in both directions on this art: a bust's shoulders and
    collar are dark and fill the bottom of most frames (that test flagged 499 of 960
    cells), and tightening it to near-black full width then MISSED the real captions,
    because the bar is only partly black and does not span the full width (measured
    frac<45 of just 0.19 on a betazoid cell that plainly reads "DEANNA (MEDITATION)").

    The white text is unambiguous. Bright pixels in the bottom band run 3-7% on a
    captioned cell against under 0.1% on a clean one - a 30x separation, and the
    distribution across all 960 cells is bimodal with a wide empty gap (p90 0.006,
    p95 0.067) that the threshold sits in. The dark-fraction test is kept only as a
    companion, so a cell that is merely bright at the bottom is not mistaken for one
    with lettering on a dark bar.
    """
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h = g.shape[0]
    band = g[h - int(h * frac):]
    return bool((band > ink).mean() > ink_min and (band < dark).mean() > dark_min)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--report-nearest", action="store_true",
                    help="record each cell's closest neighbour (advisory only)")
    ap.add_argument("-o", "--out", default=None)
    a = ap.parse_args()

    files = sorted(f for f in os.listdir(a.folder) if f.endswith(".png")
                   and not f.startswith("_"))
    rep, cens = {}, {}
    for f in files:
        img = cv2.imread(os.path.join(a.folder, f))
        rep[f] = dict(blank=bool(is_blank(img)), caption=bool(caption_band(img)))
        if a.report_nearest and not rep[f]["blank"]:
            cens[f] = centre(img)
    for f, c in cens.items():
        best, bf = 1e9, None
        for g, d in cens.items():
            if g == f:
                continue
            m = float(np.abs(c - d).mean())
            if m < best:
                best, bf = m, g
        rep[f]["dup_nearest"] = [bf, round(best, 1)]
    out = a.out or os.path.join(a.folder, "_qc.json")
    json.dump(rep, open(out, "w"), indent=1, sort_keys=True)
    nb = sum(1 for v in rep.values() if v["blank"])
    nc = sum(1 for v in rep.values() if v["caption"])
    print("%d cells: %d blank, %d with a caption bar -> %d usable "
          "(near-duplicates kept - see module docstring)"
          % (len(rep), nb, nc, len(rep) - nb - nc))
    print("wrote", out)


if __name__ == "__main__":
    main()
