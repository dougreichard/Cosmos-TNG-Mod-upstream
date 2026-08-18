"""Build face_roster.json - the cell list facegen.py and facesheets.py both read.

Sized by what the MOD needs, not by what the prototype happened to contain.

The old roster carried every key from new/work/cells_manifest.json forward, which
meant inheriting the prototype's shape: 255 Federation faces against 8 Kazon, 6
Orion and 9 Romulan - even though the mod ships hulls AND fleets for all of them.
That distribution came from whatever the first sheet was drawn with, and treating
it as fixed starved exactly the factions a mission spends time fighting.

So the pools are allocated per FACTION, weighted by how much of the mod a faction
actually is: a playable faction with a fleet ladder needs enough faces that a crowd
does not visibly repeat, while a species that appears once needs two or three.

Keys already carrying finished art are pinned and never renamed (see PINNED below).

Target is 320 cells = exactly 5 full sheets of 64, packed in era order so a sheet is
reviewable as a unit and a re-roll touches one sheet.

TWO KINDS OF CELL
  base     a whole bust. Most cells.
  overlay  hardware that sits ON a face - Borg implants, a VISOR - drawn against the
           same rig so it registers over any base. A key whose "layers" list names
           several cells composites them: "tng5 #fff 2 1;tng5 #fff 5 3;".
           Anything that changes the skull silhouette (Klingon ridges, Ferengi lobes)
           is baked into the base instead; only surface hardware can be an overlay.

TWO MODES
  from-cell  img2img over the existing 512 cell. Only for the identified characters,
             where inheriting identity from art that already reads as the right
             person beats anything a prompt can do on SDXL without a character LoRA.
  txt2img    everything else, including ALL of Voyager - there is no VOY art to
             inherit from, so those leads are generated cold and will need the most
             candidates.
"""
import argparse
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, "..", "new", "work", "cells_manifest.json")

# Style is carried by the IPAdapter reference, not by prompt wording, so these
# prompts describe SUBJECT only. Keep them concrete: species marks, uniform, age,
# build, hair, expression. SDXL rewards specific nouns and ignores adjectives.

# --- uniforms -----------------------------------------------------------------
# Division colour flips between eras, which is exactly the sort of detail that makes
# a set look researched or careless. TOS: command gold, sciences blue, ops red.
# TNG S3+ and later: command red, ops/security gold, sciences/medical teal.
TOS_DIV = {"command": "mustard gold", "science": "sky blue", "medical": "sky blue",
           "ops": "brick red", "civilian": None}
MOD_DIV = {"command": "crimson red", "science": "teal", "medical": "teal",
           "ops": "mustard gold", "civilian": None}

UNIFORM = {
    "tos": "a {c} 1960s starfleet velour tunic with a black collar and a gold delta insignia",
    "tng": "a starfleet uniform with black shoulders and a {c} chest panel, high grey collar, combadge",
    "ds9": "a grey-shouldered starfleet jumpsuit with a {c} yoke and black torso, high collar, combadge",
    "voy": "a grey-shouldered starfleet jumpsuit with a {c} yoke and black torso, high collar, combadge",
}
CIVILIAN = {
    "tos": "a plain civilian tunic in muted colors",
    "tng": "soft civilian robes in muted earth tones",
    "ds9": "a practical civilian jacket in worn brown and grey",
    "voy": "a practical civilian jacket in worn brown and grey",
}


def uniform(era, role):
    if role == "civilian":
        return CIVILIAN[era]
    div = TOS_DIV if era == "tos" else MOD_DIV
    return UNIFORM[era].format(c=div.get(role) or "grey")


