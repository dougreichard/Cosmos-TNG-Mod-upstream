"""Pack the new race cells into additional atlas sheets, alongside the shipped ones.

ADDITIVE ON PURPOSE. The mod already ships TNG_Faces_1/2 (aliases tng1/tng2) holding
127 cells, and a face string names a sheet, a column and a row - so repacking those
would silently move every existing face. Anything holding a string like
"tng2 #fff 3 2;" (a saved character, a mission, the portrait bake) would then render
somebody else. So sheets 1 and 2 are left untouched and the new art goes into tng3
onward, and new keys CONTINUE each race's existing numbering rather than restarting -
the shipped set already has andorian_01..03, so the new Andorians begin at 04.

SELECTION IS FARTHEST-POINT, not first-N. There are ~930 new cells for ~370 slots, and
the sheets contain near-duplicates that no threshold could separate (see qc_cells.py:
same-subject and distinct-subject distances overlap). Picking a maximally SPREAD
subset sidesteps that entirely - it never has to decide whether two cells are the same
person, it just declines to take both when they sit on top of each other. Seeded from
the cell closest to the species median, so the most typical face of a species is
always in, and each subsequent pick is the one farthest from everything chosen so far.

ROLE IS NOT INFERRED. Every new cell is written as role "ops", matching the default
the shipped set uses. The role skew (73 ops against 6 science) is real and still open;
guessing a division from uniform colour works for Starfleet crew and is meaningless
for Klingon armour or Ferengi tunics, so a wrong guess would be worse than a known
default.
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cv2                                            # noqa: E402
from find_outliers import features                    # noqa: E402

CELL, GRID = 512, 8
PER = GRID * GRID


def spread_select(paths, k):
    """k cells chosen to be as unlike each other as possible (farthest-point)."""
    if len(paths) <= k:
        return list(paths)
    F = np.array([features(cv2.imread(p)) for p in paths], np.float32)
    F = (F - F.mean(0)) / (F.std(0) + 1e-6)
    med = np.median(F, axis=0)
    first = int(np.argmin(((F - med) ** 2).sum(1)))    # the most typical face
    chosen = [first]
    d = ((F - F[first]) ** 2).sum(1)
    while len(chosen) < k:
        nxt = int(np.argmax(d))
        chosen.append(nxt)
        d = np.minimum(d, ((F - F[nxt]) ** 2).sum(1))
    return [paths[i] for i in chosen]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cells", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "out", "races_final"))
    ap.add_argument("--faces", default="../tng_races/tng_faces.json")
    ap.add_argument("--index", default="../tng_races/tng_face_index.json")
    ap.add_argument("--per-species", type=int, default=22)
    ap.add_argument("--first-sheet", type=int, default=3)
    ap.add_argument("--pack-version", default="v0.3.0")
    ap.add_argument("-o", "--out", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "out", "sheets_new"))
    a = ap.parse_args()

    faces = json.load(open(a.faces))
    index = json.load(open(a.index))
    man = json.load(open(os.path.join(a.cells, "_manifest.json")))

    by = {}
    for key, v in sorted(man.items()):
        by.setdefault(v["race"], []).append(os.path.join(a.cells, key + ".png"))

    # Highest existing number per race, so new keys continue the sequence.
    top = {}
    for k in faces:
        race, _, num = k.rpartition("_")
        if num.isdigit():
            top[race] = max(top.get(race, 0), int(num))

    picked = []
    for race in sorted(by):
        sel = spread_select(by[race], a.per_species)
        # keep the chosen ones in their original order for a tidy sheet
        sel = [p for p in by[race] if p in set(sel)]
        for p in sel:
            top[race] = top.get(race, 0) + 1
            picked.append(("%s_%02d" % (race, top[race]), race, p))
        print("%-12s %3d available -> %d picked" % (race, len(by[race]), len(sel)))

    os.makedirs(a.out, exist_ok=True)
    sheets = []
    for s in range((len(picked) + PER - 1) // PER):
        chunk = picked[s * PER:(s + 1) * PER]
        alias = "tng%d" % (a.first_sheet + s)
        name = "TNG_Faces_%d" % (a.first_sheet + s)
        sheet = Image.new("RGBA", (CELL * GRID, CELL * GRID), (0, 0, 0, 0))
        for i, (key, race, path) in enumerate(chunk):
            col, row = i % GRID, i // GRID
            im = Image.open(path).convert("RGBA")
            if im.size != (CELL, CELL):
                im = im.resize((CELL, CELL), Image.LANCZOS)
            sheet.paste(im, (col * CELL, row * CELL))
            faces[key] = "%s #fff %d %d;" % (alias, col, row)
            index[key] = {"era": "race", "kind": "base", "race": race, "role": "ops"}
        sheet.save(os.path.join(a.out, name + ".png"))
        sheets.append(name)
        print("%s.png  %dx%d  %d cells  alias %s"
              % (name, sheet.size[0], sheet.size[1], len(chunk), alias))

    json.dump(faces, open(os.path.join(a.out, "tng_faces.json"), "w"),
              indent=1, sort_keys=True)
    json.dump(index, open(os.path.join(a.out, "tng_face_index.json"), "w"),
              indent=1, sort_keys=True)
    print("\n%d faces total (%d new)" % (len(faces), len(picked)))
    # Exactly the form the file already uses for tng1/tng2: the pack directory
    # lives under __lib__/media, and there is NO .png - the engine (and face.js)
    # append the extension themselves. A path in any other shape looks right,
    # pastes cleanly, and resolves to nothing.
    print("\nPaste into <cosmos>/data/graphics/allFaceFiles.txt (engine-owned):")
    for n in sheets:
        print("tng%s ../missions/__lib__/media/ScornMandark.Cosmos-TNG-Mod.media.%s/"
              "faces_tng/%s" % (n.split("_")[-1], a.pack_version, n))


if __name__ == "__main__":
    main()
