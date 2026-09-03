"""Apply _tools/balance_targets.json to media/tng_ships.json.

    python _tools/retune_ships.py --dry-run    # show every change, write nothing
    python _tools/retune_ships.py              # write the ship data

WHY A GENERATOR AND NOT HAND-EDITING. The ship file is 140 KB and the interesting
part of it - "how tough is a Galaxy, and how does that compare to a Vor'Cha" - is
spread across 361 beam ports. Editing it by hand is how the two shipped ship files
drifted apart by exactly 1.2x on every Federation beam without anyone noticing. With
this, the balance lives in a 60-line table and the ship data is output.

WHAT IS PRESERVED. Each hull keeps the SHAPE of its own battery. Beam damage is
scaled by one shared factor to hit the hull's gun target, cycles by another, ranges
by a third - so a Defiant's four fast pulse phasers stay four times faster than its
main guns, and a Mogai's spinal stays its longest-reaching weapon. What changes is
where the whole battery sits, never its internal proportions.

WHAT IS NOT TOUCHED. Beam positions, colours, barrel angles, art, interiors, faces,
descriptions, energy costs. This edits combat numbers and physical scale, nothing
else.
"""
import json
import os
import sys
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tng_data as T                                            # noqa: E402

#: Radar icon size by class. Stock spans 0.3 (fighter) to 1.2 (dreadnought), so this
#: is the same spread, keyed to the class rather than left to track `meshscale` -
#: which it currently does only loosely.
RADAR_BY_CLASS = {
    "fighter": 0.30, "shuttle": 0.30, "light": 0.60, "medium": 0.75,
    "heavy": 0.90, "capital": 1.10, "civilian": 0.70, "station": 1.00,
}

#: A beam this narrow is a spinal lance, not a turret - the Galaxy-X's forward cannon
#: and the Romulan warbirds' plasma spinal. Those keep their own arc; everything else
#: takes the faction arc. Losing that distinction would make every ship's guns
#: identical in shape.
SPINAL_ARC = 30

#: Sweeps allowed for the band fit to settle. Convergence is monotone (each pass moves
#: values by less than the last), so this is a guard against a bug, not a tuning dial.
MAX_SWEEPS = 12

#: Never cycle a beam faster than this. Below about a second the engine's fixed 0.75 s
#: on-screen pulse stops keeping up and the beam reads as solid.
MIN_CYCLE = 0.9

#: Magazines are ABSOLUTE in balance_targets.json, never scaled here. They were scaled
#: at first and that made the whole tool non-idempotent - a second run took the Galaxy
#: from 40 photons to 16 to 4. Everything else is set absolutely and survives re-running;
#: magazines now do too. Sized so a photon is worth what a stock Homing is worth: 50
#: damage against a 280 facing is 18%, matching a 35-damage Homing against a
#: tsn_battleship's 200.


def _fit_to_band(values, lo, hi, floor=None):
    """(factor, clamp) that lands `values` inside [lo, hi], proportions intact.

    Slides the whole set with ONE factor so a ship's fast guns stay fast relative to
    its slow ones, then clamps whatever still falls outside. A battery whose spread is
    wider than the band cannot keep its full ratio - the clamp is what gives way, and
    it is applied to the SLOW end so pulse weapons survive.

    THE CLAMP IS ALSO WHAT MAKES THE TOOL IDEMPOTENT, which is not a detail. The first
    version slid the min up when the set sat low and the max down when it sat high, so
    a battery wider than its band oscillated: run 1 pushed the Damar to 11.08 s, run 2
    pulled it to 8.0, run 3 back again. Caught by md5-ing the output across two runs,
    not by reading.
    """
    if not values:
        return 1.0
    vmin, vmax = min(values), max(values)
    if vmax > hi and vmin >= lo:
        factor = hi / vmax          # whole battery too slow - bring the slowest to hi
    elif vmin < lo and vmax <= hi:
        factor = lo / vmin          # whole battery too fast - bring the fastest to lo
    else:
        # Either already inside the band, or spanning wider than it. Both are left
        # alone and handled by the clamp - and "already inside" MUST be a no-op, which
        # is what the second version of this got wrong: it tested `vmin > lo` and so
        # fired on every battery that already fitted, dragging all 51 hulls to the
        # floor of their band on the second run.
        factor = 1.0
    if floor is not None and vmin * factor < floor:
        factor = floor / vmin
    return factor


