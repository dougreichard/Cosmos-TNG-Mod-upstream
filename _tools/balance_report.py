"""Does the ship roster still obey its own weight classes, and do the fleet ladders
mean the same thing for every faction?

    python _tools/balance_report.py          # full report, exit 1 on any failure
    python _tools/balance_report.py --quiet  # failures only

THE CONTRACT THIS ENFORCES:

  1. Every hull declares a weight class. Five did not, and an unclassed hull is
     invisible to every check below.
  2. SHIELD bands do not overlap. This is the one that makes a class mean anything.
     Before this check, `light` topped out at 2880 while `heavy` started at 1620 -
     the bands were nested, not adjacent, so a "light" Saber out-tanked a "heavy"
     Nebula and the class names carried no information at all.
  3. GUN bands may touch. Deliberately not an error: a glass-cannon medium
     out-shooting a tanky heavy is the point of having both, and it is how the
     Defiant is expressed.
  4. A SHIP's hullpoints is 1-9. It is a size tier, NOT hit points - only stations
     use the field as armor. The mod ran 12-25 on some hulls, which bought them
     nothing but an inflated system-node pool.
  5. Every fleet ladder rises monotonically, and at each tier the factions land on
     the same strength. Difficulty 3 has to be difficulty 3 whoever shows up. It
     used to span 51x at tier 0, and four factions got WEAKER from tier 3 to tier 4.
     The tolerance is +/-15% OR half the faction's cheapest hull, whichever is
     larger - at low tiers a wave genuinely cannot be composed more finely than
     that, and failing a ladder for it would be failing it for a reason no ladder
     can fix.
"""
import os
import sys
import glob
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tng_data as T                                            # noqa: E402

try:
    import yaml
except ImportError:                                             # pragma: no cover
    # The bundled copy. A bare `import yaml` finds PyYAML in site-packages on a dev
    # box and nowhere else, so the fallback is not optional.
    sys.path.insert(0, os.path.join(os.path.dirname(T.ROOT), "sbs_utils"))
    from sbs_utils import yaml

#: See retune_fleets.tier_tolerance - a wave cannot be composed more finely than the
#: faction's cheapest hull, so a flat percentage would fail the low tiers for a reason
#: no ladder can fix. Same rule, same numbers, so the checker and the generator cannot
#: disagree about what "balanced" means.
TIER_TOLERANCE = 0.15

#: Shared with the ladders: a wave's strength is its total shields plus its guns
#: weighted to the same order of magnitude. Guns are worth more per point than
#: shields because a wave that cannot hurt you is not a difficulty.
GUN_WEIGHT = 250.0


def fleet_power(entry_index, keys):
    shields = 0.0
    guns = 0.0
    for k in keys:
        e = entry_index.get(k)
        if e is None:
            return None
        shields += sum(e.get("shields") or [0])
        guns += T.coef_sum(e)
    return shields + guns * GUN_WEIGHT


