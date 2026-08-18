# Helpers for the TNG add-on. Everything is `tng_`-prefixed on purpose: a .mastlib's .py
# files are exec'd into one shared namespace and every function in them becomes a MAST
# GLOBAL, so an unprefixed name collides with any .mast variable of the same name anywhere
# in the story. (A helper called `_ship` here took down a whole run against LM's
# standard_consoles.mast, which assigns to `_ship`.)

FACTIONS = ("Federation", "Klingon", "Romulan", "Cardassian", "Kazon", "Orion", "Dominion")


def tng_register_races():
    """Add the TNG factions to PLAYABLE_RACES / NPC_RACES, keeping what is already there.

    ADD rather than replace, so a mission can run Klingons against a TSN crew, or a Galaxy
    against Kraliens. A total conversion is then a mission's choice - it sets the settings
    to the TNG factions alone - rather than something installing a mastlib does to you.

    `settings_add_defaults` cannot do this: it only fills MISSING keys, and both of these
    always have a value. `settings_get_defaults()` returns the live cached dict, so this
    edits it in place.

    Must run before the gates below read the settings, which is why it is the first line of
    __init__.mast.
    """
    from sbs_utils.procedural.settings import settings_get_defaults
    settings = settings_get_defaults()
    added = []
    # EVERY faction is playable, not just the Federation. LM's own default lists all nine
    # of its races, a Galor has an interior in this pack, and someone will want to fly one.
    # Only the six raiding factions get NPC_RACES - that gate is about fleet ladders, and
    # the Federation has none.
    for key, wanted in (("PLAYABLE_RACES", FACTIONS),
                        ("NPC_RACES", FACTIONS[1:])):
        raw = settings.get(key) or ""
        if not isinstance(raw, str):
            raw = ",".join(str(x) for x in raw)
        have = {r.strip().lower() for r in raw.split(",") if r.strip()}
        new = [f for f in wanted if f.lower() not in have]
        if new:
            settings[key] = (raw + ", " if raw.strip() else "") + ", ".join(new)
            added += new
    return added


def tng_safe_status(text):
    """Make a status string safe to hand back to MAST.

    MAST re-runs every assigned string through f-string formatting, so a `{` anywhere in it
    is compiled as an expression - and an exception message quoting YAML syntax
    (`use quotes if the key name includes {}[],:`) is exactly the shape that blows up, with
    the error reported against the CALLER's line rather than here. Braces out, length
    capped: a status line is for a log, not a stack trace.
    """
    text = str(text).replace("{", "(").replace("}", ")")
    return text if len(text) <= 300 else text[:297] + "..."


def tng_resolve_art_path(ships_file):
    """Point every entry's `artfilepath` at wherever this pack actually unpacked.

    `artfilepath` is the FOLDER the art lives in and `artfileroot` stays the file's base
    name - they work together, and the path is relative to the EXE folder, exactly as the
    engine team's own example does it:

        "artfileroot": "tsn_light_cr",
        "artfilepath": "data/missions/BeamArcTest/extraShipGraphicData"

    IT CANNOT BE BAKED AT BUILD TIME. The pack unpacks to
    `data/missions/__lib__/media/<owner>.<repo>.media.<version>/`, so the path carries the
    version and the install layout - neither of which the author knows when writing the
    file. And the ENGINE reads it off disk, so patching the entries in memory would not
    reach it: the file itself has to be right before `add_extra_ship_data` opens it.

    Writing here is legitimate where writing into the mission was not. The unpacked pack is
    already a generated artifact under `data/missions/__lib__/`, rebuilt by `sbs.pyz lib`
    whenever the zip changes. Nothing in the game install is touched.

    Rewrites only when the value is actually wrong, so a normal run touches no files.
    """
    import os
    from sbs_utils import fs

    art_dir = os.path.join(os.path.dirname(ships_file), "ships")
    if not os.path.isdir(art_dir):
        return "no ships/ folder in the pack"
    try:
        want = os.path.relpath(art_dir, fs.exe_dir).replace("\\", "/")
    except ValueError:                      # a different drive from the exe
        want = art_dir.replace("\\", "/")

    try:
        from sbs_utils import yaml
        with open(ships_file, encoding="utf-8") as f:
            text = f.read()
        entries = (yaml.safe_load(text) or {}).get("#ship-list") or []
        if entries and all(e.get("artfilepath") == want for e in entries):
            return want + " (already correct)"
        for e in entries:
            e["artfilepath"] = want
        head = "".join(l for l in text.splitlines(True)
                       if l.lstrip().startswith("#") or not l.strip())
        tmp = ships_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(head)
            yaml.safe_dump({"#ship-list": entries}, f, sort_keys=False,
                           default_flow_style=False, allow_unicode=False,
                           width=100000)  # width=100000 = NEVER WRAP. A wrapped plain scalar stops round-tripping the
                           # moment the value holds a `:` or `,`, which ship long_desc
                           # text routinely does - and the engine, not this script, is
                           # where that surfaces.
        os.replace(tmp, ships_file)         # atomic on Windows and POSIX
        return want + " (patched)"
    except Exception as e:
        return tng_safe_status("artfilepath NOT set: " + str(e))