# --- species ------------------------------------------------------------------
# Only the marks that survive at the size gui_face draws. Fine detail is wasted.
SPECIES = {
    "human":     "a human",
    "vulcan":    "a vulcan with upswept eyebrows, pointed ears and a severe blunt fringe",
    "romulan":   "a romulan with pointed ears, a V-shaped forehead ridge and a heavy blunt fringe",
    "klingon":   "a klingon with a tall ridged forehead crest, deep-set eyes, long wild hair and a beard",
    "cardassian":"a cardassian with grey scaled skin, a spoon-shaped forehead indent, thick neck cords and black swept-back hair",
    "bajoran":   "a bajoran with a ridged nose bridge and a beaded earring on the right ear",
    "ferengi":   "a ferengi with an enormous lobed ears, a wrinkled orange-brown domed skull and sharp teeth",
    "trill":     "a trill with a line of brown leopard spots running down the temples and neck",
    "andorian":  "an andorian with blue skin, white hair and two antennae on the forehead",
    "tellarite": "a tellarite with a broad porcine snout, tusks and coarse bristled hair",
    "vorta":     "a vorta with violet eyes, pale skin and large ridged ears",
    "jemhadar":  "a jem'hadar with grey scaled skin, a keratin horn on the forehead and spined ridges",
    "breen":     "a breen in a full snouted refrigeration helmet with a green optical visor, no face visible",
    "kazon":     "a kazon with a broad ridged forehead and a huge upswept mane of matted hair",
    "orion":     "an orion with bright green skin and thick black hair",
    "gorn":      "a gorn reptilian with green pebbled scales, a heavy brow and faceted compound eyes",
    "talaxian":  "a talaxian with mottled yellow and brown skin, spotted temples and a tuft of ginger hair",
    "ocampa":    "an ocampa with delicate features, short pale hair and small ridged ears",
    "vidiian":   "a vidiian with severely necrotic patchwork skin, mismatched grafts and sunken eyes",
    "hirogen":   "a hirogen hunter with mottled grey hide, a broad heavy brow and a long braided topknot",
    "species8472":"a tall alien with pale ridged chitin skin, three-lobed eyes and no hair",
    "benzite":   "a benzite with smooth blue-grey skin, a high domed hairless skull and a small breathing apparatus at the chest",
    "hologram":  "a person rendered as a luminous blue holographic projection, translucent, scanline-lit",
    "borg":      "a borg drone with grey exsanguinated skin and black veins",

}

RACE_DRESS = {
    "klingon":   "wearing ridged klingon battle armour with a metallic baldric",
    "romulan":   "wearing a grey and green quilted romulan tunic with angular shoulders",
    "cardassian":"wearing black and grey cardassian armour with a raised neck plate",
    "kazon":     "wearing layered scavenged leather and metal armour",
    "jemhadar":  "wearing dark grey jem'hadar combat armour",
    "vorta":     "wearing a high-collared mauve dominion tunic",
    "breen":     "wearing a full breen refrigeration suit",
    "bajoran":   "wearing a rust-brown bajoran militia jacket",
    "ferengi":   "wearing a loud patterned ferengi jacket",
    "orion":     "wearing an ornate sleeveless tunic",
    "talaxian":  "wearing a colorful patchwork tunic",
    "ocampa":    "wearing a soft pale tunic",
    "vidiian":   "wearing a drab medical smock",
    "hirogen":   "wearing heavy hirogen hunter armour",
    "species8472":"bare chitinous shoulders",
    "gorn":      "wearing a simple metallic harness",
    "vulcan":    "wearing a formal vulcan robe with a high collar",
    "andorian":  "wearing an imperial guard tunic",
    "tellarite": "wearing a heavy utilitarian tunic",
    "trill":     "wearing a civilian tunic in muted colors",
    "benzite":   "wearing a starfleet-style tunic with a chest respirator unit",
    "hologram":  "wearing a uniform rendered in the same luminous blue projection",
}


# --- variety axes for the generic pools ---------------------------------------
# Named explicitly so a pool does not come back as fifty of the same young white man,
# which is what an unqualified "a starfleet officer" prompt produces.
AGE = ["young", "in their thirties", "middle-aged", "older", "elderly"]
BUILD = ["slight", "lean", "broad-shouldered", "heavyset", "wiry"]
SKIN = ["dark brown skin", "deep black skin", "olive skin", "pale skin",
        "light brown skin", "tan skin", "freckled fair skin"]
