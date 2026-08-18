"""Crop each character reference down to a face-centric square.

THE BUG THIS FIXES. ip-adapter-plus-face encodes its reference through CLIP-ViT-H
at 224x224 and expects a face to fill most of it. The fetched stills are whole
publicity photos, so the head is a small part of the frame and everything else -
body, uniform, set, background - competes with it. Measured face area as a
fraction of the frame, against how well the likeness actually landed:

    quark      24.3%   read as Quark
    picard     15.0%   read as Picard
    seven      11.5%   read as "a blonde woman with an implant"
    janeway     4.5%   read as "a woman with a bob"
    worf         n/a   no frontal face detected at all

Janeway's face was under a twentieth of what the adapter saw. That is the whole
explanation for "not sure they look like the reference" - the adapter was mostly
being shown a uniform and a wall.

The crop is expanded well past the detected box (MARGIN) because a face-only crop
loses the hairline, jaw and ears, and for this cast the silhouette above the eyes
is often the most identifying thing on screen - Picard's bald skull, Worf's crest,
Quark's ears, Seven's swept-up hair.

DETECTION FALLBACK CHAIN. Haar frontal misses a fair number of these: heavy
prosthetics (Worf's ridges), three-quarter angles and dramatic lighting all defeat
it. So: frontal -> alt2 -> profile -> a fixed upper-centre crop. The last is not a
guess so much as a portrait convention - in a publicity still the head is reliably
in the upper middle - and it is still a large improvement on the whole frame.
"""
import argparse
import json
import os

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "out", "refs")
DST = os.path.join(HERE, "out", "refs_face")
OUT_SIZE = 512
MARGIN = 1.9          # multiple of the detected face box to keep
CASCADES = ["haarcascade_frontalface_default.xml",
            "haarcascade_frontalface_alt2.xml",
            "haarcascade_profileface.xml"]


def detect(gray):
    """Largest face box from the first cascade that finds one, or None."""
    for name in CASCADES:
        cas = cv2.CascadeClassifier(os.path.join(cv2.data.haarcascades, name))
        if cas.empty():
            continue
        found = cas.detectMultiScale(gray, 1.08, 5, minSize=(36, 36))
        if len(found):
            return max(found, key=lambda r: r[2] * r[3]), name
    return None, None


def square_crop(img, box):
    """Square crop around `box`, expanded by MARGIN and clamped to the image.

    Clamping shifts the window rather than shrinking it, so a face near an edge
    still yields a full-size square instead of a thin sliver.
    """
    h, w = img.shape[:2]
    x, y, fw, fh = box
    cx, cy = x + fw / 2.0, y + fh / 2.0
    # Bias the centre UP a little: the expanded box should take in hairline and
    # skull rather than an equal amount of neck and chest.
    cy -= fh * 0.12
    side = min(max(fw, fh) * MARGIN, min(w, h))
    x0 = int(round(min(max(cx - side / 2.0, 0), w - side)))
    y0 = int(round(min(max(cy - side / 2.0, 0), h - side)))
    s = int(round(side))
    return img[y0:y0 + s, x0:x0 + s]


def fallback_crop(img):
    """Upper-centre square - where a head sits in a publicity still."""
    h, w = img.shape[:2]
    side = int(min(w, h) * 0.85)
    x0 = max((w - side) // 2, 0)
    y0 = max(int(h * 0.06), 0)
    if y0 + side > h:
        y0 = max(h - side, 0)
    return img[y0:y0 + side, x0:x0 + side]


def crop_multi(a, multi_path):
    """Crop a multi-reference set, keeping only images that really contain a face.

    This filter is the whole reason multi-reference is usable at all. An article's
    image list contains props and scenery alongside the cast - Picard's article
    offers a photograph of his Ressikan flute, Worf's a rack of bat'leths and a
    video game screenshot - and an identity embedding averaged over a flute is
    worse than one taken from a single good still. No detectable face, no reference.
    """
    os.makedirs(a.out, exist_ok=True)
    multi = json.load(open(multi_path))
    out_index, dropped = {}, []
    cache = {}
    for key in sorted(multi):
        kept = []
        for fn in multi[key]:
            if fn in cache:
                if cache[fn]:
                    kept.append(cache[fn])
                continue
            img = cv2.imread(os.path.join(a.src, fn))
            if img is None:
                cache[fn] = None
                continue
            box, _ = detect(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
            if box is None:
                cache[fn] = None
                dropped.append(fn)
                continue
            crop = cv2.resize(square_crop(img, box), (a.size, a.size),
                              interpolation=cv2.INTER_LANCZOS4)
            dest = os.path.splitext(fn)[0] + ".png"
            cv2.imwrite(os.path.join(a.out, dest), crop)
            cache[fn] = dest
            kept.append(dest)
        if kept:
            out_index[key] = kept
        print("%-18s kept %d of %d" % (key, len(kept), len(multi[key])))
    with open(os.path.join(a.out, "index_multi.json"), "w") as f:
        json.dump(out_index, f, indent=1, sort_keys=True)
    print("\n%d characters -> %s" % (len(out_index), a.out))
    if dropped:
        print("dropped (no face): %s" % ", ".join(sorted(set(dropped))))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=SRC)
    ap.add_argument("-o", "--out", default=DST)
    ap.add_argument("--size", type=int, default=OUT_SIZE)
    ap.add_argument("--multi", action="store_true",
                    help="crop index_multi.json, DROPPING images with no detectable face")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    multi_path = os.path.join(a.src, "index_multi.json")
    if a.multi and os.path.exists(multi_path):
        return crop_multi(a, multi_path)
    index = json.load(open(os.path.join(a.src, "index.json")))
    out_index, guessed = {}, []
    # Several keys share one file (the _alt cells, and lore/data); crop each file once.
    done = {}
    for key in sorted(index):
        fn = index[key]
        if fn in done:
            out_index[key] = done[fn]
            continue
        img = cv2.imread(os.path.join(a.src, fn))
        if img is None:
            print("%-18s unreadable" % key)
            continue
        h, w = img.shape[:2]
        box, cascade = detect(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
        if box is not None:
            crop = square_crop(img, box)
            note = "%s  face %.1f%% -> %.1f%%" % (
                cascade.replace("haarcascade_", "").replace(".xml", ""),
                100.0 * box[2] * box[3] / (w * h),
                100.0 * box[2] * box[3] / max(crop.shape[0] * crop.shape[1], 1))
        else:
            crop = fallback_crop(img)
            note = "no detection -> upper-centre crop"
            guessed.append(key)
        crop = cv2.resize(crop, (a.size, a.size), interpolation=cv2.INTER_LANCZOS4)
        dest_name = os.path.splitext(fn)[0] + ".png"
        cv2.imwrite(os.path.join(a.out, dest_name), crop)
        done[fn] = dest_name
        out_index[key] = dest_name
        print("%-18s %s" % (key, note))

    with open(os.path.join(a.out, "index.json"), "w") as f:
        json.dump(out_index, f, indent=1, sort_keys=True)
    print("\n%d crops -> %s" % (len(done), a.out))
    if guessed:
        print("fell back to a centre crop (eyeball these): %s" % ", ".join(guessed))


if __name__ == "__main__":
    main()
