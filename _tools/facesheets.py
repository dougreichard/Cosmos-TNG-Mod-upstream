"""Pack the 512px face cells into stock-shaped atlas sheets.

8x8 of 512 = 4096x4096, exactly the geometry of Skaraan_Set / Zimni_Set / etc, so
face.js's gridCols() (8 for any alias that is not 'ter') and the engine agree with
no special-casing. 384 cells therefore land in six sheets, all full.

Replaces the version that sat untracked at the sbs_utils repo root. Two problems
with that one: it imported `png` and `pngw`, which exist nowhere on this machine
(so it could not run at all), and mod build tooling had no business living in a
shared library checkout another session edits live.

WHAT A KEY MAPS TO. Most keys are one whole-bust cell:

    tng1 #fff 3 2;

A key with a `layers` list composites several cells instead, lowest first:

    tng6 #fff 2 1;tng6 #fff 5 3;

That is what makes Borg implants and Geordi's VISOR separate art rather than
baked into each face - and it is what lets MAST assimilate a character at runtime
by appending a layer to a face string it did not author. Overlay cells must keep
their alpha; base cells need not (see cutcells.py --bg-fill).

PACKING ORDER IS DELIBERATE. Cells are packed in roster order, which is era order
(tos, tng, ds9, voy, then the non-Federation races and finally the overlay bank),
so a sheet is reviewable as a unit and re-rolling one cell dirties one sheet.
"""
import argparse
import hashlib
import json
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
CELL, GRID = 512, 8
PER = GRID * GRID


def build(roster_path, cells_dirs, out_dir, alias_prefix="tng", size=CELL):
    roster = json.load(open(roster_path))
    entries = roster["cells"]
    os.makedirs(out_dir, exist_ok=True)

    # Resolve each key to a file, taking the FIRST directory that has it. Callers
    # pass the Gemini-derived cells ahead of the locally generated ones so a
    # hand-picked cell always wins over a regenerated stand-in.
    def find(key):
        for d in cells_dirs:
            p = os.path.join(d, key + ".png")
            if os.path.exists(p):
                return p
        return None

    placed, missing = {}, []
    for i, e in enumerate(entries):
        p = find(e["key"])
        if p is None:
            missing.append(e["key"])
        placed[e["key"]] = (i, p)

    sheets = (len(entries) + PER - 1) // PER
    faces, written = {}, []
    for s in range(sheets):
        alias = "%s%d" % (alias_prefix, s + 1)
        sheet = Image.new("RGBA", (size * GRID, size * GRID), (0, 0, 0, 0))
        n = 0
        for k in range(PER):
            idx = s * PER + k
            if idx >= len(entries):
                break
            e = entries[idx]
            col, row = k % GRID, k // GRID
            p = placed[e["key"]][1]
            if p:
                im = Image.open(p).convert("RGBA")
                if im.size != (size, size):
                    im = im.resize((size, size), Image.LANCZOS)
                sheet.paste(im, (col * size, row * size))
                n += 1
            # The face string is recorded even for a cell that has no art yet, so
            # the map stays complete and a later re-run only has to redraw pixels.
            e["_layer"] = "%s #fff %d %d;" % (alias, col, row)
        name = "TNG_Faces_%d" % (s + 1)
        dest = os.path.join(out_dir, name + ".png")
        sheet.save(dest)
        written.append((name, n))
        print("%s.png  %dx%d  %d/%d cells  alias %s"
              % (name, sheet.size[0], sheet.size[1], n, min(PER, len(entries) - s * PER), alias))

    # Now that every cell knows its own layer string, compose the key -> face map.
    by_key = {e["key"]: e for e in entries}
    for e in entries:
        layers = e.get("layers")
        if layers:
            parts = [by_key[l]["_layer"] for l in layers if l in by_key]
            faces[e["key"]] = "".join(parts)
        else:
            faces[e["key"]] = e["_layer"]

    with open(os.path.join(out_dir, "tng_faces.json"), "w") as f:
        json.dump(faces, f, indent=1, sort_keys=True)

    # A SIDECAR INDEX, because the key is not a reliable description of the cell.
    # Deriving race from the key turned every named character into its own race -
    # "picard", "seven" from seven_of_nine, "the" from the_doctor, "kai" from
    # kai_winn, and "gear" from gear_visor - giving 80 races where there are ~25.
    # The roster already knows the answer, so ship it rather than re-guess it at
    # load time. `kind` travels too: an overlay is a layer, not a face, and must
    # never be handed out by random_face().
    index = {e["key"]: {"race": e["race"], "role": e["role"], "kind": e["kind"],
                        "era": e["era"]} for e in entries}
    with open(os.path.join(out_dir, "tng_face_index.json"), "w") as f:
        json.dump(index, f, indent=1, sort_keys=True)
    print("tng_face_index.json: %d entries (race/role/kind per cell)" % len(index))

    composed = [k for k, v in faces.items() if v.count(";") > 1]
    print("\ntng_faces.json: %d face strings (%d composed of several layers)"
          % (len(faces), len(composed)))
    if composed:
        print("  composed:", ", ".join(sorted(composed)[:6]))
    if missing:
        print("%d cells have no art yet (their slot is reserved and blank):" % len(missing))
        print("  " + ", ".join(sorted(missing)[:12]) + (" ..." if len(missing) > 12 else ""))
    return written, faces, missing


