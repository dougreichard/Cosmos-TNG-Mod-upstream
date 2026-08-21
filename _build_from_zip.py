"""Derive the Cosmos-TNG-Mod add-on from Cosmos-TNG-Mod_v0-2-3.zip. Re-runnable.

The interesting part of restructuring a mod is not the copying, it is the DIFFING - and a
diff nobody can re-run is a claim, not a measurement. Point this at a newer TNG release and
it will tell you what changed and what that release would cost.

WHAT THIS PRODUCES

    media/          -> artemis-sbs.Cosmos-TNG-Mod.media.v0.2.3.zip, unpacked ONCE into
                       __lib__/media/<pack>/ and read from there by every mission
    tng_races/      -> artemis-sbs.Cosmos-TNG-Mod.tng_races.v0.2.3.mastlib (FLAT)

THE ONE DECISION EVERYTHING ELSE FOLLOWS FROM: the ships get their OWN keys.

The zip is a re-skin - it repoints 50 keys the game already owns, so installing it turns
every light cruiser in every mission into a Saber. That works (measured: an add-on entry
does override a key `data/shipData.yaml` owns, engine 1.3.5, missions/shipdata_override) but
it makes the mod a conversion rather than content: two Trek mods can never coexist, and
nothing can spawn a Saber *and* a Light Cruiser. Unique keys make it additive. The zip's own
author wants this - "I'll eventually create a TNG mission suite that breaks away from this."

Keys are `tng_<faction>_<class>`. The era prefix is deliberate: the author's roadmap has TOS
and TMP versions next, and every Trek era has a Federation cruiser.

Run:  python _build_from_zip.py            (from the Cosmos-TNG-Mod folder)
      python _build_from_zip.py --no-art   (skip the 571 MB media copy)
"""

import collections
import json
import re
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
MISSIONS = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(MISSIONS, "sbs_utils"))

from sbs_utils.fs import test_set_exe_dir                       # noqa: E402
test_set_exe_dir()
from sbs_utils.procedural.grid_ascii import (                   # noqa: E402
    grid_ascii_parse, grid_ascii_render, grid_ascii_validate)
from sbs_utils.procedural.grid_rooms import grid_room_roles     # noqa: E402
import yaml                                                     # noqa: E402

# ---------------------------------------------------------------------------------------
# VERSION AND ART PATH, both derived from __lib__.json so there is ONE place to bump.
#
# The pack unpacks to `__lib__/media/{owner}.{repo}.media.{version}/`, and every part of
# that is known at BUILD time - owner defaults to `artemis-sbs` in `sbs.pyz lib`, repo is
# this folder, version is below. So the ART PATH is baked into `artfileroot` here rather
# than patched at runtime, which means a release built by CI carries the right path already
# and no mod has to write a file while the game is running.
OWNER = "artemis-sbs"                              # `sbs.pyz lib -u` default
REPO = os.path.basename(HERE)


def mod_version():
    with open(os.path.join(HERE, "__lib__.json"), encoding="utf-8") as f:
        return json.load(f)["version"]


def art_path(version):
    """Where the art is, relative to the EXE FOLDER - which is what artfileroot resolves
    against as of engine v1.3.6.

    THE RULE CHANGED IN v1.3.6 AND THE OLD NOTE HERE IS RETIRED. This used to bake a
    graphics-relative path (`../missions/<pack>/ships/X`) on the strength of a measurement
    taken before the change, which recorded exe-relative as "not opened, then assert".
    That is no longer how the engine resolves it. Confirmed by Doug against the current
    build; do not re-derive it from the old comment, which is why the comment is gone
    rather than merely corrected.

    `artfilepath` is OBSOLETE and is not written anywhere any more - not into the manifest
    here, and not patched into entries at runtime by tng_setup. artfileroot is the whole
    path on its own.
    """
    return f"data/missions/__lib__/media/{OWNER}.{REPO}.media.{version}/ships"


ZIP = os.path.join(MISSIONS, "Cosmos-TNG-Mod_v0-2-3.zip")
GAME = os.path.dirname(MISSIONS)                    # ...\Cosmos-1-3-0\data
ADDON = os.path.join(HERE, "tng_races")
MEDIA = os.path.join(HERE, "media")