def retune(entry, target, bands, factions, rear_ratio, canon, log):
    key = entry["key"]
    cls = target["class"]
    band = bands[cls]
    faction = entry.get("origin") or entry.get("side")
    fac = factions.get(faction, {"arc": 120, "cycle_bias": 1.0})

    # ---- roles: strip, and write the weight class back in -------------------
    # Five hulls carried no class at all (both files split roles on "," with no
    # strip, so `tng_orn_brigand`'s " pirate" matched nothing either).
    roles = T.roles_of(entry)
    if cls not in roles and cls != "capital":
        roles.add(cls)
    if cls == "capital":
        roles.update({"leader", "warship", "heavy"})
    entry["roles"] = ",".join(sorted(roles))

    # ---- shields and hull ---------------------------------------------------
    front = target["front"]
    if cls == "station":
        entry["shields"] = [front]
    else:
        entry["shields"] = [front, int(round(front * rear_ratio[cls]))]
    entry["hullpoints"] = target["hull"]
    if target.get("turn"):
        entry["turn_rate"] = target["turn"]

    # ---- physical scale -----------------------------------------------------
    # meshscale is an ENGINE-INTERNAL render property with no data_set key, so it has
    # to be right in this file; there is no runtime fix-up for it.
    rec = canon["lengths"].get(key, {})
    ext = T.mesh_extent(entry)
    if rec.get("m") and ext:
        entry["meshscale"] = round((rec["m"] * canon["units_per_meter"]) / ext, 6)
    drawn = T.drawn_size(entry)
    if drawn:
        entry["exclusionradius"] = round(
            max(canon["exclusion_min"], drawn * canon["exclusion_ratio"]), 1)
    entry["radarscale"] = RADAR_BY_CLASS[cls]

    # ---- energy typo --------------------------------------------------------
    # Every other hull in the file is 0.55-1.3.
    if entry.get("warp_energy_cost", 0) > 10:
        log.append("%s: warp_energy_cost %s -> 1.31" % (key, entry["warp_energy_cost"]))
        entry["warp_energy_cost"] = 1.31

    # ---- beams --------------------------------------------------------------
    ports = T.beam_ports(entry)
    if ports:
        # Cycles first, because the damage solve below depends on them.
        cycles = [p.get("cycle_time") or 6.0 for p in ports]
        cyc_lo = band["cycle"][0] * fac["cycle_bias"]
        cyc_hi = band["cycle"][1] * fac["cycle_bias"]
        cf = _fit_to_band(cycles, cyc_lo, cyc_hi, floor=MIN_CYCLE)

        ranges = [p.get("range") or 1000 for p in ports]
        rf = _fit_to_band(ranges, band["range"][0], band["range"][1])

        for p in ports:
            p["cycle_time"] = round(
                min(cyc_hi, max(MIN_CYCLE, cyc_lo, (p.get("cycle_time") or 6.0) * cf)), 2)
            p["range"] = int(round(min(band["range"][1],
                                       max(band["range"][0], (p.get("range") or 1000) * rf))))
            arc = p.get("arcwidth", 360)
            if arc > SPINAL_ARC and arc < 360:
                p["arcwidth"] = fac["arc"]

        # Damage last: it is solved AGAINST the cycles just set, so the gun target is
        # hit exactly whatever the cycle scaling did.
        now = sum((p.get("damage_coeff") or 0.0) / (p.get("cycle_time") or 1.0) for p in ports)
        want = target["guns"]
        if want <= 0:
            for p in ports:
                p["damage_coeff"] = 0.0
        elif now > 0:
            df = want / now
            for p in ports:
                p["damage_coeff"] = round((p.get("damage_coeff") or 0.0) * df, 3)

    # ---- tubes and ordnance -------------------------------------------------
    # Five of the seven factions carried tubecount 0 on every hull, so a mission could
    # not seat a crew in a Romulan or Cardassian ship and have them launch anything.
    # This only ever matters for a PLAYER hull - NPCs never fire torpedoes - so it
    # opens a door rather than changing any fight the player did not choose.
    # Drones are the NPC-facing projectile - the presence of the field is the flag,
    # so removing it disarms a hull entirely and setting it arms one.
    if target.get("drone"):
        entry["drone_launch_timer"] = target["drone"]
    elif "drone_launch_timer" in entry:
        del entry["drone_launch_timer"]

    if target.get("tubes"):
        entry["tubecount"] = target["tubes"]
        if target.get("torps"):
            # MERGE, never replace. An entry is meant to be the CURRENT game entry plus
            # the author's deltas, and the stock six types (Homing, Nuke, EMP, Mine,
            # PShock, Tag) travel in `torpedostart` as zero-count slots. Overwriting the
            # list dropped all of them - TNG_TestRange caught it with "torpedo types kept
            # current: got ['Homing']". The counts here win for the types they name; every
            # other slot keeps whatever it had.
            slots = entry.get("torpedostart") or []
            existing = {k for slot in slots if isinstance(slot, dict) for k in slot}
            for slot in slots:
                if not isinstance(slot, dict):
                    continue
                for name in list(slot):
                    if name in target["torps"]:
                        slot[name] = target["torps"][name]
            for name, count in target["torps"].items():
                if name not in existing:
                    slots.append({name: count})
            entry["torpedostart"] = slots



