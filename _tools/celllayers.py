"""Split a finished cell into TINTABLE LAYERS - skin, hair, uniform, outline.

This is the character builder that this art can actually support, and it works for
the reason the differencing approach did not: the layers come out of ONE cell, so
they register perfectly by construction. There is no alignment step because there is
nothing to align.

WHY IT WORKS HERE. Flat cel art is a handful of solid colour regions under a bold
outline, and on a bust those regions are already semantic - skin, hair, uniform,
background. Measured on four finished cells, the top FOUR colours cover 79-91% of the
whole image, so separating by colour separates by part.

WHAT IT BUYS. The face string tints each layer independently (face.js multiplies the
layer by its colour and masks back to the sprite's alpha). Tinting a WHOLE-face cell
was useless - it shifts skin, uniform and background together, giving the same person
under different lighting. Tinting a skin layer, a hair layer and a uniform layer
separately is a real builder:

    tng1 #e0ac69 3 2;tng1 #3b2a1e 3 3;tng1 #a8302c 3 4;
      ^ skin tone     ^ hair colour    ^ uniform colour

Three cells per face instead of one, and the combinations are free.

WHAT IT DOES NOT BUY. Swapping a hairstyle BETWEEN characters still fails - a hair
path cut from one head does not fit another, which is the same registration wall
partextract.py hit. This varies colour, not shape.

STATUS, measured across kirk / picard / worf / sisko / andorian / quark:

  skin      WORKS on every species and tone tried - human, dark-skinned, blue
            (Andorian), orange (Ferengi), brown (Klingon). Seeded from the colour
            sampled at the DETECTED FACE, so it does not care how dark the skin is.
            This is a usable builder axis today.
  hair      works on most, and correctly comes back empty for a bald character.
  uniform   DOES NOT WORK. "not skin, not ink, below the face midline" describes a
            MOUTH as well as a tunic, so recolouring it turns Worf's teeth, Sisko's
            lips and Quark's eyes teal. Telling a tunic from a mouth needs real
            segmentation, not a position rule - do not ship this axis as it stands.
  backdrop  mostly excluded (flood-filled from inside the panel border), but a cell
            whose tile colour is close to the subject can still leak.

So: ship the SKIN axis, leave uniform alone until the classifier is better.

CLASSIFICATION IS HEURISTIC, and deliberately conservative. Regions are labelled by
where they sit and what hue they are: background touches the border, uniform occupies
the lower band, hair is dark and sits above/around the face, skin is the flesh-hued
region in the middle. Anything unclassified stays with the base layer rather than
being guessed at, so a mislabel loses a builder axis - it never loses part of the face.
"""
import argparse
import os

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
LAYERS = ("base", "skin", "hair", "uniform")


def quantize(img, k=8):
    Z = img.reshape(-1, 3).astype(np.float32)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 24, 1.0)
    _, lab, cen = cv2.kmeans(Z, k, None, crit, 4, cv2.KMEANS_PP_CENTERS)
    return lab.reshape(img.shape[:2]), cen.astype(np.uint8)


def background_mask(img, tol=40):
    """The flat tile backdrop, flood-filled from the corners.

    Done FIRST and structurally, not by hue. A hue window put Kirk's gold backdrop in
    the same bucket as his skin (and his brown hair with it), so one "skin" layer came
    out at 88% of the cell and tinting it moved the background too.
    """
    h, w = img.shape[:2]
    mask = np.zeros((h + 2, w + 2), np.uint8)
    flags = 4 | cv2.FLOODFILL_MASK_ONLY | cv2.FLOODFILL_FIXED_RANGE | (255 << 8)
    # Seed just INSIDE the panel border, not at the pixel corner. These cells were cut
    # from a grid and keep a dark border rule, so a corner seed fills the border ring,
    # stops at it, and never reaches the flat backdrop within - which left the
    # Andorian's orange tile unmasked and recolouring his "uniform" repainted the
    # whole square. Corners are still seeded too, for cells that have no border.
    inset_x, inset_y = max(4, w // 14), max(4, h // 14)
    seeds = ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
             (inset_x, inset_y), (w - 1 - inset_x, inset_y),
             (inset_x, h - 1 - inset_y), (w - 1 - inset_x, h - 1 - inset_y))
    for sx, sy in seeds:
        cv2.floodFill(img.copy(), mask, (int(sx), int(sy)), 0,
                      (tol,) * 3, (tol,) * 3, flags)
    return mask[1:-1, 1:-1] > 0