# ---------------------------------------------------------------------------------------
# THE SHIP KEYS. Written out rather than derived, because these are the mod's public API -
# they appear in fleet ladders, PLAYER_LIST and every mission that spawns one - so they
# should be readable and stable, not the output of a string rule. Derivation would also get
# two of them wrong: CRD_Terok_Nor is the art for BOTH DS9 and Terok Nor, and KAZ_Raider for
# both the Kazon Raider and the Kazon Fighter.
#
# The stock key on the left is what the zip re-skinned; it is kept only so the build can
# find the author's edits. Nothing at runtime refers to it.
KEYS = {
    # ---- Federation (Starfleet combatants) --------------------------------------
    "tsn_light_cruiser":      "tng_fed_saber",
    "tsn_warpster":           "tng_fed_centaur",
    "tsn_light_carrier":      "tng_fed_constellation",
    "tsn_scout":              "tng_fed_california",
    "tsn_escort":             "tng_fed_intrepid",
    "tsn_mine_layer":         "tng_fed_excelsior_refit",
    "tsn_missile_cruiser":    "tng_fed_nebula",
    "tsn_battle_cruiser":     "tng_fed_ambassador",
    "tsn_battleship":         "tng_fed_galaxy",
    "tsn_carrier":            "tng_fed_akira",
    "tsn_destroyer":          "tng_fed_defiant",
    "tsn_heavy_cruiser":      "tng_fed_luna",
    "tsn_dreadnought":        "tng_fed_sovereign",
    "tsn_juggernaut":         "tng_fed_galaxy_x",
    "tsn_shuttle":            "tng_fed_danube",
    "tsn_bomber":             "tng_fed_danube_rollbar",
    "tsn_fighter":            "tng_fed_peregrine",
    # ---- Federation (USFP civil + bases) ----------------------------------------
    "starbase_command":       "tng_fed_starbase",
    "starbase_industry":      "tng_fed_ds9",         # Cardassian-BUILT, Federation-RUN
    "starbase_civil":         "tng_fed_station",
    "starbase_science":       "tng_fed_comms_base",
    "science_ship":           "tng_fed_nova",
    "cargo_ship":             "tng_fed_freighter",
    "transport_ship":         "tng_fed_olympic",
    # ---- Klingon ------------------------------------------------------------------
    "xim_corsair":            "tng_klg_brel",
    "xim_destroyer":          "tng_klg_ktinga",
    "xim_battleship":         "tng_klg_vorcha",
    "xim_dreadnought":        "tng_klg_neghvar",
    # ---- Romulan ------------------------------------------------------------------
    "torgoth_destroyer":      "tng_rmn_tvaro",
    "torgoth_goliath":        "tng_rmn_mogai",
    "torgoth_leviathan":      "tng_rmn_dderidex",
    "torgoth_behemoth":       "tng_rmn_scimitar",
    "starbase_torgoth":       "tng_rmn_base",
    # ---- Cardassian ---------------------------------------------------------------
    "arvonian_fighter":       "tng_crd_heideki",
    "arvonian_destroyer":     "tng_crd_galor",
    "arvonian_light_carrier": "tng_crd_keldon",
    "arvonian_carrier":       "tng_crd_damar",
    "starbase_arvonian":      "tng_crd_terok_nor",
    # ---- Kazon --------------------------------------------------------------------
    "kazon_fighter":          "tng_kaz_fighter",
    "kralien_cruiser":        "tng_kaz_raider",
    "kralien_battleship":     "tng_kaz_cruiser",
    "kralien_dreadnought":    "tng_kaz_carrier",
    "starbase_kralien":       "tng_kaz_base",
    # ---- Orion --------------------------------------------------------------------
    "pirate_fighter":         "tng_orn_interceptor",
    "pirate_longbow":         "tng_orn_corvette",
    "pirate_strongbow":       "tng_orn_brigand",
    "pirate_brigantine":      "tng_orn_corsair",
    # ---- Dominion -----------------------------------------------------------------
    "skaraan_defiler":        "tng_jem_attack_ship",
    "skaraan_enforcer":       "tng_brn_chel_grett",   # Breen hull, Dominion service
    "skaraan_executor":       "tng_jem_battlecruiser",
    "starbase_skaraan":       "tng_jem_base",
}

#: Key prefix -> the faction that owns it. This is `origin` AND shipData `side`: stock uses
#: race-ish names for `side` (TSN, Kralien, Ximni), and `filter_ship_data_by_side` is how a
#: prefab finds "a Klingon warship". `race` IS `origin` in sbs_utils, so one name does all
#: three jobs.
FACTION = {
    "tng_fed_": "Federation",
    "tng_klg_": "Klingon",
    "tng_rmn_": "Romulan",
    "tng_crd_": "Cardassian",
    "tng_kaz_": "Kazon",
    "tng_orn_": "Orion",
    "tng_jem_": "Dominion",
    "tng_brn_": "Breen",       # the Chel Grett is Breen hardware...
}

#: ...but it fights for the Dominion, so it belongs to that fleet ladder and that side.
SERVES = {"Breen": "Dominion"}

#: Which hulls make a raiding fleet, lightest first. The Federation has none on purpose -
#: it is the player faction, and LM ships no `tsn` ladder either.
LADDERS = {
    "Klingon":    ["tng_klg_brel", "tng_klg_ktinga", "tng_klg_vorcha", "tng_klg_neghvar"],
    "Romulan":    ["tng_rmn_tvaro", "tng_rmn_mogai", "tng_rmn_dderidex", "tng_rmn_scimitar"],
    "Cardassian": ["tng_crd_heideki", "tng_crd_galor", "tng_crd_keldon", "tng_crd_damar"],
    "Kazon":      ["tng_kaz_fighter", "tng_kaz_raider", "tng_kaz_cruiser", "tng_kaz_carrier"],
    "Orion":      ["tng_orn_interceptor", "tng_orn_corvette", "tng_orn_brigand",
                   "tng_orn_corsair"],
    "Dominion":   ["tng_jem_attack_ship", "tng_brn_chel_grett", "tng_jem_battlecruiser"],
}

