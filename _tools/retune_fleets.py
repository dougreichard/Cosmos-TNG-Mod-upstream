"""Re-compose every faction's raiding ladder onto one shared difficulty curve.

    python _tools/retune_fleets.py --dry-run
    python _tools/retune_fleets.py

THE PROBLEM. Each faction has eleven difficulty tiers with five wave variants each,
and every ladder was written by hand against its own roster. So "difficulty 0" meant
two Kazon fighters or a Breen heavy cruiser depending on who rolled - a 51x spread
before the ship retune, still 5.2x after it - and four factions actually got WEAKER
from tier 3 to tier 4, because the ladder traded several small hulls for one bigger
one that was not proportionally stronger.

THE FIX. One monotone power curve. Every faction composes waves from its own roster
to hit the same number at the same tier, within tolerance.

CHARACTER SURVIVES, AND IT MOVES INTO THE SHAPE. Faction identity is expressed as
HOW a faction reaches a given strength, never as how strong it is: the Kazon send
many cheap hulls, the Breen send one heavy loner, the Romulans send fewer better
ships. `shape` below is what picks between equally-strong compositions.

THE BREEN BORROW. The Breen own exactly one hull in the mod, so their ladder could
only ever vary by count - and a tier-0 Breen wave would need a fraction of a Chel
Grett. tng_manifest.json already declares `"serves": {"Breen": "Dominion"}`, so the
low tiers draw Jem'Hadar hulls and the Chel Grett arrives later. That is also the
history: the Breen entered the war late.
"""
import os
import sys
import itertools
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tng_data as T                                            # noqa: E402

try:
    import yaml
except ImportError:                                             # pragma: no cover
    sys.path.insert(0, os.path.join(os.path.dirname(T.ROOT), "sbs_utils"))
    from sbs_utils import yaml

#: Must match balance_report.GUN_WEIGHT or the generator and the checker disagree.
GUN_WEIGHT = 250.0

TIERS = 11
VARIANTS = 5
BASE_POWER = 340.0          #: tier 0 - one light hull, for the faction whose light hull costs most
TOP_MULTIPLE = 10.6         #: tier 10 is this many times tier 0
MAX_SHIPS = 8

#: A wave cannot be composed more finely than the faction's CHEAPEST hull, so at low
#: tiers no amount of care will hit a target exactly - a Romulan tier 1 wants 430 and
#: the T'Varo costs 341, so the choices are 341 or 683 and nothing between. Demanding
#: a flat 15% there would be demanding something the roster cannot express. The
#: tolerance is therefore the larger of 15% and half the cheapest hull, which is the
#: real resolution limit. balance_report applies the same rule, from the same numbers.
BASE_TOLERANCE = 0.15


def tier_tolerance(cheapest, target):
    return max(BASE_TOLERANCE, (cheapest / 2.0) / target)

#: Which hulls each faction may field, and how it likes to spend a wave's budget.
#: "swarm"  - prefer more, cheaper hulls
#: "mixed"  - no preference; take the closest fit
#: "elite"  - prefer fewer, better hulls
ROSTERS = {
    "Klingon":    (["tng_klg_brel", "tng_klg_ktinga", "tng_klg_vorcha", "tng_klg_neghvar"], "mixed"),
    "Romulan":    (["tng_rmn_tvaro", "tng_rmn_mogai", "tng_rmn_dderidex", "tng_rmn_scimitar"], "elite"),
    "Cardassian": (["tng_crd_heideki", "tng_crd_galor", "tng_crd_keldon", "tng_crd_damar"], "mixed"),
    "Kazon":      (["tng_kaz_fighter", "tng_kaz_raider", "tng_kaz_cruiser", "tng_kaz_carrier"], "swarm"),
    "Orion":      (["tng_orn_interceptor", "tng_orn_corvette", "tng_orn_brigand", "tng_orn_corsair"], "swarm"),
    "Dominion":   (["tng_jem_attack_ship", "tng_jem_battlecruiser"], "elite"),
    # Serves the Dominion - see the module docstring.
    "Breen":      (["tng_jem_attack_ship", "tng_brn_chel_grett", "tng_jem_battlecruiser"], "elite"),
}