HAIR = ["close-cropped black hair", "long braided black hair", "short grey hair",
        "a shaved head", "tight dark curls", "a blonde bob", "auburn hair tied back",
        "a neat brown side part", "silver hair swept back", "a dark ponytail",
        "short red hair", "long straight black hair", "a greying beard and short hair",
        "a bald head and a moustache", "chin-length brown hair"]
EXPR = ["a calm neutral expression", "a faint confident smile", "a stern set jaw",
        "an alert focused look", "raised eyebrows", "a weary expression"]

# Species whose SPECIES entry already states hair. Appending a HAIR axis to these
# produced contradictions - a klingon with "long wild hair and a beard, auburn hair
# tied back" - so the axis is skipped and the species description wins.
HAIR_IN_SPECIES = {"klingon", "cardassian", "kazon", "talaxian", "ocampa", "hirogen",
                   "vulcan", "romulan", "orion", "andorian", "tellarite"}
# No hair to describe at all.
HAIRLESS = {"breen", "species8472", "gorn", "jemhadar", "borg", "vidiian"}
# No visible face, so an expression axis is meaningless: a Breen is a sealed helmet.
NO_FACE = {"breen"}


def race_prompt(race, i):
    """A non-Federation character: own species marks, own dress, no starfleet uniform."""
    bits = [AGE[i % len(AGE)], BUILD[(i * 3) % len(BUILD)], SPECIES[race]]
    if race not in HAIR_IN_SPECIES and race not in HAIRLESS:
        bits.append(HAIR[(i * 7) % len(HAIR)])
    bits.append(RACE_DRESS.get(race, "wearing dark utilitarian armour"))
    if race not in NO_FACE:
        bits.append(EXPR[(i * 11) % len(EXPR)])
    return ", ".join(bits)


def pool_prompt(era, role, race, i):
    """Deterministic spread over the variety axes - same index, same person."""
    bits = [AGE[i % len(AGE)], BUILD[(i * 3) % len(BUILD)],
            SPECIES.get(race, SPECIES["human"])]
    if race in ("human", "trill", "bajoran", "betazoid"):
        bits.append(SKIN[(i * 5) % len(SKIN)])
    bits.append(HAIR[(i * 7) % len(HAIR)])
    bits.append("wearing " + uniform(era, role))
    bits.append(EXPR[(i * 11) % len(EXPR)])
    return ", ".join(bits)


