"""Is every hull drawn at the size it should be, and is its collision bubble sane?

    python _tools/scale_report.py          # report, exit 1 on any failure
    python _tools/scale_report.py --quiet  # failures only

WHY THIS EXISTS. `meshscale` on its own is unreadable - each model was exported at
its own native scale, so the mod's meshscales span 0.01 to 0.84 for hulls whose
drawn sizes span 5 to 742 units. The only way to know how big a ship actually is
to measure the mesh and multiply. Nobody does that by eye, so it went unchecked and
the Kazon Carrier ended up drawn LARGER THAN A GALAXY for a ship a third the length.

The convention being checked was measured, not invented - see canon_lengths.json.

This is also the only check that can catch a mesh being re-exported or swapped at a
different native scale, because that changes the drawn size while `meshscale` in the
ship data stays exactly where it was.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tng_data as T                                            # noqa: E402


def main(argv):
    quiet = "--quiet" in argv
    canon = T.load_json(T.CANON)
    upm = canon["units_per_meter"]
    tol = canon["tolerance"]
    lengths = canon["lengths"]
    excl_target = canon["exclusion_ratio"]
    excl_min = canon["exclusion_min"]

    failures = []
    rows = []
    for entry in T.ships():
        key = entry["key"]
        drawn = T.drawn_size(entry)
        rec = lengths.get(key)
        if rec is None:
            failures.append((key, "not listed in canon_lengths.json"))
            continue
        canon_m = rec.get("m")
        excl = float(entry.get("exclusionradius") or 0.0)

        # --- scale ---
        ratio = None
        if canon_m and drawn:
            ratio = drawn / canon_m
            if not (tol["scale_lo"] <= ratio <= tol["scale_hi"]):
                failures.append((key, "drawn %.1f u for a %.0f m ship = %.3f u/m (%.2fx the %.3f convention); should draw %.1f"
                                 % (drawn, canon_m, ratio, ratio / upm, upm, canon_m * upm)))
        elif canon_m and not drawn:
            # A hull with a canonical length but no mesh cannot be checked. That is a
            # real gap rather than an exemption, so say so instead of passing silently.
            failures.append((key, "has a canonical length (%.0f m) but ships no .obj to measure" % canon_m))

        # --- collision bubble ---
        # Checked against the TARGET, not against the raw ratio, because of the floor.
        # Stock gives every cockpit-class hull a flat 25 no matter how small it is
        # (tsn_fighter, tsn_shuttle, tsn_bomber), so a bubble larger than the craft is
        # correct down there and a ratio test would fail all of them wrongly.
        er = (excl / drawn) if drawn else None
        if drawn:
            want = max(excl_min, drawn * excl_target)
            if abs(excl - want) > max(2.0, want * 0.12):
                direction = "ships will clip into the hull" if excl < want else "nothing can get near it"
                failures.append((key, "exclusionradius %.0f on a %.1f u hull - %s; want %.0f"
                                 % (excl, drawn, direction, want)))

        rows.append((key, rec.get("source", "?"), canon_m, drawn, ratio, excl, er))

    if not quiet:
        print("Scale convention: %.3f units per meter (1 unit = %.2f m)" % (upm, 1.0 / upm))
        print("exclusionradius target: %.2f of drawn length\n" % excl_target)
        hdr = "%-24s%-10s%>9s%>10s%>8s%>9s%>7s%>8s" .replace(">", "")
        print("%-24s%-10s%9s%10s%8s%9s%7s%8s"
              % ("hull", "source", "canon m", "drawn u", "u/m", "vs conv", "excl", "ratio"))
        for key, src, m, drawn, ratio, excl, er in sorted(rows, key=lambda r: -(r[4] or 0)):
            print("%-24s%-10s%9s%10s%8s%9s%7.0f%8s"
                  % (key, src,
                     "%.0f" % m if m else "-",
                     "%.1f" % drawn if drawn else "-",
                     "%.3f" % ratio if ratio else "-",
                     "%.2fx" % (ratio / upm) if ratio else "-",
                     excl,
                     "%.2f" % er if er else "-"))
        print()

    if failures:
        print("SCALE CHECK FAILED - %d problem(s):" % len(failures))
        for key, msg in failures:
            print("  %-24s %s" % (key, msg))
        return 1
    print("SCALE CHECK PASSED - %d hulls" % len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