def main(argv):
    quiet = "--quiet" in argv
    targets = T.load_json(T.TARGETS)
    bands = targets["bands"]
    entries = T.ships()
    index = {e["key"]: e for e in entries}
    failures = []

    # ---- 1 & 4: per-hull band membership ------------------------------------
    by_class = collections.defaultdict(list)
    for e in entries:
        key = e["key"]
        cls = T.weight_class(e)
        if cls is None:
            failures.append((key, "declares no weight class - its roles are %r" % e.get("roles")))
            continue
        band = bands.get(cls)
        front = T.front_shield(e)
        hp = e.get("hullpoints") or 0
        guns = T.coef_sum(e)
        by_class[cls].append((front, guns, hp, key))

        if not band["front"][0] <= front <= band["front"][1]:
            failures.append((key, "front shield %s outside the %s band %s" % (front, cls, band["front"])))
        if not band["guns"][0] - 0.005 <= guns <= band["guns"][1] + 0.005:
            failures.append((key, "guns %.2f outside the %s band %s" % (guns, cls, band["guns"])))
        if not band["hull"][0] <= hp <= band["hull"][1]:
            failures.append((key, "hullpoints %s outside the %s band %s" % (hp, cls, band["hull"])))
        if cls != "station" and not 1 <= hp <= 9:
            failures.append((key, "hullpoints %s - for a SHIP this is a 1-9 size tier, not hit points" % hp))

    # ---- 2: shield bands must be adjacent, not nested ------------------------
    ladder = ["fighter", "light", "medium", "heavy", "capital"]
    for lo_cls, hi_cls in zip(ladder, ladder[1:]):
        lo = [r for r in by_class.get(lo_cls, [])]
        hi = [r for r in by_class.get(hi_cls, [])]
        if not lo or not hi:
            continue
        lo_top = max(r[0] for r in lo)
        hi_bot = min(r[0] for r in hi)
        if lo_top >= hi_bot:
            top_key = max(lo, key=lambda r: r[0])[3]
            bot_key = min(hi, key=lambda r: r[0])[3]
            failures.append(("%s/%s" % (lo_cls, hi_cls),
                             "bands overlap: %s (%s) at %s is not below %s (%s) at %s"
                             % (top_key, lo_cls, lo_top, bot_key, hi_cls, hi_bot)))

    if not quiet:
        print("=== Weight classes ===")
        print("%-10s%4s%14s%16s%10s" % ("class", "n", "shields", "guns", "hull"))
        for cls in ladder + ["civilian", "shuttle", "station"]:
            rows = by_class.get(cls)
            if not rows:
                continue
            print("%-10s%4d%14s%16s%10s" % (
                cls, len(rows),
                "%d - %d" % (min(r[0] for r in rows), max(r[0] for r in rows)),
                "%.2f - %.2f" % (min(r[1] for r in rows), max(r[1] for r in rows)),
                "%d - %d" % (min(r[2] for r in rows), max(r[2] for r in rows))))
        print()

    # ---- 5: fleet ladders ----------------------------------------------------
    ladders = {}
    cheapest_hull = {}
    for path in sorted(glob.glob(os.path.join(T.ROOT, "tng_races", "*_fleets.yaml"))):
        with open(path, "r", encoding="utf-8") as f:
            doc = yaml.safe_load(f)
        race = doc["race"]
        tiers = []
        for tier in doc["fleets"]:
            powers = [fleet_power(index, variant) for variant in tier]
            if any(p is None for p in powers):
                failures.append((race, "a fleet variant names a hull that does not exist"))
                powers = [p for p in powers if p is not None]
            tiers.append(sum(powers) / len(powers) if powers else 0.0)
        ladders[race] = tiers
        cheapest_hull[race] = min(
            (p for p in (fleet_power(index, [k])
                         for tier in doc["fleets"] for v in tier for k in v)
             if p), default=0.0)

    depth = max((len(v) for v in ladders.values()), default=0)
    for race, tiers in sorted(ladders.items()):
        for i in range(1, len(tiers)):
            if tiers[i] < tiers[i - 1]:
                failures.append((race, "tier %d is WEAKER than tier %d (%.0f < %.0f)"
                                 % (i, i - 1, tiers[i], tiers[i - 1])))

    for i in range(depth):
        col = [(r, v[i]) for r, v in ladders.items() if i < len(v)]
        if len(col) < 2:
            continue
        vals = [v for _, v in col]
        mid = sum(vals) / len(vals)
        if mid <= 0:
            continue
        worst = max(col, key=lambda rv: abs(rv[1] - mid) / mid)
        spread = (max(vals) / min(vals)) if min(vals) > 0 else float("inf")
        # Granularity floor: half the coarsest faction's cheapest hull.
        grain = max((cheapest_hull.get(r, 0.0) for r, _ in col), default=0.0) / 2.0
        tol = max(TIER_TOLERANCE, grain / mid)
        if abs(worst[1] - mid) / mid > tol:
            failures.append(("tier %d" % i,
                             "factions span %.1fx (%.0f to %.0f); %s is the outlier at %.0f vs a %.0f mean"
                             % (spread, min(vals), max(vals), worst[0], worst[1], mid)))

    if not quiet and ladders:
        print("=== Fleet ladders (average wave strength per tier) ===")
        print("%-13s%s" % ("faction", "".join("%8d" % i for i in range(depth))))
        for race, tiers in sorted(ladders.items()):
            print("%-13s%s" % (race, "".join("%8.0f" % t for t in tiers)))
        print("%-13s%s" % ("spread", "".join(
            "%7.1fx" % ((max(c) / min(c)) if min(c) > 0 else 0)
            for c in ([v[i] for v in ladders.values() if i < len(v)] for i in range(depth)))))
        print()

    if failures:
        print("BALANCE CHECK FAILED - %d problem(s):" % len(failures))
        for who, msg in failures:
            print("  %-24s %s" % (who, msg))
        return 1
    print("BALANCE CHECK PASSED - %d hulls, %d fleet ladders" % (len(entries), len(ladders)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