# --- the identified characters -------------------------------------------------
# Deliberately described rather than named. A prompt that leans on the actor's name
# gets whatever SDXL happens to associate with it; a description of the face gets
# the same result more reliably and degrades into a plausible archetype when the
# likeness does not land, which is the honest failure mode for this set.
NAMED = {
    # --- TOS
    "kirk":      ("tos", "human", "command", "a confident square-jawed human man in his thirties, short side-parted light brown hair, wearing {u}"),
    "kirk_alt":  ("tos", "human", "command", "a human starfleet captain in his forties, short brown hair, lined face, wearing a green wraparound tunic"),
    "spock":     ("tos", "vulcan", "science", "a stern vulcan man with a severe black bowl-cut fringe, upswept eyebrows, pointed ears, wearing {u}"),
    "spock_alt": ("tos", "vulcan", "science", "an older vulcan man, black bowl-cut fringe greying at the temples, upswept eyebrows, wearing a grey vulcan robe"),
    "mccoy":     ("tos", "human", "medical", "a wry human doctor in his fifties, receding brown hair, deep frown lines, wearing {u}"),
    "mccoy_alt": ("tos", "human", "medical", "an elderly human doctor, thin white hair, heavily lined face, wearing a blue medical tunic"),
    "chekov":    ("tos", "human", "ops", "a very young human man with a mop of dark brown hair, wearing {u}"),
    "chapel":    ("tos", "human", "medical", "a human nurse, blonde hair pinned up, calm expression, wearing a white medical tunic"),
    "uhura":     ("tos", "human", "ops", "a human woman with deep black skin, hair swept up, large gold hoop earrings, wearing {u}"),
    # Scotty and Sulu were missing outright - TOS main cast with no cell, which the
    # Gemini cast grid made obvious by supplying both.
    "scotty":    ("tos", "human", "ops", "a human engineer in his forties with dark side-parted hair and a broad face, wearing {u}"),
    "sulu":      ("tos", "human", "ops", "a human helmsman of japanese descent with neat black hair and a confident half-smile, wearing {u}"),
    # --- TNG
    "picard":    ("tng", "human", "command", "a bald elderly human man with a lined severe face and a strong nose, wearing {u}"),
    "picard_alt":("tng", "human", "command", "a bald elderly human man, lined face, wearing a maroon and grey command jacket"),
    "riker":     ("tng", "human", "command", "a broad-shouldered human man with dark brown hair and a full trimmed beard, wearing {u}"),
    "riker_alt": ("tng", "human", "command", "a broad-shouldered human man, dark hair, clean shaven, wearing {u}"),
    "data":      ("tng", "android", "ops", "an android man with uniformly pale gold skin, bright yellow-gold eyes and slicked-back black hair, wearing {u}"),
    "data_alt":  ("tng", "android", "ops", "an android man with pale gold skin and gold eyes, slicked-back black hair with a grey streak, wearing {u}"),
    "worf":      ("tng", "klingon", "ops", "a klingon man with a tall ridged forehead crest, long black hair tied back, a beard, wearing {u} and a metallic sash"),
    "worf_alt":  ("ds9", "klingon", "ops", "a klingon man with a ridged forehead crest, long black hair, a beard, wearing {u} and a metallic sash"),
    "troi":      ("tng", "betazoid", "science", "a woman with long wavy dark brown hair and large dark eyes, wearing a teal blue jumpsuit"),
    "troi_alt":  ("tng", "betazoid", "science", "a woman with dark hair worn in a tight bun, large dark eyes, wearing {u}"),
    "beverly_crusher": ("tng", "human", "medical", "a human woman doctor with long straight red hair and pale skin, wearing a blue medical jumpsuit"),
    "tasha_yar": ("tng", "human", "ops", "a human woman with very short cropped blonde hair and a determined expression, wearing {u}"),
    "guinan":    ("tng", "elaurian", "civilian", "a serene woman with deep black skin wearing an enormous wide-brimmed fabric hat and flowing plum robes"),
    "geordi":    ("tng", "human", "ops", "a human man with dark brown skin wearing a curved golden metal visor across his eyes, wearing {u}"),
    "wesley":    ("tng", "human", "command", "a teenage human boy with short brown hair, wearing a grey and rust cadet jumpsuit"),
    "obrien":    ("tng", "human", "ops", "a stocky human man with short receding brown hair and a broad honest face, wearing {u}"),
    "pulaski":   ("tng", "human", "medical", "a human woman doctor in her fifties with short blonde hair, wearing a blue medical jumpsuit"),
    "barclay":   ("tng", "human", "ops", "an anxious human man with thinning brown hair and a nervous expression, wearing {u}"),
    "q":         ("tng", "human", "command", "a smirking human man with short dark hair and an arch amused expression, wearing {u}"),
    "lore":      ("tng", "android", "civilian", "an android man with pale gold skin and gold eyes, slicked-back black hair, a cruel smile, wearing a dark jumpsuit"),
    # --- DS9
    "sisko":     ("ds9", "human", "command", "a human man with deep black skin, a shaved head and a greying goatee, wearing {u}"),
    "sisko_alt": ("ds9", "human", "command", "a human man with deep black skin, a shaved head and a greying goatee, wearing an ornate gold-trimmed bajoran ceremonial robe"),
    "kira":      ("ds9", "bajoran", "command", "a bajoran woman with short red-brown hair, a ridged nose bridge and a beaded right earring, wearing {u}"),
    "kira_alt":  ("ds9", "bajoran", "command", "a bajoran woman with short red-brown hair and a ridged nose bridge, wearing a rust-brown bajoran militia jacket"),
    "odo":       ("ds9", "changeling", "ops", "a man with a smooth unfinished face, barely-formed features and slicked-back fair hair, wearing a plain rust-brown jumpsuit"),
    "quark":     ("ds9", "ferengi", "civilian", "a ferengi with enormous lobed ears and a wrinkled domed skull, a sly grin, wearing a loud patterned gold jacket"),
    "rom":       ("ds9", "ferengi", "ops", "a ferengi with enormous lobed ears, an anxious overbite and a hesitant expression, wearing a drab work tunic"),
    "nog":       ("ds9", "ferengi", "ops", "a young ferengi with large lobed ears and an eager expression, wearing a starfleet cadet jumpsuit"),
    "bashir":    ("ds9", "human", "medical", "a young human doctor with light brown skin, short dark hair and an eager expression, wearing {u}"),
    "dax":       ("ds9", "trill", "science", "a trill woman with brown leopard spots down her temples and neck, long dark hair, wearing {u}"),
    "ezri":      ("ds9", "trill", "medical", "a small young trill woman with brown spots down her temples, short dark hair, wearing {u}"),
    "garak":     ("ds9", "cardassian", "civilian", "a cardassian with grey scaled skin, a spoon-shaped forehead indent and an affable smile, wearing an ornate tailored civilian tunic"),
    "dukat":     ("ds9", "cardassian", "command", "a cardassian with grey scaled skin, a spoon-shaped forehead indent and a smug expression, wearing black cardassian armour"),
    "jake":      ("ds9", "human", "civilian", "a teenage human boy with deep black skin and short hair, wearing a casual civilian shirt"),
    # DS9's recurring cast carries as much of the station's drama as the main crew,
    # and a mission set on DS9 that cannot show Martok, Weyoun or Winn is missing the
    # faces players actually talk to.
    "martok":    ("ds9", "klingon", "command", "a one-eyed klingon general with a tall ridged forehead crest, a wild grey-streaked mane and beard, a scarred empty left eye socket, wearing ridged klingon battle armour"),
    "gowron":    ("ds9", "klingon", "command", "a klingon chancellor with enormous staring wide-open eyes, a ridged forehead crest and long dark curled hair, wearing ornate klingon robes"),
    "weyoun":    ("ds9", "vorta", "command", "a vorta with violet eyes, pale skin, large ridged ears and a sleek dark bowl-cut, an unctuous smile, wearing a high-collared mauve dominion tunic"),
    "damar":     ("ds9", "cardassian", "command", "a cardassian officer with grey scaled skin, a spoon-shaped forehead indent and short dark hair, a hard grim expression, wearing black cardassian armour"),
    "kai_winn":  ("ds9", "bajoran", "civilian", "an older bajoran woman with a ridged nose bridge, a serene insincere smile, wearing an elaborate gold and cream bajoran clerical headdress and robes"),
    "leeta":     ("ds9", "bajoran", "civilian", "a young bajoran woman with a ridged nose bridge, long wavy auburn hair and a bright smile, wearing a colorful civilian top"),
    "brunt":     ("ds9", "ferengi", "civilian", "a ferengi liquidator with enormous lobed ears, a wrinkled orange-brown domed skull and a sour officious expression, wearing a drab brown ferengi commission uniform"),
    "zek":       ("ds9", "ferengi", "civilian", "a very old ferengi grand nagus with enormous lobed ears, a deeply wrinkled orange-brown skull, hunched posture, wearing ornate gold-trimmed robes and holding nothing"),
    "eddington": ("ds9", "human", "ops", "a human starfleet security officer with short greying hair and a neat beard, a guarded expression, wearing {u}"),
    "bareil":    ("ds9", "bajoran", "civilian", "a calm bajoran vedek with a ridged nose bridge and short dark hair, wearing simple brown and orange bajoran clerical robes"),
    # --- VOY  (no existing art: all txt2img, all cold)
    "janeway":   ("voy", "human", "command", "a human woman starfleet captain in her forties, auburn hair in a tight bun, a firm set jaw, wearing {u}"),
    "chakotay":  ("voy", "human", "command", "a human man with light brown skin, short black hair and a small angular tattoo above his left eyebrow, wearing {u}"),
    "tuvok":     ("voy", "vulcan", "ops", "a vulcan man with deep black skin, upswept eyebrows, pointed ears and a severe fringe, wearing {u}"),
    "torres":    ("voy", "klingon", "ops", "a half-klingon woman with light brown skin, subtle forehead ridges and dark hair pulled back, wearing {u}"),
    "paris":     ("voy", "human", "command", "a human man with short sandy blonde hair and a cocky half-smile, wearing {u}"),
    "kim":       ("voy", "human", "ops", "a young human man of east asian descent with neat black hair, wearing {u}"),
    "the_doctor":("voy", "hologram", "medical", "a bald man with an impassive clinical expression, wearing {u}"),
    "neelix":    ("voy", "talaxian", "civilian", "a talaxian with mottled yellow skin, spotted temples, a tuft of ginger whiskers and a cheerful grin, wearing a patchwork chef's tunic"),
    "kes":       ("voy", "ocampa", "medical", "a delicate young woman with very short pale blonde hair and small ridged ears, wearing a soft lilac tunic"),
    "seven_of_nine": ("voy", "human", "science", "a blonde woman with her hair in a tight twist, a silver metallic implant arcing over her left eyebrow and a small implant on her cheek, wearing a plain silver-grey bodysuit"),
}

