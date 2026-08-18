"""Generate the style board that decides the house style, then freeze the winner.

This is the gate the whole set hangs on. Once ~360 cells are generated against a
style reference, changing the style means regenerating all of them, so the choice
is made once, deliberately, against the hard cases rather than against a flattering
one.

SUBJECTS are picked to break a style rather than show it off:
  picard   an ordinary human face - nowhere to hide a weak likeness
  worf     heavy prosthetic ridges, long hair, dark skin tones
  seven    hard metallic implants next to skin, the sternest surface-mix test
  romulan  a face that must NOT read as vulcan or human
  ensign   a plain background character - most of the set looks like this
  ferengi  extreme caricature proportions, huge ears, orange-brown skin

Seeds are fixed per subject, so a difference between two panels is the style or
the checkpoint and never the roll.

The board is rendered twice: full size, and at the size gui_face actually draws.
A style that only works at 512 is not a style this set can use - most faces are
seen small, and heavy linework that reads as detail at full size turns to mud.

    python styleboard.py --ckpt juggernautXL_v9.safetensors --ckpt openDalle_v11.safetensors
    # then, once chosen:
    python styleboard.py --freeze out/board/<ckpt>/<style>_<subject>.png
"""
import argparse
import os
import shutil

from PIL import Image, ImageDraw

import facegen

HERE = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.join(HERE, "out", "board")
FROZEN = os.path.join(HERE, "style_ref.png")

# Three genuinely different directions, not three phrasings of one. The user asked
# for a NEW house style, so "match the existing set" is deliberately not on the board.
STYLES = {
    "cel": ("comic book illustration, bold clean black ink outlines, flat cel shading, "
            "limited flat color palette, crisp graphic shapes"),
    "painted": ("digital painted portrait illustration, soft blended shading, subtle "
                "linework, rich saturated color, graphic novel painting"),
    "screenprint": ("retro screenprint poster illustration, heavy simplified shapes, "
                    "two-tone shading, halftone texture, bold silhouette, vintage "
                    "science fiction paperback cover art"),
}

SUBJECTS = [
    ("picard", 101, "a bald elderly human man with a lined severe face and a strong nose, "
                    "wearing a starfleet uniform with black shoulders and a crimson red "
                    "chest panel, high grey collar"),
    ("worf", 102, "a klingon man with a tall ridged forehead crest, deep-set eyes, dark "
                  "brown skin, long black hair tied back and a beard, wearing a starfleet "
                  "uniform with a metallic baldric sash"),
    ("seven", 103, "a blonde woman with her hair in a tight twist, a silver metallic "
                   "implant arcing over her left eyebrow and a small implant on her cheek, "
                   "wearing a plain silver-grey bodysuit"),
    ("romulan", 104, "a romulan officer with pointed ears, a V-shaped forehead ridge and a "
                     "heavy blunt black fringe, wearing a grey and green quilted tunic with "
                     "angular padded shoulders"),
    ("ensign", 105, "a young human woman with tan skin and a dark ponytail, wearing a "
                    "starfleet uniform with black shoulders and a mustard gold chest panel"),
    ("ferengi", 106, "a ferengi with enormous lobed ears, a wrinkled orange-brown domed "
                     "skull, sharp teeth and a sly grin, wearing a loud patterned jacket"),
]


def generate(ckpts, server, steps, cfg, cn_strength, cn_end):
    for ckpt in ckpts:
        tag = os.path.splitext(ckpt)[0]
        out = os.path.join(BOARD, tag)
        jobs = []
        for style, suffix in STYLES.items():
            for name, seed, subject in SUBJECTS:
                jobs.append({"key": "%s_%s" % (style, name), "candidate": 0,
                             "seed": seed, "prompt": subject + ", " + suffix})
        print("=== %s: %d panels ===" % (tag, len(jobs)), flush=True)
        facegen.run(jobs, server, ckpt, os.path.join(HERE, "rig_depth.png"), None,
                    out, steps, cfg, cn_strength, 0.8, 1024, cn_end)


def contact(ckpts):
    """One sheet per checkpoint: styles down, subjects across, plus a small-size strip."""
    for ckpt in ckpts:
        tag = os.path.splitext(ckpt)[0]
        d = os.path.join(BOARD, tag)
        if not os.path.isdir(d):
            continue
        T, SMALL, PAD = 300, 64, 26
        W = T * len(SUBJECTS)
        H = (T + PAD) * len(STYLES) + SMALL + PAD * 2
        sheet = Image.new("RGB", (W, H), (24, 24, 30))
        dr = ImageDraw.Draw(sheet)
        dr.text((6, 6), "%s   -   styles down, subjects across" % tag, fill=(240, 240, 160))
        for r, style in enumerate(STYLES):
            y = PAD + r * (T + PAD)
            dr.text((6, y - 16), style, fill=(200, 220, 255))
            for c, (name, _, _) in enumerate(SUBJECTS):
                p = os.path.join(d, "%s_%s_c0.png" % (style, name))
                if os.path.exists(p):
                    sheet.paste(Image.open(p).convert("RGB").resize((T, T)), (c * T, y))
                if r == 0:
                    dr.text((c * T + 6, PAD - 16), name, fill=(160, 220, 160))
        # The small strip: every style at the size gui_face actually draws.
        y = PAD + len(STYLES) * (T + PAD)
        dr.text((6, y - 16), "as drawn (%dpx)" % SMALL, fill=(255, 200, 140))
        x = 0
        for style in STYLES:
            for name, _, _ in SUBJECTS:
                p = os.path.join(d, "%s_%s_c0.png" % (style, name))
                if os.path.exists(p):
                    sheet.paste(Image.open(p).convert("RGB").resize((SMALL, SMALL)), (x, y))
                x += SMALL + 4
        dest = os.path.join(BOARD, "board_%s.png" % tag)
        sheet.save(dest)
        print("wrote", dest)


def freeze(src):
    """Copy the chosen panel to style_ref.png - the frozen IPAdapter reference.

    Everything after this point inherits its style from this one file, so it is
    version-controlled with the sheets and must not be edited in place.
    """
    shutil.copy2(src, FROZEN)
    import hashlib
    h = hashlib.sha256(open(FROZEN, "rb").read()).hexdigest()[:16]
    print("style_ref.png <- %s\nsha256:%s\nFREEZE THIS with rig_depth.png." % (src, h))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ckpt", action="append", default=None)
    ap.add_argument("--server", default="127.0.0.1:8188")
    ap.add_argument("--steps", type=int, default=30)
    ap.add_argument("--cfg", type=float, default=6.5)
    ap.add_argument("--cn-strength", type=float, default=0.25)
    ap.add_argument("--cn-end", type=float, default=0.5)
    ap.add_argument("--contact-only", action="store_true")
    ap.add_argument("--freeze", default=None, help="panel to adopt as the style reference")
    a = ap.parse_args()

    if a.freeze:
        freeze(a.freeze)
        return
    ckpts = a.ckpt or ["juggernautXL_v9.safetensors", "openDalle_v11.safetensors"]
    if not a.contact_only:
        generate(ckpts, a.server, a.steps, a.cfg, a.cn_strength, a.cn_end)
    contact(ckpts)


if __name__ == "__main__":
    main()