# The escalation curve is LM's own `pirate_fleets.yaml`, which is built on exactly this
# shape - three combat hulls plus a flagship at the top. Copying a shipped, played curve
# beats inventing one: 0 is a single light hull, 10 is a six-ship wall.
#   L = light, M = medium, H = heavy, F = flagship
LADDER_SHAPE = [
    [["L"], ["L"], ["L"], ["L"], ["L"]],
    [["L"], ["L"], ["L"], ["L", "L"], ["L", "L"]],
    [["L"], ["L"], ["L", "L"], ["L", "L"], ["M"]],
    [["L"], ["L", "L"], ["L", "L"], ["M"], ["M"]],
    [["L"], ["L", "L"], ["M"], ["M"], ["M"]],
    [["L", "L"], ["M"], ["M", "L"], ["M", "L"], ["M", "L", "L"]],
    [["L", "L", "L"], ["M", "L", "L"], ["M", "L", "L"], ["M", "L", "L"], ["H"]],
    [["M", "L", "L"], ["M", "L", "L"], ["M", "L", "L"], ["H", "L"], ["H", "L", "L"]],
    [["M", "L", "L"], ["M", "L", "L", "L"], ["H", "L", "L"], ["H", "L", "L"],
     ["H", "L", "L", "L"]],
    [["M", "M", "L", "L"], ["H", "L", "L", "L"], ["M", "H", "L", "L"],
     ["H", "H", "L", "L"], ["F", "M", "H", "L", "L"]],
    [["F", "H", "H", "M", "M", "L"], ["F", "H", "H", "M", "M", "L"],
     ["F", "H", "H", "M", "M", "L"], ["F", "H", "H", "M", "M", "L"],
     ["F", "H", "H", "M", "M", "L"]],
]

# The zip carries a misspelling of the game's own `monster_charybdis`. Installing the mod
# deletes the real monster and adds this typo in its place; it is not new content.
DROP_KEYS = {"monster_charbdis"}

# The zip keys this plan by ARTFILEROOT; grid data is keyed by shipData KEY, and the two
# differ on about half the ships, so as shipped it matched no hull and did nothing.
REKEY_GRID = {"klg_ktinga": "xim_destroyer"}

# ONE NAME MUST MEAN ONE ROLESET. The `.grid` legend maps a name to its roles once, so a
# plan using a single name for two rolesets loses the distinction - and the room registry
# resolves the survivor, which is how all 37 of the zip's `SHIELD` cells would have become
# AFT shields, deleting the forward shield from the damage model. Caught by the round-trip
# check below, not by reading. Both names are already in the registry.
DISAMBIGUATE = {
    ("SHIELD", "fwd,shield,system"): "fwd-shield",
    ("SHIELD", "aft,shield,system"): "aft-shield",
    ("rec-room", "cabin,gym,room"): "gymnasium",
    ("rec-room", "cabin,recreation,room"): "rec-room",
}

# A cell holds one grid object. Stock uses 0 stacked cells across 162 hulls and LM's `races`
# 0 across 63, so a stack is an authoring slip, not an idiom the format cannot express.
# Resolved by role weight because which one survives is a MECHANICS question: weapon and
# system cells feed the system_max_damage pools, a duplicated crew cabin feeds nothing.
_ROLE_RANK = (("weapon", 3), ("system", 2))

#: Engine-rendered strings are ASCII only; the taunt source has curly quotes in two lines.
_ASCII_FIXES = {0x2019: "'", 0x2018: "'", 0x201c: '"', 0x201d: '"', 0x2014: "-", 0x2013: "-"}

#: Race group in the zip's taunt file -> the faction that inherits those lines.
TAUNT_FACTION = {
    "kralien": "Kazon", "torgoth": "Romulan", "arvonian": "Cardassian",
    "skaraan": "Dominion", "ximni": "Klingon",
}


def faction_of(key):
    for prefix, name in FACTION.items():
        if key.startswith(prefix):
            return name
    return None


def _rank(obj):
    roles = obj.get("roles", "").lower()
    for token, score in _ROLE_RANK:
        if token in roles:
            return score
    return 1


def _role_key(obj):
    return ",".join(sorted(t.strip().lower() for t in obj.get("roles", "").split(",")))


# ---------------------------------------------------------------------------------------


def verify_yaml_roundtrip(path, entries):
    """Re-read what we just wrote and refuse to ship it if it does not match.

    Added after a `safe_dump(width=100)` wrapped a long `long_desc` mid-value: the file
    still looked fine, sbs_utils' own loader tolerated it, and the failure only appeared as
    an ENGINE parse error two layers away ("Found ',' where a key name was expected").
    Writing and re-reading here costs milliseconds and moves that discovery to the build.
    """
    with open(path, encoding="utf-8") as f:
        back = (yaml.safe_load(f) or {}).get("#ship-list") or []
    if back != entries:
        keys = {e.get("key") for e in entries}
        bad = sorted(keys ^ {e.get("key") for e in back}) or "field values differ"
        raise SystemExit(f"{os.path.basename(path)} does not round-trip: {bad}")
    return len(back)