# --- Borg: bases + overlays ----------------------------------------------------
# 4 bases x 10 overlays covers far more drones than 14 whole-drone cells could, and
# the overlays double as the assimilation layer MAST can append to ANY face.
BORG_BASES = [
    ("borg_base_human",     "a human drone with grey exsanguinated skin, black veins and a shaved head, wearing black borg exoskeleton armour"),
    ("borg_base_klingon",   "a klingon drone with grey exsanguinated skin, a ridged forehead crest and black veins, wearing black borg exoskeleton armour"),
    ("borg_base_bajoran",   "a bajoran drone with grey exsanguinated skin, a ridged nose bridge and black veins, wearing black borg exoskeleton armour"),
    ("borg_base_female",    "a woman drone with grey exsanguinated skin, black veins and a bald head, wearing black borg exoskeleton armour"),
]
BORG_OVERLAYS = [
    ("borg_impl_ocular_l",  "a single silver metallic ocular implant apparatus over the LEFT eye with a small red laser emitter, isolated hardware only"),
    ("borg_impl_ocular_r",  "a single silver metallic ocular implant apparatus over the RIGHT eye with a small red laser emitter, isolated hardware only"),
    ("borg_impl_brow",      "a slim silver metallic implant arc above the left eyebrow, isolated hardware only"),
    ("borg_impl_cheek",     "a small silver metallic plate implant on the left cheekbone, isolated hardware only"),
    ("borg_impl_cranial",   "a curved silver metallic plate covering the left side of the skull, isolated hardware only"),
    ("borg_impl_temple",    "a silver metallic disc implant at the temple with fine cabling, isolated hardware only"),
    ("borg_impl_jaw",       "a silver metallic mandible brace along the jawline, isolated hardware only"),
    ("borg_impl_tubes",     "black corrugated tubing running from the neck up behind the ear, isolated hardware only"),
    ("borg_impl_neck",      "a silver metallic collar plate around the base of the neck, isolated hardware only"),
    ("borg_impl_crown",     "a silver metallic band across the crown of the skull with small emitters, isolated hardware only"),
]
# Other surface hardware. Same mechanism, nothing to do with the Borg.
GEAR_OVERLAYS = [
    ("gear_visor",          "a curved golden metal visor spanning the eyes with silver temple clamps, isolated hardware only"),
    ("gear_scar_left",      "a long pale scar down the left cheek, isolated mark only"),
    ("gear_eyepatch",       "a plain black eyepatch over the right eye with a thin strap, isolated hardware only"),
    ("gear_breather",       "a small transparent respirator cup over the nose and mouth with side tubing, isolated hardware only"),
]

