#!/usr/bin/env python3
"""Validate Cosmos 3D art against what the engine's mesh loader will accept.

Written after a client running "Gamma with a Q" hit this assert:

    elementCount && "elementCount is zero for DX11PaxGraphicsClass::CreateIndexList"

Symbolizing the shipping exe against its PDB put that assert in
`DX11PaxGraphicsClass::CreateIndexList(name, elementCount)`, checked on entry, and the only
callers are the two mesh loaders in the same class - `Load3dObject` (.paxmesh, falling back
to .obj) and `Load3DObjectNative` (.paxmesh). Every other call site at that vtable slot
belongs to a different class. So the assert is a MESH LOAD event, not a draw event: it
fires the first time a client loads a piece of 3D art whose render segment has no indices.

The engine's own guards stop short of it. `Load3DObjectNative` asserts numRenderSegments,
numTextureNames, numVertLists and numIndexLists are all > 0 - how many LISTS there are,
never how many ELEMENTS are in a list. The .obj path checks neither. So one zero-length
segment walks straight into the assert, and the process dies with a modal dialog.

This tool checks the art on disk for that condition and for the things that produce it.
It is stdlib-only and read-only. Run it against a Cosmos install:

    python check_art.py                 # infer the install root from this file's location
    python check_art.py E:/a/Cosmos-dev
    python check_art.py --quiet         # errors and warnings only, no INFO, no bake list

Exit code is 0 when nothing is wrong and 1 when any ERROR was reported, so it can gate a
release.

TWO THINGS THIS TOOL DELIBERATELY DOES NOT CALL ERRORS
------------------------------------------------------
*Aliasing* - two ship keys sharing one artfileroot - is reported as INFO, not as a problem.
The engine keeps name-keyed registries (`map<string, PAX3DObject*>`,
`map<string, PaxIndexList*>`) whose key is the artfileroot AS SPELLED, so an identical
artfileroot is a cache HIT. That is the intended way to reskin, and the TNG mod relies on
it five times, including three bases pointing at stock art.

*Unbaked art* is reported as a checklist, not as a failure. A `.paxmesh` is baked on demand
the first time something draws the hull, and it embeds the folder it was baked in - so it
must be produced on the machine that runs it and must never be packaged.
"""

import argparse
import collections
import json
import os
import re
import struct
import sys

# A render segment is one face-bearing RUN: a new run starts at every `g`/`o` change AND at
# every `usemtl` change. Verified exact on 233 of 233 obj/paxmesh pairs in a full install,
# including 32 baked by the engine while writing this.
#
# The identity of a segment is the GROUP - the baked list name is
# "<artfileroot>_<group>_verts_<n>". A material change inside a group still splits it, and
# the engine mints a name for the extra piece by suffixing "_2" (FED_Ambassador has four
# `o` groups and five segments, the fifth named `Ambassador_Class_Windows_2`).
#
# Two wrong rules came before this one, and both made the tool tell an operator to DELETE
# derived art that was perfectly good:
#   * "one per group"                 - 3 mismatches
#   * "one per (group, material) pair" - 2 mismatches; right count, wrong mechanism, and it
#     still mis-called TSN_Dreadnought and TSN_Escort, whose single group cycles
#     A-B-C-B-C through materials. Distinct pairs counts that as 3; the engine makes 5.
# Runs are what the engine actually does. A false "delete your bake" is the worst thing
# this tool could say, so the rule is measured, not reasoned.
RUN_BREAK_KEYS = ("g", "o", "usemtl")

# Inside a .paxmesh a named list is introduced by a 0x01 marker, then a uint16 length, then
# that many bytes of name: "<artfileroot as spelled>_<group>_verts_<n>". Scanning for the
# marker is exact. Anchoring on the "_verts_<n>" tail with a regex is NOT - the digits run
# straight on into the binary payload, so the match ends one byte late and the whole name is
# lost. That misread 16 stock meshes the game renders every day as having no lists at all.
LIST_MARKER = 0x01
MAX_LIST_NAME = 400
MIN_LIST_NAME = 8