def load_zip_data():
    z = zipfile.ZipFile(ZIP)

    def y(name):
        return {e["key"]: e
                for e in yaml.safe_load(z.read(name).decode("utf-8"))["#ship-list"]}

    def j(name):
        return json.loads(z.read(name).decode("utf-8-sig"))

    return {
        "ships": y("data/shipData.yaml"),
        "ships_base": y("data/shipData_stock.yaml"),
        "grid": j("data/grid_data.json"),
        "taunts": j("data/missions/legendarymissions/comms/taunts.json"),
        "taunts_base": j("data/missions/legendarymissions/comms/taunts_stock.json"),
        "zip": z,
    }


def load_races_grid():
    """LM's `races` floor plans, parsed. The current home of stock interiors.

    Read from the LM SOURCE folder at BUILD time, so the derived plan is baked into this
    mod's own mastlib and nothing depends on races at runtime. Absent LM, the build falls
    through to the engine file.
    """
    root = os.path.join(MISSIONS, "LegendaryMissions", "races")
    out = {}
    if not os.path.isdir(root):
        return out
    for name in sorted(os.listdir(root)):
        if not name.endswith(".grid"):
            continue
        with open(os.path.join(root, name), encoding="utf-8") as f:
            try:
                out[name[:-5]] = grid_ascii_parse(f.read())["entry"]["grid_objects"]
            except Exception:
                pass
    return out


def load_game_data():
    with open(os.path.join(GAME, "shipData.yaml"), encoding="utf-8") as f:
        ships = {e["key"]: e for e in yaml.safe_load(f)["#ship-list"]}
    with open(os.path.join(GAME, "grid_data.json"), encoding="utf-8-sig") as f:
        grid = json.load(f)
    return ships, grid


def build_ship_entries(mod, base, game, report):
    """Current game entry + only the fields the mod author actually changed, re-keyed.

    The direction matters. Taking the mod's entry whole ships its year-old copy of every
    field it never meant to touch; taking only its deltas ships its intent. Measured: that
    keeps 18 `torpedostart` fields the game has moved on (the PShock and Tag rounds).
    """
    out, reverts, missing = [], collections.Counter(), []
    for stock_key in sorted(mod):
        if stock_key in DROP_KEYS:
            continue
        if stock_key in base and mod[stock_key] == base[stock_key]:
            continue                                    # the author never touched it
        new_key = KEYS.get(stock_key)
        if new_key is None:
            missing.append(stock_key)
            continue

        if stock_key in base:
            entry = json.loads(json.dumps(game[stock_key]))
            for f in set(mod[stock_key]) | set(base[stock_key]):
                if mod[stock_key].get(f) != base[stock_key].get(f):
                    if f in mod[stock_key]:
                        entry[f] = json.loads(json.dumps(mod[stock_key][f]))
                    else:
                        entry.pop(f, None)
                elif f in game[stock_key] and game[stock_key][f] != base[stock_key].get(f):
                    reverts[f] += 1
        else:
            entry = json.loads(json.dumps(mod[stock_key]))   # a genuinely new ship

        entry["key"] = new_key
        faction = faction_of(new_key)
        entry["origin"] = faction
        entry["side"] = faction
        out.append(entry)

    if missing:
        raise SystemExit("no key mapping for: " + ", ".join(missing))
    if reverts:
        report.append(f"  reverts avoided  {sum(reverts.values())} fields "
                      f"({', '.join(sorted(reverts))}) kept at the game's current value")
    counts = collections.Counter(faction_of(e["key"]) for e in out)
    for faction in sorted(counts):
        report.append(f"  faction          {faction:<12} {counts[faction]} hull(s)")
    return out


def resolve_stacks(objects, report, key):
    by_cell = {}
    for obj in objects:
        cell = (int(obj["x"]), int(obj["y"]))
        if cell not in by_cell or _rank(obj) > _rank(by_cell[cell]):
            by_cell[cell] = obj
    dropped = len(objects) - len(by_cell)
    if dropped:
        report.append(f"  stacked cells    {key}: {dropped} surplus object(s) dropped, "
                      f"weapon and system cells kept")
    return [by_cell[c] for c in sorted(by_cell)]


