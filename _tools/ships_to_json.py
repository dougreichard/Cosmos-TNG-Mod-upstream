"""Emit the engine's copy of the ship data as JSON, from the authored YAML.

WHY BOTH FORMATS. YAML is the preferred authoring format and stays the source of truth -
it is what a person edits and what the diff is readable in. This writes the ENGINE's copy
as JSON because the engine's own YAML reader currently has problems, and `add_extra_ship_data`
accepts either.

It is NOT about parse speed on the script side. Measured on this file (119 KB):

    ryaml (PyAddons, what the engine and mission_runner use)   0.007 s
    json.loads                                                0.001 s
    bundled yaml (the fallback, when PyAddons is not present)  0.220 s

Six milliseconds. The reason is the engine reader, not the clock. (The one place the
format does pay is a run with no PyAddons on the path, where the fallback costs 220ms a
file - see sbs_utils/fs.load_yaml_string.)

STALENESS IS THE REAL RISK, so `--check` exists and the loader warns: the JSON is a
generated artifact and the YAML is the source, and an edit to the YAML that never gets
re-emitted leaves the engine reading yesterday's hulls while the library reads today's.
That divergence is invisible - both files parse, both look right, and only the hulls
disagree.

Usage:
    python ships_to_json.py            # regenerate media/tng_ships.json
    python ships_to_json.py --check    # exit 1 if the JSON is missing or stale
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(os.path.join(HERE, "..", "media", "tng_ships.yaml"))
DST = os.path.abspath(os.path.join(HERE, "..", "media", "tng_ships.json"))

# PyAddons carries ryaml, the fast parser the engine uses. Falling back to the bundled one
# is fine here - this is a build step, not a hot path.
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "sbs_utils")))
sys.path.append(os.path.abspath(os.path.join(HERE, "..", "..", "..", "..", "PyAddons")))


def load(path):
    from sbs_utils.fs import load_yaml_string
    text = open(path, encoding="utf-8").read()
    # The authored file carries `//` line comments, which the engine's reader tolerates and
    # neither YAML parser does. Stripped the same way tng_declare_ships strips them.
    return load_yaml_string(re.sub(r"^[ \t]*//.*$", "", text, flags=re.M))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="verify the JSON exists and is no older than the YAML")
    a = ap.parse_args()

    if not os.path.exists(SRC):
        print("no source: " + SRC)
        return 1

    if a.check:
        if not os.path.exists(DST):
            print("STALE: " + os.path.basename(DST) + " does not exist - run ships_to_json.py")
            return 1
        if os.path.getmtime(DST) < os.path.getmtime(SRC):
            print("STALE: " + os.path.basename(DST) + " is older than the YAML - re-run ships_to_json.py")
            return 1
        print("ok: " + os.path.basename(DST) + " is current")
        return 0

    data = load(SRC)
    if not isinstance(data, dict) or "#ship-list" not in data:
        print("source did not parse to a '#ship-list' dict")
        return 1
    with open(DST, "w", encoding="utf-8") as f:
        # Compact but not minified: this is a generated file, and a readable one still
        # diffs when a hull changes.
        json.dump(data, f, indent=1)
    print("wrote %s  %d hulls  %.0f KB" % (
        os.path.basename(DST), len(data["#ship-list"]), os.path.getsize(DST) / 1024))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