def build_portraits(roster_path, cells_dirs, out_dir, cols=16, cell=256):
    """Re-cut the PORTRAIT atlas from the same cells.

    `image://tng:picard` is a different mechanism from a face: a flat ImageAtlas
    sub_rect, no layering, no alpha compositing. It has to be rebuilt from the same
    art or the mod ships two visibly different generations of the same characters -
    the new TAS bust as a face, the old soft one as a portrait.

    Rows are derived from the cell count rather than fixed, and the cells are square
    here (256x256) where the old sheet used 256x340. `gui_image_add_atlas_grid`
    measures the cell size from the file, so the shape is free to change - but the
    COLS/ROWS passed to it must match, which is why this prints them.
    """
    entries = json.load(open(roster_path))["cells"]

    def find(key):
        for d in cells_dirs:
            q = os.path.join(d, key + ".png")
            if os.path.exists(q):
                return q
        return None

    have = [e for e in entries if find(e["key"])]
    rows = (len(have) + cols - 1) // cols
    sheet = Image.new("RGBA", (cols * cell, rows * cell), (0, 0, 0, 0))
    names = []
    for i, e in enumerate(have):
        im = Image.open(find(e["key"])).convert("RGBA").resize((cell, cell), Image.LANCZOS)
        sheet.paste(im, ((i % cols) * cell, (i // cols) * cell))
        names.append(e["key"])
    os.makedirs(out_dir, exist_ok=True)
    dest = os.path.join(out_dir, "tng_portraits.png")
    sheet.save(dest)
    with open(os.path.join(out_dir, "tng_portraits.json"), "w") as f:
        json.dump(names, f, indent=1)
    print("tng_portraits.png  %dx%d  %d of %d slots  grid %dx%d"
          % (sheet.size[0], sheet.size[1], len(names), cols * rows, cols, rows))
    print("  -> tng_register_portraits must be called with (%d, %d)" % (cols, rows))
    return cols, rows, len(names)


def print_registry(out_dir, sheets, pack_version):
    """The allFaceFiles.txt lines to paste, for an engine that cannot register a sheet.

    Since engine 1.3.15 tng_register_faces hands each sheet to the engine itself (verified
    with a stock file on the exe of 2026-10-14); these lines are for an older engine, and
    for an early 1.3.15 exe that could only re-point a tag this file already named."""
    print("\n" + "=" * 72)
    print("Only if the engine cannot take the sheets itself (see tng_register_faces),")
    print("paste into <cosmos>/data/graphics/allFaceFiles.txt (engine-owned):")
    for name, _ in sheets:
        alias = "tng%s" % name.split("_")[-1]
        print("%s ../missions/__lib__/media/ScornMandark.Cosmos-TNG-Mod.media.%s/faces_tng/%s"
              % (alias, pack_version, name))
    print("=" * 72)
    print("NOTE the version is baked into these paths. Bumping the media pack "
          "version silently breaks every face until this file is re-pasted.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--roster", default=os.path.join(HERE, "face_roster.json"))
    ap.add_argument("--cells", action="append", default=None,
                    help="cell directory; repeatable, earlier wins")
    ap.add_argument("-o", "--out", default=os.path.join(HERE, "out", "sheets"))
    ap.add_argument("--pack-version", default="v0.3.0")
    a = ap.parse_args()
    cells = a.cells or [os.path.join(HERE, "out", "cells_named"),
                        os.path.join(HERE, "out", "cells_generated")]
    sheets, faces, missing = build(a.roster, cells, a.out)
    build_portraits(a.roster, cells, a.out)
    print_registry(a.out, sheets, a.pack_version)
    for name, _ in sheets:
        p = os.path.join(a.out, name + ".png")
        print("%s sha256:%s" % (name, hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]))


if __name__ == "__main__":
    main()
