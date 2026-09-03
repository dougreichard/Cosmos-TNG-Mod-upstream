"""Do fights actually resolve in a reasonable time?

    python _tools/duel_report.py          # report, exit 1 on failure
    python _tools/duel_report.py --quiet

THE TARGET IS NOT INVENTED. `sbs_utils/mkdocs/docs/api/engine/events.md` records the
stock game's own calibration band, measured against the engine: "duels resolve in
15-110 s; a starbase is >2x tankier than a cruiser". Holding the mod to the base
game's number is the whole point of the rebalance, so it is the number used here.

WHY IT IS SCORED BY CLASS GAP. A flat "every pairing must land in 15-110 s" would be
the wrong test - it would demand that a Peregrine trade evenly with a Scimitar, which
is precisely what weight classes exist to prevent. So the band is enforced on PEER
duels (same class, or one class apart) and merely reported for the rest. A three-class
mismatch being decisive in both directions is the system working.

Before the rebalance the sampled duels ran 47-346 s, and a Galor needed nearly six
minutes to threaten a Galaxy.

WHAT THIS IS NOT. A closed-form estimate: front facing, beams only, no shield regen,
no torpedoes, no manoeuvring, both ships pointed at each other. It catches gross
mis-calibration, which is what it is for. It is not a substitute for playing the game,
and it cannot see anything about how a fight FEELS.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tng_data as T                                            # noqa: E402

#: LegendaryMissions sets these in consoles/server_console.mast: players 7.0, NPCs
#: DIFFICULTY/2+3, which is 5.5 at the default DIFFICULTY 5. Per-shot damage is this
#: base x the beam's damage_coeff, so a hull's coef_sum x base is its DPS.
PLAYER_BASE = 7.0
NPC_BASE = 5.5

TTK_LO, TTK_HI = 15.0, 110.0
PEER_GAP = 1
PEER_PASS_RATE = 0.95
STARBASE_TANK_MULTIPLE = 2.0

ORDER = ["fighter", "shuttle", "light", "medium", "heavy", "capital"]


def rank(entry):
    cls = T.weight_class(entry)
    # fighter and shuttle are the same tier - a shuttle is not a class below a fighter.
    if cls == "shuttle":
        cls = "fighter"
    return ORDER.index(cls) if cls in ORDER else None


def main(argv):
    quiet = "--quiet" in argv
    ships = T.ships()
    index = {e["key"]: e for e in ships}
    armed = [e for e in ships if rank(e) is not None and T.coef_sum(e) > 0]

    buckets = {}
    for a in armed:
        dps = T.coef_sum(a) * NPC_BASE
        for b in armed:
            if a["key"] == b["key"]:
                continue
            gap = abs(rank(a) - rank(b))
            buckets.setdefault(gap, []).append(T.front_shield(b) / dps)

    failures = []
    peer = [t for gap, ts in buckets.items() if gap <= PEER_GAP for t in ts]
    if peer:
        ok = sum(1 for t in peer if TTK_LO <= t <= TTK_HI)
        rate = ok / float(len(peer))
        if rate < PEER_PASS_RATE:
            failures.append("only %.0f%% of peer duels resolve in %g-%g s (want >= %.0f%%)"
                            % (rate * 100, TTK_LO, TTK_HI, PEER_PASS_RATE * 100))

    # "a starbase is >2x tankier than a cruiser" - the second half of the same target.
    cruisers = [T.front_shield(e) for e in ships if T.weight_class(e) == "heavy"]
    bases = [T.front_shield(e) for e in ships
             if T.weight_class(e) == "station" and T.coef_sum(e) > 0]
    if cruisers and bases:
        mult = (sum(bases) / len(bases)) / (sum(cruisers) / len(cruisers))
        if mult < STARBASE_TANK_MULTIPLE:
            failures.append("an armed starbase is only %.1fx a cruiser (want > %.1fx)"
                            % (mult, STARBASE_TANK_MULTIPLE))

    if not quiet:
        print("Time-to-kill: front facing, beams only, no regen. NPC beam base %.1f."
              % NPC_BASE)
        print("Engine's own stock band: %g-%g s.\n" % (TTK_LO, TTK_HI))
        print("%-10s%7s%8s%9s%8s%13s" % ("class gap", "n", "min", "median", "max", "in band"))
        for gap in sorted(buckets):
            v = sorted(buckets[gap])
            ok = sum(1 for t in v if TTK_LO <= t <= TTK_HI)
            label = str(gap) + ("  (peer)" if gap <= PEER_GAP else "")
            print("%-10s%7d%8.0f%9.0f%8.0f%12.0f%%"
                  % (label, len(v), v[0], v[len(v) // 2], v[-1], 100.0 * ok / len(v)))
        print("\nA large class gap SHOULD be decisive in both directions - that is what a")
        print("weight class is for - so the band is only enforced on peer duels.")
        if cruisers and bases:
            print("\narmed starbase / heavy cruiser tankiness: %.1fx" % mult)
        print()

    if failures:
        print("DUEL CHECK FAILED:")
        for f in failures:
            print("  %s" % f)
        return 1
    print("DUEL CHECK PASSED - %d peer duels, %.0f%% in band"
          % (len(peer), 100.0 * sum(1 for t in peer if TTK_LO <= t <= TTK_HI) / len(peer)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