def tng_declare_ships(ships_file):
    """Give the 51 hulls to the ENGINE and to the library, without writing a file.

    TWO CONSUMERS, and they are not the same thing:

      * the ENGINE needs them to build hulls, and learns them from a real file on disk.
        `sbs.add_extra_ship_data(name, path)` (engine 1.3.5) points it straight at the
        mod's own copy - no extension on the name, the engine tries .yaml then .json.
      * the LIBRARY needs them for its own queries: `filter_ship_data_by_side` is how a
        prefab finds "a Klingon warship", and `get_ship_name` is what a console displays.
        The engine call does not populate that, so it is merged here too.

    WHY NOT `ship_data_merge_mod`: it is the BROKEN route, not merely the older one.
    It reaches the engine by GENERATING `extraShipData.json` in the mission folder during
    sim_create(). That file stays on disk, and on the next run `get_ship_data()` prepends
    it whole - `#mod` entries and all - while the add-on declares the same entries again.
    This mod is where it was measured: 51 hulls became 102 from run 2 onward. The file the
    feature generates is the input that breaks it. Writing nothing avoids the class.

    Returns a short STATUS STRING rather than a dict - MAST re-runs an assigned string
    through f-string formatting, so a dict's braces reaching `log(f"...{result}")` die with
    "FORMAT String error" reported against the caller.

    The presence guard is what makes this safe to call twice: the MOCK's
    `add_extra_ship_data` already merges library-side (so headless behaves like the engine),
    the real engine does not, and one guard covers both without either knowing about the
    other.
    """
    from sbs_utils.helpers import FrameContext
    from sbs_utils.procedural.ship_data import get_ship_data_for, merge_mod_ship_yaml
    import os

    if not ships_file:
        return "NOT DECLARED - the media pack was not found"

    # media_shared answers RELATIVE TO THE MISSION - that is what gui_image_add_atlas and
    # friends want, and it reads better in a stack trace. Neither `open()` nor the engine
    # is standing in the mission folder, so resolve it before using it either way.
    from sbs_utils.fs import get_mission_dir
    if not os.path.isabs(ships_file):
        ships_file = os.path.abspath(os.path.join(get_mission_dir(), ships_file))
    pack_dir = os.path.dirname(ships_file)

    # THE ENGINE GETS JSON, THE AUTHOR KEEPS YAML.
    #
    # YAML is the preferred authoring format and media/tng_ships.yaml stays the source of
    # truth - it is what a person edits and what a diff is readable in. But the ENGINE's own
    # YAML reader currently has problems, and `add_extra_ship_data` takes either, so it is
    # handed the generated .json sitting beside it (`_tools/ships_to_json.py`).
    #
    # This is not a speed change. On the script side ryaml parses this file in 7ms against
    # json's 1ms; the reason is the engine reader, not the clock.
    #
    # STALENESS IS THE FAILURE MODE and it is silent: both files parse, both look right, and
    # only the hulls disagree - the engine reading yesterday's while the library reads
    # today's. So an out-of-date .json is REPORTED rather than quietly preferred.
    engine_file = ships_file
    stale = ""
    _json_file = os.path.splitext(ships_file)[0] + ".json"
    if os.path.exists(_json_file):
        engine_file = _json_file
        # A DEV-TIME check only. Inside an unpacked media pack both files carry their
        # EXTRACTION time, not their authoring time, so comparing them there reports a
        # stale JSON whenever the zip happened to write the YAML second - which is exactly
        # what it did the first time this ran. The pack was built from whatever was on
        # disk, so there is nothing to catch at that end anyway.
        if "__lib__" not in _json_file.replace("\\", "/"):
            try:
                if os.path.getmtime(_json_file) < os.path.getmtime(ships_file):
                    stale = " JSON-STALE(re-run _tools/ships_to_json.py)"
            except OSError:
                pass

    # Point the entries at where the art really is BEFORE the engine opens the file.
    art = tng_resolve_art_path(ships_file)

    told_engine = None
    try:
        sbs = FrameContext.context.sbs
        # ONE argument, the whole file. The 2026-08-15 engine takes
        # `add_extra_ship_data(fully_pathed_file)`; the old `(name, folder)` form is a
        # TypeError, caught below as "failed:" and otherwise silent - the library merge
        # still runs, so the hulls have every stat and simply do not exist in the engine.
        sbs.add_extra_ship_data(engine_file)
        told_engine = True
    except AttributeError:
        # An older engine or sbslib without the call. Not fatal: the library merge below
        # still gives the mission its ships, they just have no engine-side hull.
        told_engine = False
    except Exception as e:
        told_engine = "failed: " + str(e)

    merged = 0
    if get_ship_data_for("tng_fed_saber") is None:
        try:
            with open(engine_file, encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            return tng_safe_status("engine=" + str(told_engine) + " library=unreadable "
                    + str(e) + " art=" + art)
        import re
        merge_mod_ship_yaml(re.sub(r"^[ \t]*//.*$", "", text, flags=re.M), "tng_races")
        merged = 1
    return ("engine=" + str(told_engine) + stale
            + " fmt=" + os.path.splitext(engine_file)[1].lstrip(".")
            + " library=" + ("merged" if merged else "already present"))


def _tng_enabled(manifest, test):
    from sbs_utils.procedural.settings import (settings_race_is_playable,
                                               settings_race_is_npc)
    check = settings_race_is_playable if test == "playable" else settings_race_is_npc
    serves = (manifest or {}).get("serves") or {}
    out = []
    for faction in sorted(((manifest or {}).get(
            "interiors" if test == "playable" else "fleets")) or {}):
        # A Breen hull is a Dominion asset: it loads when the Dominion is on, rather than
        # asking a mission to name a faction that fields exactly one ship.
        if check(serves.get(faction, faction)):
            out.append(faction)
    return out


def tng_interiors_enabled(manifest):
    """Floor-plan filenames for every faction a player may fly.

    An interior is only ever built for a PLAYER ship, so plans for a faction nobody can be
    are parsed at load and never used - which is the whole reason for the gate.
    """
    files = []
    for faction in _tng_enabled(manifest, "playable"):
        files += manifest["interiors"][faction]
    return files


def tng_fleets_enabled(manifest):
    """Ladder filenames for every faction that may raid."""
    return [manifest["fleets"][f] for f in _tng_enabled(manifest, "npc")]


def tng_register_portraits(sheet, names):
    """Register the TNG character portraits as one image atlas.

    A flat portrait is NOT a face: `gui_face` composites 512px layers out of a sheet
    registered in `data/graphics/allFaceFiles.txt`, which a mastlib cannot write. These are
    ordinary images, so they go through `ImageAtlas` instead - which DOES resolve out of the
    unpacked shared-media pack, and therefore ships with the mod. Use them as
    `image://tng:picard`, not in a face string.

    One `gui_image_add_atlas_grid` call rather than 192 `gui_image_add_atlas` lines: the
    sheet is an even 16x12 grid so the cell size is measured from the file, and the names
    list is laid out row-major to match.

    `domain="tng"` namespaces the keys. Without it, generic keys like `ds9_ops_04` would sit
    in the global image namespace and collide with the next add-on that has the same idea.
    """
    from sbs_utils.procedural.gui.image import gui_image_add_atlas_grid
    try:
        registered = gui_image_add_atlas_grid(sheet, 16, 8, names, domain="tng")
    except Exception as e:
        return "portraits NOT registered: " + tng_safe_status(e)
    return str(len(registered)) + " portraits"


# A faction is not a species. The Federation fields humans, vulcans, andorians,
# trill, betazoids and more; the Dominion is jem'hadar soldiers, vorta overseers and
# breen allies. Mapped here so a script can pass whatever it already has.
_TNG_FACTION_RACES = {
    "federation": ("human", "vulcan", "andorian", "trill", "betazoid", "benzite",
                   "bajoran", "android", "elaurian", "holographic", "hologram"),
    "dominion":   ("jemhadar", "vorta", "breen"),
    "klingon":    ("klingon",),
    "romulan":    ("romulan",),
    "cardassian": ("cardassian",),
    "kazon":      ("kazon",),
    "orion":      ("orion",),
    "borg":       ("borg",),
}


def tng_register_faces(faces, index=None, sheets=None):
    """Make the TNG face sheets reachable from MAST.

    `tng_faces.json` has been generated and shipped in this mastlib since the first
    build, and until now NOTHING loaded it: there was no register call and the
    library's `random_face()` had a hard-coded list of the six stock races, so a
    script could not ask for a TNG face at all. This closes that.

    Registration teaches the library two things:

      * the SHEET ALIASES and their grid, so anything that parses or draws a face
        string knows how to read cells out of `tng1`..`tng6`.
      * a POOL PER RACE and per role, so `random_face("klingon")` and
        `random_face("klingon", "command")` work as they do for stock races.

    It does NOT make the sheets loadable. The engine maps an alias to a file through
    `data/graphics/allFaceFiles.txt`, which a mastlib cannot write because a mastlib
    is a zip - so those lines are still pasted in by hand. Same engine-owned seam as
    art paths, SFX and font names; `_tools/facesheets.py` prints the exact lines.

    `index` is `tng_face_index.json`, shipped beside the face map. Do not try to
    infer race from the key instead: that reads `picard` as a race called "picard",
    `seven_of_nine` as "seven" and `gear_visor` as "gear", which gave 80 races where
    there are about 25. It also carries `kind`, which is what keeps OVERLAY cells -
    an implant, a VISOR - out of the random pools. An overlay is a layer to add to a
    face, never a face on its own.

    Args:
        faces: parsed `tng_faces.json`, key -> face string.
        index: parsed `tng_face_index.json`, key -> {race, role, kind, era}.
        sheets: how many `tng<N>` sheets the build produced. Leave it None to
            DERIVE the count from the face strings, which is what callers should do -
            the default used to be a literal 6, and adding sheets 7 and 8 left them
            unregistered because the call site never passed the new number. A count
            that lives in the data cannot drift from it.

    Returns:
        str: one line for the log. Never raises - a mod that cannot register its
        faces should still load its ships.
    """
    try:
        from sbs_utils.faces import face_register_sheet, face_register_race
    except ImportError:
        return "faces NOT registered: this sbs_utils has no face registry"
    if not faces:
        return "faces NOT registered: tng_faces.json was empty"
    _TNG_FACES.clear(); _TNG_FACES.update(faces)
    _TNG_INDEX.clear(); _TNG_INDEX.update(index or {})
    try:
        if sheets is None:
            sheets = 0
            for face in faces.values():
                alias = str(face).split(" ")[0]
                if alias.startswith("tng") and alias[3:].isdigit():
                    sheets = max(sheets, int(alias[3:]))
        for n in range(1, int(sheets) + 1):
            face_register_sheet("tng%d" % n, 8, 8)
        pools = {}
        skipped = 0
        for key, face in faces.items():
            meta = (index or {}).get(key)
            if meta is None:
                skipped += 1
                continue
            if meta.get("kind") == "overlay":
                continue            # a layer, not a face
            race = str(meta.get("race") or "human").lower()
            if race == "holographic":
                race = "hologram"      # two roster spellings, one thing
            role = meta.get("role")
            e = pools.setdefault(race, {"any": [], "roles": {}})
            e["any"].append(face)
            if role and role != "none":
                e["roles"].setdefault(str(role).lower(), []).append(face)
        # FACTION ALIASES. A mission has a FACTION in hand - `ship.race` is "Federation"
        # or "Dominion", the same names tng_manifest uses - while the roster stores the
        # BIOLOGICAL race. Without this, random_face("Federation") matches nothing and
        # silently falls back to a stock Terran face, which is the one failure mode that
        # looks like it worked. The Federation is deliberately multi-species.
        for faction, members in _TNG_FACTION_RACES.items():
            # SEED FROM THE SAME-NAMED RACE, do not replace it. A faction alias can
            # collide with a real race of the same name - the new sheets include a
            # "dominion" race, and "dominion" is also the faction covering jemhadar
            # and vorta. Assigning the merged pool straight into pools[faction] threw
            # that race's own 22 faces away silently, and the only symptom was the
            # registration count coming back 22 short of the index.
            seed = pools.get(faction)
            merged = {"any": list(seed["any"]) if seed else [],
                      "roles": {k: list(v) for k, v in seed["roles"].items()} if seed else {}}
            for m in members:
                src = pools.get(m)
                if not src:
                    continue
                merged["any"].extend(src["any"])
                for role, v in src["roles"].items():
                    merged["roles"].setdefault(role, []).extend(v)
            if merged["any"]:
                pools[faction] = merged

        for race, e in pools.items():
            # in_random=False: loading this mod for its SHIPS must not silently
            # restyle every crowd in a stock mission. Ask for a TNG race by name.
            face_register_race(race, e["any"], e["roles"], in_random=False)
    except Exception as e:
        return "faces NOT registered: " + tng_safe_status(e)
    note = ""
    if skipped:
        note = ", %d had no index entry and were skipped" % skipped
    # Count DISTINCT faces: the faction aliases re-list their members' faces, so
    # summing the pools reports 652 for a 370-face set.
    distinct = len(set(f for v in pools.values() for f in v["any"]))
    return "%d faces over %d races and factions%s" % (distinct, len(pools), note)


def tng_face_assimilate(face, *overlays):
    """Append implant overlays to ANY face string, including one this mod never drew.

    This is why implants are separate cells rather than baked into each drone: a
    face string is layers, so a character who already exists on screen can be
    assimilated at runtime by adding to theirs. Falls back to returning the face
    unchanged if the library is too old to have `face_overlay`.
    """
    try:
        from sbs_utils.faces import face_overlay
    except ImportError:
        return face
    return face_overlay(face, *overlays)


# ---- character builder helpers --------------------------------------------
#
# Every one of these is prefixed `tng_builder_`. A mod's top-level functions become
# MAST globals in ONE flat mission-wide namespace and the last loaded wins with no
# warning, so an unprefixed `faces()` or `describe()` here would collide with another
# addon and fail at runtime in whichever one lost.
#
# The builder reads the REGISTRY, not a second manifest: the same pools random_face()
# uses. That way the panel cannot list a face the sheets do not have, and it needs no
# updating when the sheet set grows.

_TNG_OVERLAY_LABELS = {
    "gear_visor": "VISOR", "gear_eyepatch": "Eyepatch", "gear_scar_left": "Scar",
    "gear_breather": "Breather", "borg_impl_ocular_l": "Borg eye L",
    "borg_impl_ocular_r": "Borg eye R", "borg_impl_brow": "Borg brow",
    "borg_impl_cheek": "Borg cheek", "borg_impl_cranial": "Borg plate",
    "borg_impl_temple": "Borg temple", "borg_impl_jaw": "Borg jaw",
    "borg_impl_tubes": "Borg tubes", "borg_impl_neck": "Borg collar",
    "borg_impl_crown": "Borg crown",
}

_TNG_FACES = {}          # key -> face string, filled by tng_register_faces
_TNG_INDEX = {}          # key -> {race, role, kind, era}


def tng_builder_races():
    """Species the shipped sheets actually contain, for the panel's left list."""
    out = sorted({str(v.get("race") or "human").lower()
                  for k, v in _TNG_INDEX.items() if v.get("kind") != "overlay"})
    return out or ["human"]


def tng_builder_faces(race, role="any"):
    """Cell KEYS for a species, optionally filtered by role.

    Returns keys rather than face strings so the list can show a readable name; the
    string is looked up only when something is previewed or worn.
    """
    race = str(race).lower()
    out = []
    for k, v in sorted(_TNG_INDEX.items()):
        if v.get("kind") == "overlay":
            continue
        if str(v.get("race") or "human").lower() != race:
            continue
        if role and role != "any" and str(v.get("role") or "").lower() != str(role).lower():
            continue
        out.append(k)
    return out


def tng_builder_overlays():
    """Overlay cells that actually shipped. Empty until overlay art exists, and the
    panel simply shows no overlay buttons - it does not break."""
    return sorted(k for k, v in _TNG_INDEX.items() if v.get("kind") == "overlay")


def tng_builder_overlay_label(key):
    return _TNG_OVERLAY_LABELS.get(key, key.replace("_", " "))


def tng_builder_toggle(current, key):
    """Add or remove an overlay. Returns a NEW list - MAST holds these in task state
    and mutating in place would not register as a change for `on change`."""
    cur = list(current or [])
    if key in cur:
        cur.remove(key)
    else:
        cur.append(key)
    return cur


def tng_builder_compose(face_key, overlays=None):
    """The finished face string: the chosen bust plus any overlays, lowest first."""
    base = _TNG_FACES.get(face_key, "")
    if not base:
        return ""
    extra = [_TNG_FACES.get(o, "") for o in (overlays or [])]
    return tng_face_assimilate(base, *[e for e in extra if e])


def tng_builder_describe(face_key, overlays=None):
    """Text for the panel. Returns a STRING with no braces in it.

    A MAST assignment re-runs a string through f-string formatting, so a `{` that
    arrived from data - a dict repr, a stray brace in a key - is a SyntaxError
    reported against the caller's line. Everything here is joined by hand for that
    reason; do not be tempted to interpolate a dict.
    """
    v = _TNG_INDEX.get(face_key) or {}
    parts = ["# " + str(face_key).replace("_", " ")]
    parts.append("species: " + str(v.get("race", "?")))
    parts.append("role: " + str(v.get("role") or "-"))
    parts.append("era: " + str(v.get("era") or "-"))
    ov = [tng_builder_overlay_label(o) for o in (overlays or [])]
    parts.append("overlays: " + (", ".join(ov) if ov else "none"))
    return "\n".join(parts)


def tng_builder_apply(face):
    """Put the chosen face on the client's own ship. Returns a status string."""
    if not face:
        return "no face chosen"
    try:
        from sbs_utils.faces import set_face
        from sbs_utils.helpers import FrameContext
        import sbs
        ship = sbs.get_ship_of_client(FrameContext.client_id)
        if ship is None:
            return "no ship for this client"
        set_face(ship.id, face)
    except Exception as e:
        return "could not apply: " + tng_safe_status(e)
    return "worn"


def tng_gallery_heading(race, total, page, pages):
    """A heading string for the gallery, with NO braces in it.

    A MAST assignment re-runs a string through f-string formatting, so a `{` that
    arrives from data is a SyntaxError reported against the CALLER's line. Built by
    concatenation for that reason.
    """
    return ("TNG faces - " + str(race) + " - " + str(total) +
            " in set - page " + str(page) + " of " + str(pages))


def tng_gallery_names(keys):
    """The keys on this page, as one plain line."""
    return ", ".join(str(k).replace("_", " ") for k in (keys or [])) or "(none)"


# ---- listbox templates ----------------------------------------------------
#
# A .mastlib's .py is exec'd, not imported as a module, so it does NOT inherit the
# MAST globals a .mast file sees - gui_row and friends have to be imported by name
# here or they are a NameError at layout time. LM's casino helpers do the same.
from sbs_utils.procedural.gui import gui_row, gui_text, gui_face, gui_text_escape
#
# These MUST be Python functions, not MAST labels. gui_list_box CALLS the template
# while it lays each row out, and a MAST label is not callable - passing one raises
# "'Label' object is not callable" from inside layout_listbox.present, which reads as
# a layout bug rather than a wiring mistake. LM's casino templates are the reference.

def tng_row_title_species():
    gui_row("row-height: 1.6em; padding:6px; background:#1578;")
    gui_text("$text:Species;justify:center;")


def tng_row_species(item):
    gui_row("row-height: 1.8em; padding:4px;")
    gui_text("$text:" + gui_text_escape(str(item)) + ";")


def tng_row_title_faces():
    gui_row("row-height: 1.6em; padding:6px; background:#1578;")
    gui_text("$text:Faces;justify:center;")


def tng_row_face(item):
    """A face row shows the FACE, not just its key - that is the whole point of a
    chooser, and gui_face here draws from the same sheet the preview does."""
    gui_row("row-height: 3.2em; padding:4px;")
    gui_face(tng_builder_compose(str(item), []))
    gui_text("$text:" + gui_text_escape(str(item).replace("_", " ")) + ";")


MUSIC_BANK = "TNG_Music"


def tng_set_default_music():
    """Make the TNG bank the default soundtrack, without overriding anyone.

    `settings_set_mod_default` is the mod tier: it beats the library built-in
    (`MUSIC_SELECT: "random"`) but loses to the mission's settings.yaml, a profile,
    COSMOS_SETTINGS, or `var.MUSIC_SELECT=` on the command line. So this is a re-skin a
    mission can decline by simply naming its own, which is the same stance
    `tng_register_races` takes with the faction lists.

    Note `settings_add_defaults` cannot express this - it only fills keys nothing has set,
    and MUSIC_SELECT always has a library value.

    Returns:
        str: one line for the log, saying whether it applied and what is playing instead.
    """
    from sbs_utils.procedural.settings import settings_set_mod_default, settings_get_defaults
    if settings_set_mod_default("MUSIC_SELECT", MUSIC_BANK):
        return MUSIC_BANK
    return (f"{settings_get_defaults().get('MUSIC_SELECT')} "
            f"(the mission asked for it; {MUSIC_BANK} is still selectable)")
