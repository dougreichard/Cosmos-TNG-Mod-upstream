"""Generate `media/tng_reskin.json` - the CONVERSION half of this mod.

WHAT IT IS FOR. The mod proper gives its hulls their own `tng_*` keys, which is what makes
it additive: a mission can spawn a Saber and a Light Cruiser in the same game, and two Trek
mods can coexist. That decision is right and it stays.

But a mission written before this mod existed names STOCK keys, in literals, in its own
content. LegendaryMissions hardcodes `enemyTypeNameList = ["Kralien", "Torgoth",
"Arvonian"]` in every map and thirteen `station_type` keys across its maps and prefabs.
Nothing about that reads a setting, so no profile can point it at TNG art - the hulls are
available and never asked for.

So this writes a SECOND ship-data file that declares the stock keys carrying TNG ships.
An add-on entry overrides a key `data/shipData.yaml` already owns - engine-verified 1.3.5,
`missions/shipdata_override` - so with this loaded, every Kralien battleship LM spawns is a
Negh'Var and every starbase is a Federation station, without editing one line of LM.

It is opt-in. Nothing loads it unless a profile includes the `tng_reskin` add-on, so the
additive mod is untouched and the conversion is a command-line flag.

WHAT IT COPIES, AND THE TWO FIELDS IT DOES NOT.

Everything comes from the TNG entry - art, name, description, shields, beams, torpedoes,
turn rate, scale - except `key`, `side` and `roles`, which are kept from the STOCK entry.
Those two are not stats, they are wiring:

  * `side` - stock `Kralien` becomes TNG `Cardassian`. LM picks ships with
    `filter_ship_data_by_side`, so a converted side means a map asking for a Kralien ship
    finds none and spawns nothing.
  * `roles` - `station` is how docking, comms and the market find a station at all; some
    TNG entries also carry `carrier`, which would give a starbase a hangar it never had.

Keeping them means the conversion changes what a ship IS and looks like, and never changes
what the mission around it can find.

Run:  python _tools/make_reskin.py        (from the Cosmos-TNG-Mod folder)
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.dirname(HERE)
MEDIA = os.path.join(MOD, "media")

# The stock -> TNG map lives in _build_from_zip.py and is the mod's own directing work.
# Read it rather than copying it, so the two cannot drift.
def stock_to_tng():
    src = io.open(os.path.join(MOD, "_build_from_zip.py"), encoding="utf-8").read()
    m = re.search(r"^KEYS\s*=\s*\{", src, re.M)
    if not m:
        raise SystemExit("KEYS not found in _build_from_zip.py")
    depth, i = 1, m.end()
    while depth and i < len(src):
        depth += (src[i] == "{") - (src[i] == "}")
        i += 1
    return dict(re.findall(r'"([^"]+)"\s*:\s*"(tng_[a-z0-9_]+)"', src[m.end():i - 1]))


def main():
    from_stock = stock_to_tng()
    ships_path = os.path.join(MEDIA, "tng_ships.json")
    tng = {e["key"]: e for e in json.loads(io.open(ships_path, encoding="utf-8").read())["#ship-list"]}

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(MOD)), "missions", "sbs_utils"))
    from sbs_utils.fs import test_set_exe_dir
    test_set_exe_dir()
    from sbs_utils.procedural.ship_data import get_ship_data_for

    out, missing_tng, missing_stock = [], [], []
    for stock_key, tng_key in sorted(from_stock.items()):
        tng_entry = tng.get(tng_key)
        if tng_entry is None:
            missing_tng.append((stock_key, tng_key))
            continue
        stock_entry = get_ship_data_for(stock_key)
        if stock_entry is None:
            # A stock key the installed game does not have. Declaring it would ADD a ship
            # rather than convert one, which is the additive mod's job, not this file's.
            missing_stock.append(stock_key)
            continue
        entry = dict(tng_entry)
        entry["key"] = stock_key
        for wiring in ("side", "roles"):
            if stock_entry.get(wiring) is not None:
                entry[wiring] = stock_entry[wiring]
        entry.pop("#mod", None)
        out.append(entry)

    text = json.dumps({"#ship-list": out}, indent=2, ensure_ascii=True) + chr(10)
    # newline="\n" and a trailing newline are both load-bearing: the engine reader is line
    # oriented, and a file whose last line is unterminated is rejected WHOLE with
    # "End of input while parsing an object" - on a file every JSON parser reads happily.
    dest = os.path.join(MEDIA, "tng_reskin.json")
    io.open(dest, "w", encoding="utf-8", newline="\n").write(text)

    json.loads(io.open(dest, encoding="utf-8").read())      # never ship one that will not re-read
    print(f"  wrote {os.path.relpath(dest, MOD)}: {len(out)} stock keys re-skinned")
    if missing_tng:
        print(f"  no TNG hull for: {[k for k, _ in missing_tng]}")
    if missing_stock:
        print(f"  not in this install's shipData (skipped): {missing_stock}")


if __name__ == "__main__":
    main()