def classify(img, lab, cen):
    """label index -> one of LAYERS, seeded from the DETECTED FACE.

    Skin is whatever colour occupies the middle of the detected face box - sampled,
    not assumed. Thresholding on brightness instead ("dark and high in the frame is
    hair") works for a light-skinned human and fails immediately on a dark-skinned or
    prosthetic one: Worf's brown skin came out as 68% "hair" and his skin layer was
    empty, which would have shipped a builder that only recolours white faces.

    Order matters; each test only sees what the earlier ones left:
      background  flood-filled from the corners
      skin        the cluster(s) matching the sampled face colour
      base        the ink - dark AND thin, so a black tunic is not read as outline
      hair        what remains ABOVE the face box
      uniform     what remains BELOW it
    """
    from crop_refs import detect
    h, w = lab.shape
    bg = background_mask(img)
    box, _ = detect(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    if box is None:
        box = (int(w * .28), int(h * .18), int(w * .44), int(h * .44))
    fx, fy, fw, fh = box
    # Sample the cheeks/forehead, avoiding eyes, brows and mouth.
    patch = img[fy + int(fh * .30):fy + int(fh * .55), fx + int(fw * .22):fx + int(fw * .78)]
    skin_ref = np.median(patch.reshape(-1, 3), axis=0) if patch.size else np.array([200, 170, 150])

    out = {}
    for i, c in enumerate(cen):
        m = lab == i
        if not m.any():
            continue
        ys = np.nonzero(m)[0]
        share = float(m.mean())
        val = int(cv2.cvtColor(np.uint8([[c]]), cv2.COLOR_BGR2HSV)[0][0][2])
        if float((m & bg).sum()) / max(m.sum(), 1) > 0.6:
            out[i] = "background"
            continue
        # Close to the sampled face colour -> skin, at any darkness.
        if float(np.abs(np.float32(c) - skin_ref).max()) < 46:
            out[i] = "skin"
            continue
        if val < 70:
            er = cv2.erode(m.astype(np.uint8), np.ones((7, 7), np.uint8))
            if er.mean() < share * 0.25:
                out[i] = "base"
                continue
        out[i] = "hair" if ys.mean() < fy + fh * 0.55 else "uniform"
    return out


def split(path, k=8, feather=0.6):
    img = cv2.imread(path)
    if img is None:
        raise SystemExit("cannot read " + path)
    lab, cen = quantize(img, k)
    kind = classify(img, lab, cen)
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    # SUBTRACT the backdrop from every layer, do not merely decline to label it.
    # Classification is per colour CLUSTER, and a cluster that is mostly subject can
    # still own pixels out in the flat backdrop - which is how recolouring Worf's
    # "hair" repainted his green tile, and the Andorian's "uniform" turned the whole
    # square green. Masking each layer against the flood-filled backdrop makes that
    # impossible regardless of how the cluster was labelled.
    bg = background_mask(img)
    out = {}
    for name in LAYERS:
        m = np.zeros(lab.shape, np.uint8)
        for i, kd in kind.items():
            if kd == name:
                m[lab == i] = 255
        m[bg] = 0
        if not m.any():
            continue
        if feather:
            m = cv2.GaussianBlur(m, (0, 0), feather)
        out[name] = Image.fromarray(np.dstack([rgb, m]), "RGBA")
    return out, {LAYERS[j]: sum((lab == i).mean() for i, kd in kind.items() if kd == LAYERS[j])
                 for j in range(len(LAYERS))}


def tint(img, hexcol):
    """Exactly face.js drawLayer(): multiply through, mask back to the sprite alpha."""
    r, g, b = [int(hexcol[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]
    a = np.asarray(img, np.float32)
    a[..., 0] *= r
    a[..., 1] *= g
    a[..., 2] *= b
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cell")
    ap.add_argument("-o", "--out", default=os.path.join(HERE, "out", "layers"))
    ap.add_argument("-k", type=int, default=8)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    layers, share = split(a.cell, a.k)
    key = os.path.splitext(os.path.basename(a.cell))[0]
    for name, im in layers.items():
        im.save(os.path.join(a.out, "%s_%s.png" % (key, name)))
        print("  %-8s %5.1f%% of the cell" % (name, share.get(name, 0) * 100))
    print("wrote %d layers -> %s" % (len(layers), a.out))


if __name__ == "__main__":
    main()