# Composed characters: a base plus overlays, as a face string with several layers.
COMPOSED = {
    "seven_of_nine": ["seven_of_nine", "borg_impl_brow", "borg_impl_cheek"],
    "geordi":        ["geordi", "gear_visor"],
}

ERA_ORDER = ["tos", "tng", "ds9", "voy", "race", "overlay"]


def load_pinned():
    """Keys that already have art cut from a cast grid - never rename these."""
    p = os.path.join(HERE, "grid_keys.json")
    if not os.path.exists(p):
        return set()
    with open(p) as f:
        data = json.load(f)
    return {k for g, v in data.items() if not g.startswith("_") for k in v if k != "-"}


PINNED = load_pinned() if os.path.exists(os.path.join(HERE, "grid_keys.json")) else set()


def load_existing():
    with open(os.path.abspath(MANIFEST)) as f:
        man = json.load(f)
    return [m for m in man if not m.get("junk")]


def era_of(key):
    for e in ("tos", "tng", "ds9", "voy"):
        if key.startswith(e + "_"):
            return e
    return None


def role_of(key):
    for r in ("command", "ops", "science", "medical", "civilian"):
        if "_" + r + "_" in key:
            return r
    return "ops"


def build():
    cells = []
    seen = set()

    def add(key, era, race, role, prompt, mode="txt2img", kind="base",
            source_cell=None, group=None):
        if key in seen:
            return
        seen.add(key)
        e = {"key": key, "era": era, "race": race, "role": role, "kind": kind,
             "mode": mode, "prompt": prompt, "group": group or era}
        if source_cell:
            e["source_cell"] = source_cell
        cells.append(e)

    existing = load_existing()
    by_key = {m["key"]: m for m in existing}

    # 1. Named characters first, so they own their key before any pool claims it.
    for key, (era, race, role, tmpl) in NAMED.items():
        src = by_key.get(key)
        # from-cell only where art actually exists AND is not itself a duplicate:
        # seeding img2img from a cell the manifest already flagged as a copy of
        # another one would reproduce the duplication in the new set.
        usable = src and not src.get("duplicate_of")
        add(key, era, race, role,
            tmpl.format(u=uniform(era, role)),
            mode="from-cell" if usable else "txt2img",
            source_cell=src["name"] if usable else None,
            group=era)

    # 2. PINNED keys: any key that already has finished art. Those cells were cut
    #    from the cast grids and keyed by hand, so renaming one would orphan the art.
    #    Everything else from the prototype is free to go - it was a naming accident,
    #    not a requirement, and carrying 48 tng_ops_* slots forward is what crowded
    #    the Kazon and the Romulans out.
    for key in sorted(PINNED):
        if key in seen:
            continue
        era = era_of(key) or "tng"
        role = role_of(key)
        race = "human"
        for r in SPECIES:
            if key.startswith(r):
                race, era = r, "race"
                break
        idx = sum(ord(c) for c in key)
        prompt = (race_prompt(race, idx) if era == "race"
                  else pool_prompt(era, role, race, idx))
        add(key, era, race, role, prompt, group=era)

    # 3. Voyager pools - the era that has nothing at all today.
    # Federation crews, per era. Sized so a bridge or a corridor scene can be filled
    # without obvious repeats, and no larger: this is the pool that used to eat the
    # whole roster.
    for era, spec in (("tos", (("command", 5), ("ops", 8), ("science", 4),
                               ("medical", 3), ("civilian", 5))),
                      ("tng", (("command", 8), ("ops", 14), ("science", 6),
                               ("medical", 4), ("civilian", 8))),
                      ("ds9", (("command", 6), ("ops", 10), ("science", 4),
                               ("medical", 3), ("civilian", 10))),
                      ("voy", (("command", 5), ("ops", 10), ("science", 4),
                               ("medical", 3), ("civilian", 6)))):
        for role, n in spec:
            for i in range(1, n + 1):
                add("%s_%s_%02d" % (era, role, i), era, "human", role,
                    pool_prompt(era, role, "human", i * 3 + len(role)), group=era)
    # Maquis: VOY's other half of the crew, civilian-dressed on a starfleet ship.
    for i in range(1, 5):
        add("voy_maquis_%02d" % i, "voy", "human", "civilian",
            pool_prompt("voy", "civilian", "human", i * 5) +
            ", a maquis irregular in a patched leather jacket", group="voy")

    # 4. Race pools. Counts are weighted by how much the mod actually uses them:
    #    Kazon, Cardassian, Klingon and Romulan have ships and fleets; Gorn does not.
    # Weighted by the mod's own content. The first group are factions with hulls and
    # a fleet ladder - they crew ships the players will meet repeatedly, so they need
    # depth. The second are species that turn up as individuals; two or three each is
    # plenty. Federation depth comes from the era pools above, not from here.
    RACE_POOL = [
        # factions the mod ships fleets for
        ("klingon", 26), ("cardassian", 26), ("romulan", 24), ("kazon", 20),
        ("jemhadar", 18), ("orion", 14), ("breen", 12), ("vorta", 8),
        # recurring species, seen as individuals
        ("bajoran", 12), ("ferengi", 10), ("trill", 6), ("vulcan", 6),
        ("andorian", 5), ("tellarite", 4), ("benzite", 3),
        # Delta Quadrant, for the Voyager side of the mod
        ("talaxian", 5), ("ocampa", 4), ("hirogen", 5), ("vidiian", 4),
        ("species8472", 3),
        # odds and ends
        ("gorn", 3), ("hologram", 5),
    ]
    for race, n in RACE_POOL:
        for i in range(1, n + 1):
            role = ["command", "ops", "civilian", "science"][i % 4]
            add("%s_%02d" % (race, i), "race", race, role, race_prompt(race, i),
                group="race")

    # 5. Borg bases and every overlay.
    for key, prompt in BORG_BASES:
        add(key, "race", "borg", "ops", prompt, group="race")
    for key, prompt in BORG_OVERLAYS + GEAR_OVERLAYS:
        add(key, "overlay", "none", "none", prompt, kind="overlay", group="overlay")

    # 6. Composition: a key can stack several cells into one face string.
    index = {c["key"]: c for c in cells}
    for key, layers in COMPOSED.items():
        if key in index and all(l in index for l in layers):
            index[key]["layers"] = layers

    cells.sort(key=lambda c: (ERA_ORDER.index(c["group"]), c["key"]))
    return cells