def _size_by_class(entries, targets, canon, log):
    """Size the hulls that have no canonical length, from the ones that do.

    Seven ships are original or STO designs with nothing to measure against, and left
    alone they keep whatever the pack shipped - which is how the Orion Interceptor
    ended up a 60-unit "fighter" parked beside a 12-unit Peregrine. Each takes the
    MEDIAN drawn size of the canonical members of its own class.

    Median, not mean: the D'Deridex is 1042 m and would drag every heavy up on its own.

    Stations are skipped. Half of them are by_class, three ship no mesh at all, and
    their real sizes span a Spacedock to a docking ring - there is no useful median.
    """
    by_class = collections.defaultdict(list)
    for e in entries:
        cls = targets["ships"][e["key"]]["class"]
        if canon["lengths"].get(e["key"], {}).get("m"):
            drawn = T.drawn_size(e)
            if drawn:
                by_class[cls].append(drawn)

    for e in entries:
        key = e["key"]
        cls = targets["ships"][key]["class"]
        if cls == "station" or canon["lengths"].get(key, {}).get("m"):
            continue
        peers = sorted(by_class.get(cls) or [])
        ext = T.mesh_extent(e)
        if not peers or not ext:
            continue
        want = peers[len(peers) // 2]
        was = T.drawn_size(e)
        e["meshscale"] = round(want / ext, 6)
        e["exclusionradius"] = round(
            max(canon["exclusion_min"], want * canon["exclusion_ratio"]), 1)
        log.append("%s: no canonical length; sized to the %s median, %.0f -> %.0f u"
                   % (key, cls, was or 0, want))


def main(argv):
    dry = "--dry-run" in argv
    data = T.load_json(T.SHIPS)
    targets = T.load_json(T.TARGETS)
    canon = T.load_json(T.CANON)
    log = []

    before = {}
    for e in data["#ship-list"]:
        before[e["key"]] = (T.front_shield(e), e.get("hullpoints"), T.coef_sum(e), T.drawn_size(e))

    missing = [e["key"] for e in data["#ship-list"] if e["key"] not in targets["ships"]]
    if missing:
        print("ABORT - no target for: %s" % ", ".join(missing))
        return 1

    # ITERATE TO THE FIXED POINT rather than passing once. The band fit slides a
    # battery with one factor and clamps whatever still falls outside, so the clamped
    # set has a slightly different spread than the one that was measured, and the next
    # pass moves it again by a little less. Left at one pass, the tool produced output
    # that a SECOND run would still change - a trap for anyone regenerating the pack,
    # and the reason the Galaxy's magazine once went 40 -> 16 -> 4 unnoticed. Looping
    # until the serialization stops changing makes "run it again" provably free, which
    # the verification asserts by byte-comparison.
    last = None
    for sweep in range(MAX_SWEEPS):
        for e in data["#ship-list"]:
            retune(e, targets["ships"][e["key"]], targets["bands"], targets["factions"],
                   targets["rear_ratio"], canon, log)
        _size_by_class(data["#ship-list"], targets, canon, log)
        now = json.dumps(data, sort_keys=True)
        if now == last:
            break
        last = now
    else:
        print("WARNING: did not converge in %d sweeps - the output is not stable"
              % MAX_SWEEPS)
    seen = set()
    log[:] = [x for x in log if not (x in seen or seen.add(x))]

    print("%-24s%9s%9s%9s%9s%9s%9s" % ("hull", "shld", "->", "guns", "->", "drawn", "->"))
    for e in data["#ship-list"]:
        k = e["key"]
        b = before[k]
        a = (T.front_shield(e), e.get("hullpoints"), T.coef_sum(e), T.drawn_size(e))
        print("%-24s%9s%9s%9s%9s%9s%9s" % (
            k, b[0], a[0], "%.2f" % b[2], "%.2f" % a[2],
            "%.0f" % b[3] if b[3] else "-", "%.0f" % a[3] if a[3] else "-"))
    for line in log:
        print("  fix: %s" % line)

    if dry:
        print("\n--dry-run: nothing written")
        return 0

    # A ship-data file MUST end with a newline. The engine's reader is line-oriented
    # and without one it never consumes the last line, failing on valid JSON with
    # "End of input while parsing an object". One byte; it cost a whole session once.
    with open(T.SHIPS, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    print("\nwrote %s" % T.SHIPS)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
