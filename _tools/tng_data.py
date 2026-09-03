"""Shared loaders for the TNG balance tools.

Kept apart from the tools themselves because scale_report, balance_report and
retune_ships all need the same three things - the ship list, a hull's weight
class, and the size the engine actually draws a hull at - and three copies of
"how do I read a beam port" is how the numbers drift.

NOT a mod addon: nothing here is imported by MAST, so the `tng_` name-prefix
rule for addon functions does not apply.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIPS = os.path.join(ROOT, "media", "tng_ships.json")
CANON = os.path.join(ROOT, "_tools", "canon_lengths.json")
TARGETS = os.path.join(ROOT, "_tools", "balance_targets.json")
MESH_DIR = os.path.join(ROOT, "media", "ships")

#: Weight classes, weakest first. Order is load-bearing: `weight_class` returns the
#: FIRST one a hull's roles mention, and `station` has to win over anything else a
#: station happens to carry (Terok Nor is "station,carrier").
CLASS_ORDER = ("station", "civilian", "fighter", "shuttle", "light", "medium", "heavy", "capital")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def ships():
    """The #ship-list, in file order."""
    return load_json(SHIPS)["#ship-list"]


def roles_of(entry):
    """Roles as a stripped set.

    The strip is not cosmetic. `tng_orn_brigand` is written "ship, pirate" and
    `tng_fed_olympic` "ship, civilian,transport", so a bare split on "," yields
    " pirate" and " civilian" - roles that match nothing. Stock shipData has the
    same wart, so read defensively even after the data is fixed.
    """
    return {r.strip() for r in (entry.get("roles") or "").split(",") if r.strip()}


def weight_class(entry):
    """The hull's weight class, or None when it declares none.

    `capital` is not a role anyone writes - it is `leader` on a warship, which is
    how the Scimitar and the Damar are already marked.
    """
    roles = roles_of(entry)
    if "station" in roles:
        return "station"
    if "leader" in roles and "warship" in roles:
        return "capital"
    for cls in CLASS_ORDER:
        if cls in roles:
            return cls
    return None


def beam_ports(entry):
    """Every beam port on a hull.

    A port group counts as weaponry when its NAME STARTS WITH "beam" - that is the
    engine's own rule, and it is why "exhaust" (pure VFX) is excluded while the
    monster art's "beam Bite" would be included.
    """
    out = []
    for group, ports in (entry.get("hull_port_sets") or {}).items():
        if not group.startswith("beam"):
            continue
        out.extend(ports)
    return out


def coef_sum(entry):
    """Sum of damage_coeff/cycle_time over every beam - the hull's gun rating.

    This, NOT `damage_coeff`, is what compares two ships. Per-shot damage is
    `set_beam_damages` base x damage_coeff, and LegendaryMissions sets that base to
    7.0 for players and DIFFICULTY/2+3 for NPCs (5.5 at DIFFICULTY 5). So real DPS
    is coef_sum x base, and coef_sum is the part a ship's data controls.
    """
    total = 0.0
    for b in beam_ports(entry):
        cycle = b.get("cycle_time") or 1.0
        total += (b.get("damage_coeff") or 0.0) / cycle
    return total


def front_shield(entry):
    sh = entry.get("shields") or [0]
    return sh[0] if sh else 0


_mesh_cache = {}


def mesh_extent(entry):
    """Longest axis of the hull's .obj bounding box, in the mesh's own units.

    Returns None when the hull ships no mesh - the three bases that borrow stock art
    (kralien_station / skaraan_station / torgoth_station) are the real cases, and a
    missing mesh is not an error for them.

    Only "v " lines are parsed, which is why this is cheap enough to run on every
    build despite the meshes totalling ~195 MB.
    """
    root = os.path.basename(str(entry.get("artfileroot") or ""))
    if not root:
        return None
    if root in _mesh_cache:
        return _mesh_cache[root]
    path = os.path.join(MESH_DIR, root + ".obj")
    if not os.path.exists(path):
        _mesh_cache[root] = None
        return None
    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    with open(path, "r", errors="ignore") as f:
        for line in f:
            if line[:2] != "v ":
                continue
            parts = line.split()
            if len(parts) < 4:
                continue
            try:
                xyz = (float(parts[1]), float(parts[2]), float(parts[3]))
            except ValueError:
                continue
            for i in range(3):
                if xyz[i] < lo[i]:
                    lo[i] = xyz[i]
                if xyz[i] > hi[i]:
                    hi[i] = xyz[i]
    ext = None if hi[0] == float("-inf") else max(hi[i] - lo[i] for i in range(3))
    _mesh_cache[root] = ext
    return ext


def drawn_size(entry):
    """Size the engine draws the hull at, in game units: mesh extent x meshscale.

    This is the only honest measure of a ship's size. `meshscale` alone says nothing,
    because each model was exported at its own native scale - the mod's meshscales
    span 0.01 to 0.84 for ships whose drawn sizes span 5 to 742.
    """
    ext = mesh_extent(entry)
    if ext is None:
        return None
    return ext * float(entry.get("meshscale") or 0.0)