# Bytes per element, measured across every mesh in a full install.
VERTEX_STRIDE = 100
INDEX_STRIDE = 4

DERIVED_SUFFIXES = (".paxmesh", ".pointcube", "1024.png", "256.png", ".rawbitmap")


class Report:
    """Collects findings so the summary can be ordered by severity rather than by check."""

    def __init__(self, quiet=False):
        self.rows = collections.defaultdict(list)
        self.quiet = quiet

    def add(self, level, check, message):
        self.rows[level].append((check, message))

    error = lambda self, c, m: self.add("ERROR", c, m)
    warn = lambda self, c, m: self.add("WARN", c, m)
    info = lambda self, c, m: self.add("INFO", c, m)

    def emit(self):
        shown = ("ERROR", "WARN") if self.quiet else ("ERROR", "WARN", "INFO")
        for level in shown:
            rows = self.rows.get(level)
            if not rows:
                continue
            print("\n%s (%d)" % (level, len(rows)))
            print("-" * 78)
            for check, message in rows:
                print("  [%-22s] %s" % (check, message))
        return len(self.rows.get("ERROR", []))


# ---------------------------------------------------------------------------
# readers
# ---------------------------------------------------------------------------

def load_ship_table(path):
    """Parse a Cosmos ship-data file.

    The engine reads these as HJSON, not YAML, whatever the extension says -
    `data/shipData.yaml` states so in its own header. The only two HJSON liberties the
    shipped files actually take are `#` comment lines and trailing commas, so stripping
    those and handing the rest to json is enough and keeps this tool stdlib-only.
    """
    kept = []
    for line in open(path, encoding="utf-8", errors="replace"):
        stripped = line.lstrip()
        if stripped.startswith("#") or stripped.startswith("//"):
            continue
        kept.append(line)
    text = re.sub(r",(\s*[}\]])", r"\1", "".join(kept))
    return json.loads(text).get("#ship-list", [])


def obj_segments(path):
    """Return (face count per face-bearing run, total face count).

    A run ends at any `g`/`o` or `usemtl` line; runs with no faces are not emitted, which is
    why the `g default` header 37 stock meshes carry costs nothing.
    """
    runs = []
    current = 0
    seen_any = False
    faces = 0
    for line in open(path, "r", errors="replace"):
        fields = line.split()
        if not fields:
            continue
        if fields[0] == "f":
            faces += 1
            current += 1
            seen_any = True
        elif fields[0] in RUN_BREAK_KEYS:
            if current:
                runs.append(current)
            current = 0
            seen_any = True
    if current:
        runs.append(current)
    if not seen_any and faces:
        runs = [faces]
    return runs, faces


def paxmesh_lists(path):
    """Return (vert names, index names, {name: (declared count, payload bytes, stride)}).

    Layout, decoded from the shipped files: a named list is `0x01`, a uint16 name length,
    the name, then a **uint32 element count**, then the data. Vertices are a flat 100-byte
    stride in every one of the 234 meshes in a full install; indices are uint32.

    Reading the DECLARED count matters more than any of the derived checks: it is exactly
    the value the engine asserts on, so a zero here is the crash sitting on disk rather than
    an inference about one.

    Payload is measured to the next list marker, so it OVER-states the real data (per-segment
    trailer follows the indices). Only ever test it as a lower bound - `payload < count *
    stride` means truncated; `payload > count * 4` on an index list is normal.
    """
    data = open(path, "rb").read()
    found = []
    limit = len(data) - 3
    pos = data.find(bytes([LIST_MARKER]))
    while 0 <= pos < limit:
        length = struct.unpack_from("<H", data, pos + 1)[0]
        if MIN_LIST_NAME <= length <= MAX_LIST_NAME and pos + 3 + length <= len(data):
            raw = data[pos + 3:pos + 3 + length]
            if all(32 <= b < 127 for b in raw):
                name = raw.decode("ascii")
                if "_verts_" in name or "_indexes_" in name:
                    found.append((pos, pos + 3 + length, name))
        pos = data.find(bytes([LIST_MARKER]), pos + 1)

    stats = {}
    for i, (_marker, end, name) in enumerate(found):
        nxt = found[i + 1][0] if i + 1 < len(found) else len(data)
        if end + 4 > len(data):
            stats[name] = (None, nxt - end, None)
            continue
        count = struct.unpack_from("<I", data, end)[0]
        payload = nxt - end - 4
        stride = INDEX_STRIDE if "_indexes_" in name else VERTEX_STRIDE
        stats[name] = (count, payload, stride)
    verts = [n for _m, _e, n in found if "_verts_" in n]
    indexes = [n for _m, _e, n in found if "_indexes_" in n]
    return verts, indexes, stats