def build_interiors(mod_grid, game_grid, races_grid, entries, report):
    """One `.grid` per hull the mod re-plans, each verified to parse back."""
    by_key = {e["key"]: e for e in entries}

    # UNIQUE KEYS CHANGE THE RULE HERE. While this was a re-skin, a hull with no plan of its
    # own kept the game's, because it still answered to the game's key. It does not any
    # more: nothing in `data/grid_data.json` mentions `tng_crd_heideki`, so a hull this mod
    # does not plan has NO interior at all - a dead Engineering console, silently.
    #
    # So every key gets a plan, from the best available source:
    #   1. the zip's own, where the author drew one
    #   2. otherwise LM's `races` plan for the hull it replaced. That add-on, not
    #      `data/grid_data.json`, is where stock interiors now live - the engine file is
    #      being deprecated and is already EMPTY for hulls races fully plans (cargo_ship,
    #      starbase_civil, every Torgoth and Skaraan hull), so skipping it would leave
    #      those with no Engineering
    #   3. otherwise the engine's own file, for anything races does not carry
    # A derived plan is a worse fit for the new shape than a purpose-drawn one, and
    # infinitely better than none. The zip BLANKS seven interiors that are fully planned
    # upstream; those fall through rather than being carried as the empty lists they are.
    plans, sources = {}, collections.Counter()
    mod_grid = {REKEY_GRID.get(k, k): v for k, v in mod_grid.items()}
    for stock_key, new_key in KEYS.items():
        objects = (mod_grid.get(stock_key) or {}).get("grid_objects") or []
        if objects:
            sources["authored by the mod"] += 1
        else:
            objects = races_grid.get(stock_key) or \
                (game_grid.get(stock_key) or {}).get("grid_objects") or []
            if not objects:
                # Interiors are only ever built for PLAYER ships, so a hull nobody flies
                # having none is normal, not a gap.
                sources["none upstream either"] += 1
                continue
            blanked = stock_key in mod_grid
            sources["derived from the stock hull" + (" (zip blanked it)" if blanked
                                                     else "")] += 1
        plans[new_key] = json.loads(json.dumps(objects))
    for why in sorted(sources):
        report.append(f"  interiors        {sources[why]:>2} {why}")

    # RECONCILE MAP SIZE AGAINST THE PLAN, before rendering anything.
    #
    # The renderer draws a w-by-h box, so a cell outside it is silently DROPPED - and the
    # mod shrinks several maps below the extent of the plan the hull ends up with. Two
    # hulls do it to plans the zip itself keeps (xim_battleship 20x20 -> 16x19 against a
    # 20x19 interior); a derived plan can too, since it was drawn for the stock hull's map.
    # Rooms outside the map are rooms damcons cannot reach, so the map grows back to the
    # size its interior needs rather than the interior losing rooms.
    #
    # This was originally a hardcoded list of two hulls. It is computed now because the
    # fallback tiers above create the same situation for hulls nobody thought to list.
    for key, objects in plans.items():
        if key not in by_key:
            continue
        need_w = max(int(o["x"]) for o in objects) + 1
        need_h = max(int(o["y"]) for o in objects) + 1
        have_w, have_h = by_key[key]["internalmapw"], by_key[key]["internalmaph"]
        if need_w > have_w or need_h > have_h:
            by_key[key]["internalmapw"] = max(have_w, need_w)
            by_key[key]["internalmaph"] = max(have_h, need_h)
            report.append(f"  map size grown   {key}: {have_w}x{have_h} -> "
                          f"{by_key[key]['internalmapw']}x{by_key[key]['internalmaph']} "
                          f"so its interior fits")

    written, unknown, renames = 0, set(), collections.Counter()
    for key in sorted(plans):
        if key not in by_key:
            report.append(f"  orphan interior  {key}: no ship entry, skipped")
            continue
        objects = resolve_stacks(plans[key], report, key)
        for obj in objects:
            renamed = DISAMBIGUATE.get((obj["name"], _role_key(obj)))
            if renamed and renamed != obj["name"]:
                obj["name"] = renamed
                renames[renamed] += 1
        w, h = by_key[key]["internalmapw"], by_key[key]["internalmaph"]
        text = grid_ascii_render(key, objects, w, h)

        def sig(objs):
            return sorted((int(o["x"]), int(o["y"]), o["name"].lower(),
                           ",".join(sorted(t.strip().lower()
                                           for t in o["roles"].split(","))))
                          for o in objs)

        back = grid_ascii_parse(text)["entry"]["grid_objects"]
        # Case is folded because that is exactly what LM's shipped `races` plans do to the
        # stock data (WARP -> warp): the format's normalization, not a loss.
        if sig(objects) != sig(back):
            raise SystemExit(f"round-trip mismatch on {key} - refusing to write")

        # Validated WITH the ship entry, so beam and tube CELL counts are checked against
        # what the hull carries. A plan whose weapon cells drift from shipData gives the
        # ship a damage pool its guns do not match.
        for level, msg in grid_ascii_validate(back, w, h, ship_data=by_key[key]):
            if level == "error":
                raise SystemExit(f"{key}: {msg}")
            if level == "warn":
                report.append(f"  WARN {key}: {msg}")
        for obj in objects:
            if grid_room_roles(obj["name"]) is None:
                unknown.add(obj["name"])

        with open(os.path.join(ADDON, key + ".grid"), "w", encoding="utf-8") as f:
            f.write(text)
        written += 1

    if renames:
        report.append("  disambiguated    "
                      + ", ".join(f"{n} x{c}" for n, c in sorted(renames.items())))
    if unknown:
        report.append(f"  new room types   {', '.join(sorted(unknown))} (roles inline)")
    report.append(f"  floor plans      {written}")
    return written


