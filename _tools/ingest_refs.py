"""Ingest hand-picked reference images and fold them into the reference index.

Automated sourcing has a ceiling. Wikipedia gives 2-4 images per character and a
fair number are not the character at all - Picard's article offers a photograph of
his Ressikan flute, Worf's a rack of bat'leths - while Commons offers the actor
decades later and out of costume, which for a prosthetic character like Quark is
worse than useless. A human picking three good in-costume stills beats any of that.

So: drop images into `out/refs_user/`, named after the cell key. Anything matching
the key is picked up:

    out/refs_user/picard.jpg
    out/refs_user/picard2.jpg
    out/refs_user/picard_anything.png

They are face-cropped exactly like fetched ones (same detector, same margin, same
512 square) so the identity adapter sees the face filling the frame rather than a
uniform and a wall, and they are written into index_multi.json AHEAD of the fetched
ones - a hand-picked reference should outrank a scraped one.

Files dropped straight into `out/refs_face/` are also picked up, because that is
where they were put the first time; they are cropped in place if they are not
already a 512 square.
"""
import argparse
import json
import os
import re
import shutil

import cv2

from crop_refs import detect, fallback_crop, square_crop

HERE = os.path.dirname(os.path.abspath(__file__))
USER = os.path.join(HERE, "out", "refs_user")
FACE = os.path.join(HERE, "out", "refs_face")
SIZE = 512
EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


def key_of(filename, keys):
    """Longest matching key, so `seven_of_nine2.jpg` beats a stray `seven` key."""
    stem = re.split(r"[^a-z0-9_]", os.path.splitext(os.path.basename(filename))[0].lower())[0]
    stem = stem.rstrip("0123456789")
    best = None
    for k in keys:
        if stem == k or stem.startswith(k) or os.path.basename(filename).lower().startswith(k):
            if best is None or len(k) > len(best):
                best = k
    return best


def crop_to_face(src, dest, size=SIZE):
    img = cv2.imread(src)
    if img is None:
        return None
    if img.shape[0] == size and img.shape[1] == size:
        shutil.copy2(src, dest)          # already a prepared square - leave it alone
        return "already square"
    box, cascade = detect(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    crop = square_crop(img, box) if box is not None else fallback_crop(img)
    crop = cv2.resize(crop, (size, size), interpolation=cv2.INTER_LANCZOS4)
    cv2.imwrite(dest, crop)
    return cascade.replace("haarcascade_", "").replace(".xml", "") if box is not None \
        else "no detection -> centre crop"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user", default=USER)
    ap.add_argument("--face", default=FACE)
    ap.add_argument("--roster", default=os.path.join(HERE, "face_roster.json"))
    a = ap.parse_args()
    os.makedirs(a.user, exist_ok=True)
    os.makedirs(a.face, exist_ok=True)

    keys = set(c["key"] for c in json.load(open(a.roster))["cells"])
    idx_path = os.path.join(a.face, "index_multi.json")
    index = json.load(open(idx_path)) if os.path.exists(idx_path) else {}

    # Candidates: everything in refs_user, plus loose drops in refs_face that are
    # not already one of our generated crops.
    generated = set()
    for v in index.values():
        generated.update(v if isinstance(v, list) else [v])
    cands = []
    for d in (a.user, a.face):
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.lower().endswith(EXTS) or fn == "index.json":
                continue
            if d == a.face and (fn in generated or re.match(r".+_\d+\.png$", fn)):
                continue
            cands.append(os.path.join(d, fn))

    added = {}
    for path in cands:
        k = key_of(path, keys)
        if not k:
            print("%-42s no key match - skipped" % os.path.basename(path))
            continue
        n = len(added.get(k, [])) + 1
        dest_name = "user_%s_%d.png" % (k, n)
        note = crop_to_face(path, os.path.join(a.face, dest_name))
        if note is None:
            print("%-42s unreadable" % os.path.basename(path))
            continue
        added.setdefault(k, []).append(dest_name)
        print("%-42s -> %-24s %s" % (os.path.basename(path), k, note))

    # Hand-picked first: they should outrank anything scraped.
    for k, files in added.items():
        prev = index.get(k, [])
        prev = prev if isinstance(prev, list) else [prev]
        index[k] = files + [p for p in prev if not p.startswith("user_")]

    with open(idx_path, "w") as f:
        json.dump(index, f, indent=1, sort_keys=True)
    print("\n%d hand-picked references over %d characters -> %s"
          % (sum(len(v) for v in added.values()), len(added), idx_path))
    for k in sorted(added):
        print("   %-18s %d refs total" % (k, len(index[k])))


if __name__ == "__main__":
    main()