def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default=os.path.join(HERE, "face_roster.json"))
    ap.add_argument("--only-with-art", default=None,
                    help="keep ONLY cells that have a file in this directory. Sizes the "
                         "roster to the art that exists instead of reserving slots for "
                         "art that may never be drawn.")
    a = ap.parse_args()
    cells = build()
    if a.only_with_art:
        # Local SDXL generation did not reach the quality of the hand-made cells, so
        # the set is sized to the good art rather than padded out with filler. A
        # reserved-but-empty slot is not free: it still costs 512x512 of a 4096 sheet,
        # and five near-blank 12MB PNGs would ship in the media pack for nothing.
        have = {os.path.splitext(f)[0] for f in os.listdir(a.only_with_art)
                if f.endswith(".png")}
        before = len(cells)
        cells = [c for c in cells if c["key"] in have]
        # A composed key can only keep the layers that survived.
        keys = {c["key"] for c in cells}
        for c in cells:
            if c.get("layers"):
                kept = [l for l in c["layers"] if l in keys]
                if len(kept) > 1:
                    c["layers"] = kept
                else:
                    c.pop("layers", None)
        print("kept %d of %d cells that have art" % (len(cells), before))

    from collections import Counter
    groups = Counter(c["group"] for c in cells)
    modes = Counter(c["mode"] for c in cells)
    kinds = Counter(c["kind"] for c in cells)
    sheets = (len(cells) + 63) // 64

    with open(a.out, "w") as f:
        json.dump({"cell": 512, "grid": 8, "cells": cells}, f, indent=1)

    print("%d cells -> %d sheets (%d slots spare on the last)"
          % (len(cells), sheets, sheets * 64 - len(cells)))
    print("  groups:", dict(groups))
    print("  modes :", dict(modes))
    print("  kinds :", dict(kinds))
    print("  wrote :", a.out)


if __name__ == "__main__":
    main()