# ---------------------------------------------------------------------------
# resolution
# ---------------------------------------------------------------------------

def short_root(artfileroot):
    """An artfileroot shortened for display: "<pack tag>/<basename>".

    A pack path is ~90 characters of boilerplate ("data/missions/__lib__/media/
    ScornMandark.Cosmos-TNG-Mod.media.v0.3.0/ships/FED_Galaxy"), and truncating it from
    either end hides the half that identifies the hull.
    """
    parts = artfileroot.replace("\\", "/").split("/")
    if len(parts) <= 2:
        return artfileroot
    pack = next((p for p in parts if ".media." in p), parts[-2])
    tag = pack.split(".media.")[0].split(".")[-1] if ".media." in pack else pack
    return tag + "/" + parts[-1]


def resolve_root(install, artfileroot):
    """Resolve an artfileroot to an extensionless on-disk path, or None.

    Two spellings are both live in a current install, so both are tried:
      * exe-relative, carrying the whole path - what engine v1.3.6 introduced and what
        every mod pack now writes.
      * graphics-relative - what stock `data/shipData.yaml` uses ("ships/kralien_station").
    """
    if not artfileroot:
        return None, None
    candidates = [
        (os.path.join(install, artfileroot.replace("/", os.sep)), "exe-relative"),
        (os.path.join(install, "data", "graphics", artfileroot.replace("/", os.sep)),
         "graphics-relative"),
    ]
    for base, how in candidates:
        if os.path.exists(base + ".obj") or os.path.exists(base + ".paxmesh"):
            return base, how
    return None, None


def find_ship_tables(install):
    tables = []
    stock = os.path.join(install, "data", "shipData.yaml")
    if os.path.exists(stock):
        tables.append(stock)
    packs = os.path.join(install, "data", "missions", "__lib__", "media")
    if os.path.isdir(packs):
        for pack in sorted(os.listdir(packs)):
            # The media folder holds loose bookkeeping files (.stamp.json) beside the
            # unpacked packs, so only descend into real directories.
            if not os.path.isdir(os.path.join(packs, pack)):
                continue
            for name in sorted(os.listdir(os.path.join(packs, pack))):
                if not name.endswith((".json", ".yaml", ".yml")):
                    continue
                path = os.path.join(packs, pack, name)
                try:
                    if "#ship-list" in open(path, encoding="utf-8", errors="replace").read():
                        tables.append(path)
                except OSError:
                    continue
    return tables


def art_dirs(install):
    dirs = [os.path.join(install, "data", "graphics")]
    packs = os.path.join(install, "data", "missions", "__lib__", "media")
    if os.path.isdir(packs):
        dirs.append(packs)
    return dirs


# ---------------------------------------------------------------------------
# checks
# ---------------------------------------------------------------------------