def build_ladders(report):
    """One fleet ladder per raiding faction, on LM's own pirate escalation curve."""
    for faction, hulls in sorted(LADDERS.items()):
        light, medium, heavy = hulls[0], hulls[1], hulls[2]
        flagship = hulls[3] if len(hulls) > 3 else heavy
        slot = {"L": light, "M": medium, "H": heavy, "F": flagship}
        fleets = [[[slot[c] for c in variant] for variant in tier]
                  for tier in LADDER_SHAPE]
        text = [
            f"# {faction} raiding fleets, by difficulty.",
            "#",
            "# Eleven tiers, five variants each; a variant is the ship keys making up one",
            "# fleet. Loaded when this faction is in the NPC_RACES setting.",
            "#",
            "# The escalation curve is LM's own races/pirate_fleets.yaml, which is built on",
            "# the same spread - three combat hulls plus a flagship. A shipped, played",
            "# curve beats an invented one.",
            f"race: {faction}",
            "fleets:",
        ]
        for difficulty, tier in enumerate(fleets):
            text.append(f"  # difficulty {difficulty}")
            text.append("  -")
            for variant in tier:
                text.append("    - [" + ", ".join(variant) + "]")
        name = f"tng_{faction.lower()}_fleets.yaml"
        with open(os.path.join(ADDON, name), "w", encoding="utf-8") as f:
            f.write("\n".join(text) + "\n")
    report.append(f"  fleet ladders    {len(LADDERS)} "
                  f"({', '.join(sorted(LADDERS))}); Federation has none by design")


def _ascii(lines):
    out = []
    for entry in lines:
        new = {}
        for f, text in entry.items():
            swapped = text.translate(_ASCII_FIXES)
            if any(ord(c) > 127 for c in swapped):
                raise SystemExit(f"non-ASCII left in a taunt: {swapped!r}")
            new[f] = swapped
        out.append(new)
    return out