FILES = {
    "Klingon": "tng_klingon_fleets.yaml", "Romulan": "tng_romulan_fleets.yaml",
    "Cardassian": "tng_cardassian_fleets.yaml", "Kazon": "tng_kazon_fleets.yaml",
    "Orion": "tng_orion_fleets.yaml", "Dominion": "tng_dominion_fleets.yaml",
    "Breen": "tng_breen_fleets.yaml",
}


def hull_power(entry):
    return sum(entry.get("shields") or [0]) + T.coef_sum(entry) * GUN_WEIGHT


def curve(tier):
    return BASE_POWER * (TOP_MULTIPLE ** (tier / float(TIERS - 1)))


def compose(roster, powers, target, shape, tol):
    """Up to VARIANTS wave compositions that each land near `target`.

    Enumerates every multiset up to MAX_SHIPS ships, keeps the ones within `tol` of
    target, then picks across them by ship COUNT so a tier offers a real spread of
    wave shapes rather than five copies of one answer.
    """
    cands = []
    for n in range(1, MAX_SHIPS + 1):
        for combo in itertools.combinations_with_replacement(roster, n):
            p = sum(powers[k] for k in combo)
            err = abs(p - target) / target
            if err <= tol:
                cands.append((err, n, list(combo)))
    if not cands:
        # Nothing in tolerance - fall back to the single closest composition so a
        # tier is never empty. The checker will flag it rather than it passing quietly.
        best = min(
            ((abs(sum(powers[k] for k in c) - target) / target, len(c), list(c))
             for n in range(1, MAX_SHIPS + 1)
             for c in itertools.combinations_with_replacement(roster, n)),
            key=lambda t: t[0])
        return [best[2]] * VARIANTS

    # Order by the faction's taste first, accuracy second.
    if shape == "swarm":
        cands.sort(key=lambda c: (-c[1], c[0]))
    elif shape == "elite":
        cands.sort(key=lambda c: (c[1], c[0]))
    else:
        cands.sort(key=lambda c: (c[0], c[1]))

    out = []
    seen = set()
    for _, _, combo in cands:
        sig = tuple(sorted(combo))
        if sig in seen:
            continue
        seen.add(sig)
        out.append(combo)
        if len(out) == VARIANTS:
            break
    while len(out) < VARIANTS:
        out.append(list(out[-1]))
    return out


HEADER = """# {race} raiding fleets, by difficulty.
#
# GENERATED by _tools/retune_fleets.py - edit that, not this. The curve is shared by
# every faction, so difficulty N is the same fight whoever shows up; what differs is
# the SHAPE of the wave, which is where faction character lives.
#
# Eleven tiers, five variants each; a variant is the ship keys making up one fleet.
# Loaded when this faction is in the NPC_RACES setting.
race: {race}
fleets:
"""


def main(argv):
    dry = "--dry-run" in argv
    index = {e["key"]: e for e in T.ships()}
    powers = {k: hull_power(v) for k, v in index.items()}

    print("target curve: " + "  ".join("%d:%.0f" % (t, curve(t)) for t in range(TIERS)))
    print()
    print("%-13s%s" % ("faction", "".join("%8d" % i for i in range(TIERS))))

    written = []
    for race, (roster, shape) in sorted(ROSTERS.items()):
        missing = [k for k in roster if k not in powers]
        if missing:
            print("ABORT - %s roster names unknown hulls: %s" % (race, missing))
            return 1
        tiers = []
        means = []
        for t in range(TIERS):
            cheapest = min(powers[k] for k in roster)
            variants = compose(roster, powers, curve(t), shape,
                               tier_tolerance(cheapest, curve(t)))
            tiers.append(variants)
            means.append(sum(sum(powers[k] for k in v) for v in variants) / len(variants))
        print("%-13s%s" % (race, "".join("%8.0f" % m for m in means)))

        lines = [HEADER.format(race=race)]
        for t, variants in enumerate(tiers):
            lines.append("  # difficulty %d\n  -\n" % t)
            for v in variants:
                lines.append("    - [%s]\n" % ", ".join(v))
        written.append((os.path.join(T.ROOT, "tng_races", FILES[race]), "".join(lines)))

    if dry:
        print("\n--dry-run: nothing written")
        return 0
    for path, text in written:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    print("\nwrote %d ladders" % len(written))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