def check_meshes(install, report):
    """Walk every .obj and .paxmesh the engine can reach and validate it standalone."""
    obj_count = pax_count = 0
    for top in art_dirs(install):
        for dirpath, _dirnames, filenames in os.walk(top):
            for name in sorted(filenames):
                path = os.path.join(dirpath, name)
                shown = os.path.relpath(path, install).replace("\\", "/")
                lower = name.lower()

                if lower.endswith(".obj"):
                    obj_count += 1
                    try:
                        segments, faces = obj_segments(path)
                    except OSError as exc:
                        report.error("obj-unreadable", "%s: %s" % (shown, exc))
                        continue
                    if faces == 0:
                        report.error("obj-zero-faces",
                                     "%s has no faces - loading it asks DX11 for a "
                                     "zero-element index list" % shown)
                    if not segments:
                        report.error("obj-all-segments-empty",
                                     "%s: no face-bearing render segment" % shown)

                elif lower.endswith(".paxmesh"):
                    pax_count += 1
                    try:
                        verts, indexes, payloads = paxmesh_lists(path)
                    except (OSError, struct.error) as exc:
                        report.error("paxmesh-unreadable", "%s: %s" % (shown, exc))
                        continue
                    if not verts or not indexes:
                        report.error("paxmesh-no-lists",
                                     "%s: %d vert lists, %d index lists - the engine "
                                     "asserts on either being zero"
                                     % (shown, len(verts), len(indexes)))
                        continue
                    if len(verts) != len(indexes):
                        report.error("paxmesh-unpaired",
                                     "%s: %d vert lists but %d index lists"
                                     % (shown, len(verts), len(indexes)))
                    for name_ in verts + indexes:
                        count, payload, stride = payloads.get(name_, (None, 0, None))
                        if count is None:
                            report.error("paxmesh-headerless",
                                         "%s: list %r has no element count" % (shown, name_))
                        elif count == 0:
                            report.error("paxmesh-zero-elements",
                                         "%s: list %r declares 0 elements - this is the "
                                         "CreateIndexList assert, sitting on disk"
                                         % (shown, name_))
                        elif payload < count * stride:
                            report.error("paxmesh-truncated",
                                         "%s: list %r declares %d elements (%d bytes) but "
                                         "only %d bytes follow"
                                         % (shown, name_, count, count * stride, payload))
    return obj_count, pax_count


def check_stale_bakes(install, report):
    """A .paxmesh whose segment count disagrees with its .obj was baked from other art.

    The baker emits exactly one index list per face-bearing run, so a disagreement means
    the .obj changed underneath the bake. The stale mesh is what the engine will actually draw,
    because Load3dObject prefers .paxmesh and never looks at the .obj again.
    """
    for top in art_dirs(install):
        for dirpath, _dirnames, filenames in os.walk(top):
            for name in sorted(filenames):
                if not name.lower().endswith(".paxmesh"):
                    continue
                pax = os.path.join(dirpath, name)
                obj = os.path.splitext(pax)[0] + ".obj"
                if not os.path.exists(obj):
                    continue
                shown = os.path.relpath(pax, install).replace("\\", "/")
                try:
                    verts, _indexes, _stats = paxmesh_lists(pax)
                    segments, _faces = obj_segments(obj)
                except (OSError, struct.error):
                    continue
                if len(verts) != len(segments):
                    report.warn("paxmesh-stale",
                                "%s has %d segments but its .obj has %d face-bearing runs - "
                                "baked from different art; delete it to force a re-bake"
                                % (shown, len(verts), len(segments)))


def check_misplaced_derived(install, report):
    """Derived art written outside the folder its source lives in.

    The engine has been seen writing `<root>256.png` and a whole .paxmesh into the exe root
    rather than beside the art. A stray copy is not loaded, but it is a duplicate that
    drifts from the real one - a .paxmesh embeds the folder it was baked in, so two copies
    of the same name are never interchangeable.
    """
    for name in sorted(os.listdir(install)):
        if not name.endswith(DERIVED_SUFFIXES):
            continue
        path = os.path.join(install, name)
        if not os.path.isfile(path):
            continue
        report.warn("derived-in-exe-root",
                    "%s sits in the install root, not beside its source art - safe to "
                    "delete; the real copy lives under data/graphics" % name)