def build_taunts(mod, base, report):
    """The five groups the author rewrote, keyed by the faction that now flies those hulls.

    Only the groups that differ from the zip's own baseline: it carries a year-old copy of
    the rest, and LM's `tsn` group is not in its file at all, so installing the file whole
    DELETES ten lines.

    Keyed LOWERCASE because taunts are looked up by `get_race`, and `SpaceObject.origin`
    lowercases. The stock race names are NOT kept as aliases here the way they were while
    this was a re-skin - these hulls no longer pretend to be Kralien.
    """
    changed = {k: v for k, v in mod.items() if v != base.get(k)}
    out = {}
    for race, lines in sorted(changed.items()):
        faction = TAUNT_FACTION.get(race)
        if faction:
            out[faction.lower()] = _ascii(lines)
    # Breen fly for the Dominion and have no lines of their own.
    for breen, serves in SERVES.items():
        if serves.lower() in out:
            out[breen.lower()] = out[serves.lower()]
    with open(os.path.join(ADDON, "tng_taunts.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=4, ensure_ascii=True)
        f.write("\n")
    report.append(f"  taunts           {', '.join(sorted(out))}")


def build_manifest(entries, report):
    """Which floor plan and ladder file belongs to which faction.

    So `__init__.mast` can be eight lines that loop, instead of fifty `grid_merge_ascii`
    calls that silently drift the moment a hull is renamed. The add-on reads this, asks the
    settings which factions are on, and loads only those.
    """
    interiors = collections.defaultdict(list)
    for entry in entries:
        name = entry["key"] + ".grid"
        if os.path.exists(os.path.join(ADDON, name)):
            interiors[faction_of(entry["key"])].append(name)
    manifest = {
        # VERSION STAMP. The add-on logs this and puts it in a shared variable, so a running
        # game can say which build of the mod it has - and the test range asserts it matches
        # the pack it loaded from, which is how a half-updated install gets caught.
        "mod": REPO,
        "version": mod_version(),
        "interiors": {f: sorted(v) for f, v in sorted(interiors.items())},
        "fleets": {f: f"tng_{f.lower()}_fleets.yaml" for f in sorted(LADDERS)},
        # Breen hulls are Dominion assets; they load with that faction rather than
        # needing their own settings entry.
        "serves": SERVES,
    }
    with open(os.path.join(ADDON, "tng_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=4)
        f.write("\n")
    report.append(f"  version          {REPO} {mod_version()}, art -> {art_path(mod_version())}")
    report.append("  manifest         "
                  + ", ".join(f"{f} {len(v)}" for f, v in manifest["interiors"].items()))


# Music entries the pack deliberately does not carry. Measured, not guessed: the zip's
# `default` bank is byte-identical to its `TNG_Music` one (19 of 19 files), so shipping
# both was the same audio twice under two names - 37 MB of it.
#
# The name is the real problem, not the duplication. `default` is the STOCK bank's name,
# and `true_path()` looks in data/audio/music first, so the copy in the pack is dead
# weight that does nothing - right up until someone installs it into the game's audio
# folder, at which point it silently replaces the default soundtrack for EVERY mission,
# not just the ones loading this mod. A mod's bank should be reachable by its own name.
_MUSIC_SKIP_BANKS = ("default",)
_AUDIO_SUFFIXES = (".ogg", ".wav", ".mp3")


def _skip_music(name, skipped):
    """Whether a `data/audio/music/...` zip entry is left out of the pack."""
    prefix = "data/audio/music/"
    if not name.startswith(prefix):
        return False
    rest = name[len(prefix):]
    bank = rest.split("/", 1)[0]
    if bank in _MUSIC_SKIP_BANKS:
        skipped[f"music/{bank} (duplicate of TNG_Music, and shadows the stock bank)"] += 1
        return True
    # `newfile.m` - two bytes of CRLF - rode along in TNG_Music. Anything that is not
    # audio is not part of a bank.
    if not rest.lower().endswith(_AUDIO_SUFFIXES):
        skipped["non-audio files under music/"] += 1
        return True
    return False


def copy_media(z, report):
    """Art into the shared-media pack, split by what the engine does with each kind."""
    buckets = {
        # MUSIC FIRST, and the order is load-bearing: the loop takes the first prefix that
        # matches, and "data/audio/" would otherwise swallow these.
        #
        # A music bank goes to media/music/<bank>, not media/audio/music/<bank>, because
        # that is where sbs_utils probes for a `@media/music` label - the same
        # <root>/<kind>/<path> rule skyboxes use. Under data/audio/ the bank resolved to
        # nothing and the label silently failed its file test, which is why the mod's
        # soundtrack had never played.
        "data/audio/music/": "music",
        "data/graphics/ships/": "ships",
        "data/graphics/fonts/": "fonts",
        "data/audio/": "audio",
    }
    counts, sizes = collections.Counter(), collections.Counter()
    skipped = collections.Counter()
    for name in z.namelist():
        if name.endswith("/"):
            continue
        if _skip_music(name, skipped):
            continue
        dest = None
        for prefix, folder in buckets.items():
            if name.startswith(prefix):
                dest = os.path.join(MEDIA, folder, name[len(prefix):])
                break
        if dest is None and name.startswith("data/graphics/"):
            # Face sheets and the logo sit loose in data/graphics.
            leaf = name[len("data/graphics/"):]
            if "/" not in leaf and leaf.lower().endswith(".png"):
                if " - Copy" in leaf:      # the zip ships duplicates of all seven
                    continue
                dest = os.path.join(MEDIA, "faces", leaf)
        if dest is None:
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        data = z.read(name)
        with open(dest, "wb") as f:
            f.write(data)
        folder = os.path.relpath(os.path.dirname(dest), MEDIA).split(os.sep)[0]
        counts[folder] += 1
        sizes[folder] += len(data)
    for folder in sorted(counts):
        report.append(f"  media/{folder:<11} {counts[folder]:>4} files, "
                      f"{sizes[folder] / 1048576:6.1f} MB")
    for why, n in sorted(skipped.items()):
        report.append(f"  skipped      {n:>4} {why}")


# Numeric fields the zip wrote as HJSON bare words with the separator glued on - `.86,` -
# which any JSON/HJSON reader hands back as the STRING ".86,". They reach the engine as
# text, and `mod_ship_data_process` does `float(val)` on them, so the hull dies with
# `could not convert string to float: '.86,'` the moment a player ship is created from it.
# Measured: 9 values across 6 hulls (turn_rate, ship_energy_cost, warp_energy_cost,
# radarscale). Repaired rather than left alone, because unlike the extra torpedo rooms
# this is not an authoring opinion - it is a value that cannot be read.
_NUM_JUNK = re.compile(r"^\s*(-?\d*\.?\d+)\s*,?\s*$")


def repair_numeric_strings(entry, report):
    """Coerce '.86,' -> 0.86 anywhere in one entry. Returns how many it fixed."""
    fixed = 0

    def walk(node, key, path):
        nonlocal fixed
        if isinstance(node, dict):
            for k in list(node):
                v = node[k]
                if isinstance(v, str):
                    m = _NUM_JUNK.match(v)
                    if m and ("," in v or v.strip().startswith(".")):
                        num = float(m.group(1))
                        node[k] = int(num) if num.is_integer() and "." not in m.group(1) else num
                        report.append(f"  REPAIR {path}/{k}: {v!r} -> {node[k]}")
                        fixed += 1
                else:
                    walk(v, k, path + "/" + str(k))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, key, path + "[" + str(i) + "]")

    walk(entry, "", str(entry.get("key", "?")))
    return fixed


def main():
    os.makedirs(ADDON, exist_ok=True)
    for stale in os.listdir(ADDON):
        if stale.endswith((".grid", "_fleets.yaml")):
            os.remove(os.path.join(ADDON, stale))

    zd = load_zip_data()
    game_ships, game_grid = load_game_data()
    report = []

    entries = build_ship_entries(zd["ships"], zd["ships_base"], game_ships, report)

    # Interiors FIRST: reconciling a map against its floor plan can change internalmapw/h,
    # and tng_ships.json has to be written after that, not before.
    build_interiors(zd["grid"], game_grid, load_races_grid(), entries, report)
    header = ("# GENERATED by _build_from_zip.py from Cosmos-TNG-Mod_v0-2-3.zip.\n"
              "#\n"
              "# UNIQUE KEYS: nothing here collides with data/shipData.yaml, so this mod\n"
              "# adds ships rather than replacing them.\n"
              "#\n"
              "# Each entry is the CURRENT game entry with only the fields the mod's\n"
              "# author changed applied on top - not the mod's copy of the entry, which\n"
              "# carries its year-old value for every field it never meant to touch.\n")
    # INTO THE MEDIA PACK, not the mastlib. The ENGINE reads this file itself, via
    # sbs.add_extra_ship_data(name, path) - so it has to be a real file in a real folder,
    # and a .mastlib is a zip. The unpacked shared-media pack is the one place a mod owns
    # that is both versioned and openable by the engine.
    #
    # The split this settles is not "art vs code". It is WHO READS IT: the engine needs
    # files on disk (art, ship data), MAST is happy inside a zip (labels, interiors,
    # ladders, taunts, sides).
    #
    # YAML, not JSON. `add_extra_ship_data` takes the name WITHOUT an extension and tries
    # .yaml then .json itself, so the format is the mod's choice - and YAML has real
    # comments, which JSON only fakes with the `//` lines every reader then has to strip.
    #
    # `artfilepath` IS NOT WRITTEN ANYWHERE. The field is obsolete as of engine v1.3.6 -
    # artfileroot carries the whole path on its own, resolved against the exe folder - so it
    # is stripped from every imported entry below and no longer patched in at load time.
    version = mod_version()
    numeric_fixed = 0
    for entry in entries:
        # artfileroot IS the path now, and artfilepath is gone from the engine's data.
        entry.pop("artfilepath", None)
        numeric_fixed += repair_numeric_strings(entry, report)
        root = str(entry.get("artfileroot", "") or "")
        if root and "/" not in root:
            entry["artfileroot"] = art_path(version) + "/" + root
    report.append(f"  numeric repairs  {numeric_fixed} unreadable value(s) coerced")
    os.makedirs(MEDIA, exist_ok=True)
    # WRITE JSON, AND ONLY JSON.
    #
    # THE ENGINE SEARCHES FOR .yaml FIRST. With both files present it takes the .yaml -
    # the one format it does not read properly yet - so shipping a .yaml beside the .json
    # meant the good file was never opened. That is a silent whole-file rejection: the
    # add-on merges library-side too, so the test range, every headless run and every name
    # lookup pass regardless, and only the ENGINE has no hulls.
    #
    # This used to be backwards: it wrote tng_ships.yaml (containing JSON) and then DELETED
    # tng_ships.json, leaving `_tools/ships_to_json.py` to convert one into the other.
    # There is no intermediate now - one generated file, in the format the engine reads.
    #
    # NO `#` HEADER COMMENTS. They are valid HJSON and NOT valid JSON, and the point of the
    # .json extension is that a strict reader can open it. Provenance lives in
    # tng_manifest.json, which carries mod and version.
    # newline="\n" IS LOAD-BEARING. Without it Windows text mode turns every
    # newline into a CRLF pair, and this was the ONLY ship-data file in the install with
    # CRLF endings - LM's two and the engine team's own BeamArcTest/extraShipDataAAA.json
    # are all bare LF. Whether the engine's HJSON reader is what chokes on that is being
    # measured separately (probes tng_probe_lf / tng_probe_crlf_small); LF is what every
    # file the engine DOES accept uses, so match them regardless.
    with open(os.path.join(MEDIA, "tng_ships.json"), "w", encoding="utf-8",
              newline="\n") as f:
        f.write(json.dumps({"#ship-list": entries}, indent=2,
                           ensure_ascii=True) + chr(10))

    # And remove the .yaml, or the engine finds it again on the next run.
    for stale in ("tng_ships.yaml",):
        if os.path.exists(os.path.join(MEDIA, stale)):
            os.remove(os.path.join(MEDIA, stale))

    n = verify_yaml_roundtrip(os.path.join(MEDIA, "tng_ships.json"), entries)
    report.insert(0, f"  ship entries     {n} (media/tng_ships.json, the ONLY ship file; round-trips)")

    build_ladders(report)
    build_taunts(zd["taunts"], zd["taunts_base"], report)
    build_manifest(entries, report)
    if "--no-art" not in sys.argv:
        copy_media(zd["zip"], report)

    print("Cosmos-TNG-Mod built from " + os.path.basename(ZIP))
    for line in report:
        print(line)


if __name__ == "__main__":
    main()
