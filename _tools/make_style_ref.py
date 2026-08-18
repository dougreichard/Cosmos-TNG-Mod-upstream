"""Bootstrap the frozen IPAdapter style reference for the new house style.

WHY A MONTAGE AND NOT ONE PICTURE. IPAdapter "style transfer" carries palette as
well as rendering. Measured with a single reference cell (the gold TOS Kirk bust):
at ip_weight 0.9 every subject came back in a gold uniform - Picard's crimson, the
Ferengi's patterned jacket, all gold. A reference spanning several uniform colors
has no single palette to donate, so the subject's own colors survive.

WHY TWO STAGES. Neither checkpoint will stylize from prompt wording alone; the
style board proved that (three very different style prompts produced three nearly
identical semi-realistic rows on both Juggernaut and OpenDalle). So the new style
cannot be written into existence - it has to be pulled out with an IPAdapter
reference that does not exist yet.

  stage A  montage four EXISTING cells chosen for color spread (TNG crimson, TOS
           gold, TOS blue, civilian plum). This is a scaffold, not the answer: it
           only has to get the model into outline-and-flat-color territory while
           leaving colors alone.
  stage B  generate the four NEW-style busts through that scaffold at ip 0.6 - the
           weight measured to apply style while preserving color and identity -
           prompting for the heavier line weight and deeper palette that make this
           a new house style rather than a sharper copy of the old one.
  freeze   montage stage B into style_ref.png. Every cell in the set inherits its
           look from that one file, so it is frozen alongside rig_depth.png and
           must never be edited in place.

The style deliberately keeps bold outlines and flat color. That is not nostalgia:
measured on the style board, semi-realistic renders turn muddy and blur together at
the ~64px gui_face actually draws, while outline-and-flat-color stays legible.
"""
import argparse
import hashlib
import os

from PIL import Image

import facegen

HERE = os.path.dirname(os.path.abspath(__file__))
CELLS = os.path.join(HERE, "..", "new", "work", "facecells")
SCAFFOLD = os.path.join(HERE, "out", "style_scaffold.png")
FROZEN = os.path.join(HERE, "style_ref.png")

# Chosen for COLOR SPREAD, not for who they are.
SCAFFOLD_CELLS = [
    ("c08r00", "picard - TNG crimson"),
    ("c00r00", "kirk   - TOS gold"),
    ("c01r00", "spock  - TOS blue"),
    ("c14r01", "guinan - civilian plum"),
]

# The new house style lives in facegen.STYLE_TEXT so there is exactly one copy.
NEW_STYLE = facegen.STYLE_TEXT

# Four subjects spanning the same color range as the scaffold, so the frozen
# reference inherits the spread instead of a single dominant hue.
STAGE_B = [
    ("cmd_red", 201, "a bald elderly human man with a lined severe face, wearing a "
                     "starfleet uniform with black shoulders and a deep CRIMSON RED "
                     "chest panel and high grey collar"),
    ("ops_gold", 202, "a broad-shouldered human man with short dark hair and a trimmed "
                      "beard, wearing a starfleet uniform with black shoulders and a "
                      "MUSTARD GOLD chest panel"),
    ("sci_teal", 203, "a human woman with tan skin and dark hair tied back, wearing a "
                      "starfleet uniform with black shoulders and a TEAL BLUE chest panel"),
    ("civ_plum", 204, "a klingon with a tall ridged forehead crest and long black hair, "
                      "wearing deep PLUM and brown civilian robes"),
]


def montage(paths, dest, size=1024):
    """2x2 at half scale each - IPAdapter reads the whole frame, so four quadrants
    give it four palettes and one consistent rendering style to average over."""
    h = size // 2
    out = Image.new("RGB", (size, size), (235, 235, 238))
    for i, p in enumerate(paths):
        im = Image.open(p).convert("RGBA")
        flat = Image.new("RGBA", im.size, (235, 235, 238, 255))
        flat.alpha_composite(im)                       # cells are cutouts; flatten first
        out.paste(flat.convert("RGB").resize((h, h), Image.LANCZOS),
                  ((i % 2) * h, (i // 2) * h))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    out.save(dest)
    return dest


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ckpt", default="openDalle_v11.safetensors")
    ap.add_argument("--server", default="127.0.0.1:8188")
    ap.add_argument("--ip-weight", type=float, default=0.6)
    ap.add_argument("--candidates", type=int, default=2)
    ap.add_argument("--stage-b-only", action="store_true")
    a = ap.parse_args()

    # --- stage A -------------------------------------------------------------
    paths = [os.path.join(CELLS, n + ".png") for n, _ in SCAFFOLD_CELLS]
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        raise SystemExit("missing scaffold cells: " + ", ".join(missing))
    montage(paths, SCAFFOLD)
    print("stage A scaffold ->", SCAFFOLD)
    for n, why in SCAFFOLD_CELLS:
        print("   ", n, why)

    # --- stage B -------------------------------------------------------------
    out = os.path.join(HERE, "out", "styleref")
    jobs = [{"key": n, "candidate": c, "seed": seed + c * 37, "prompt": p + ", " + NEW_STYLE}
            for n, seed, p in STAGE_B for c in range(a.candidates)]
    facegen.run(jobs, a.server, a.ckpt, os.path.join(HERE, "rig_depth.png"),
                SCAFFOLD, out, 30, 6.5, 0.25, a.ip_weight, 1024, 0.5)
    print("\nstage B candidates in", out)
    print("Pick one per subject, then freeze:")
    print("  python make_style_ref.py --freeze <cmd_red> <ops_gold> <sci_teal> <civ_plum>")


def freeze(paths):
    montage(paths, FROZEN)
    h = hashlib.sha256(open(FROZEN, "rb").read()).hexdigest()[:16]
    print("style_ref.png sha256:%s" % h)
    print("FROZEN. Regenerating any cell against a different style_ref.png or "
          "rig_depth.png will not match the rest of the set.")


if __name__ == "__main__":
    import sys
    if "--freeze" in sys.argv:
        i = sys.argv.index("--freeze")
        freeze(sys.argv[i + 1:])
    else:
        main()