def check_declarations(install, report):
    """Cross-check every declared artfileroot against the art on disk.

    Returns {artfileroot: {keys}} for every declared root with no .paxmesh yet.
    """
    by_root = collections.defaultdict(list)
    tables = find_ship_tables(install)
    if not tables:
        report.warn("no-ship-tables", "found no ship-data files under %s" % install)
        return {}

    unresolved = 0
    unbaked = {}
    for table in tables:
        label = os.path.relpath(table, install).replace("\\", "/")
        try:
            entries = load_ship_table(table)
        except (ValueError, OSError) as exc:
            report.error("ship-table-unreadable", "%s: %s" % (label, exc))
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            key = entry.get("key") or entry.get("name") or "<unnamed>"
            root = entry.get("artfileroot")
            if not root:
                continue
            by_root[root].append((key, label))
            base, _how = resolve_root(install, root)
            if base is None:
                unresolved += 1
                report.error("artfileroot-missing",
                             "%s declares artfileroot %r with no .obj and no .paxmesh - "
                             "the engine asserts \"the artfileroot of this ship was not "
                             "found\"" % (key, root))
                continue
            if not os.path.exists(base + ".paxmesh"):
                # Keyed by ROOT, not by key: baking is per art file, and a root that four
                # reskinned keys share still only needs drawing once.
                unbaked.setdefault(root, set()).add(key)

    # Aliasing: informational. Same spelling means the same registry key means a cache hit.
    for root, users in sorted(by_root.items()):
        keys = sorted({k for k, _t in users})
        if len(keys) > 1:
            report.info("artfileroot-alias",
                        "%d keys share artfileroot %r (%s) - this is a cache hit, not a "
                        "fault" % (len(keys), root, ", ".join(keys)))

    # The real aliasing hazard: two DIFFERENT art files reaching one registry name. The key
    # is the artfileroot as spelled, so this only happens when two spellings differ but name
    # the same file, or when one spelling resolves differently for different consumers.
    by_resolved = collections.defaultdict(set)
    for root in by_root:
        base, _how = resolve_root(install, root)
        if base is not None:
            by_resolved[os.path.normcase(os.path.abspath(base))].add(root)
    for base, spellings in sorted(by_resolved.items()):
        if len(spellings) > 1:
            report.warn("artfileroot-double-load",
                        "%s is named by %d different spellings (%s) - the engine keys its "
                        "mesh cache by the spelling, so it loads and bakes the same art "
                        "once per spelling"
                        % (os.path.basename(base), len(spellings),
                           ", ".join(sorted(spellings))))

    return unbaked

def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("install", nargs="?", default=None,
                        help="Cosmos install root (the folder holding Artemis3-x64-*.exe)")
    parser.add_argument("--quiet", action="store_true",
                        help="errors and warnings only - no INFO, no bake checklist")
    args = parser.parse_args()

    install = args.install
    if install is None:
        # .../<install>/data/missions/Cosmos-TNG-Mod/_tools/check_art.py
        here = os.path.dirname(os.path.abspath(__file__))
        install = os.path.abspath(os.path.join(here, "..", "..", "..", ".."))
    install = os.path.abspath(install)
    if not os.path.isdir(os.path.join(install, "data", "graphics")):
        sys.exit("no data/graphics under %s - pass the Cosmos install root explicitly"
                 % install)

    print("checking art under %s" % install)
    report = Report(quiet=args.quiet)
    obj_count, pax_count = check_meshes(install, report)
    check_stale_bakes(install, report)
    check_misplaced_derived(install, report)
    unbaked = check_declarations(install, report)

    errors = report.emit()
    if unbaked and not args.quiet:
        print("\nNOT YET BAKED (%d art files) - each bakes at first draw, mid-session"
              % len(unbaked))
        print("-" * 78)
        for root in sorted(unbaked, key=short_root):
            users = sorted(unbaked[root])
            shown = users[0] if len(users) == 1 else "%s +%d" % (users[0], len(users) - 1)
            print("  %-46s %s" % (short_root(root), shown))
        print("\n  Draw each once before the session so no bake lands during play."
              "\n  The bake only runs in the REAL engine - the mock never writes a"
              "\n  .paxmesh, so a green headless run proves nothing here.")
    print("\n%d .obj and %d .paxmesh checked; %d error(s), %d warning(s)"
          % (obj_count, pax_count, errors, len(report.rows.get("WARN", []))))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
