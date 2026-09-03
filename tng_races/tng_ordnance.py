"""Which Federation hulls carry the special ordnance.

Held in Python rather than written into the .mast route so the answer is a LIST in one
place, greppable and testable, rather than a chain of string comparisons in a spawn
route. Prefixed `tng_` because every top-level function here becomes a MAST global in one
flat, mission-wide namespace and the last one loaded wins, silently.
"""

#: Quantum torpedoes were late-era and never general issue. These are the hulls that
#: plausibly carried them - the Sovereign, the Defiant and the Galaxy refit. On the SIDE
#: they would have been standard issue on a Constellation, which is the wrong century.
_QUANTUM_HULLS = (
    "tng_fed_sovereign",
    "tng_fed_defiant",
    "tng_fed_galaxy_x",
)

#: A tricobalt device is not standard Federation ordnance at all - it is what a ship
#: seventy thousand light years from home uses when it has run out of better ideas.
_TRICOBALT_HULL = "tng_fed_intrepid"


def tng_quantum_hulls():
    return list(_QUANTUM_HULLS)


def tng_tricobalt_hull():
    return _TRICOBALT_HULL


def tng_hull_of(obj):
    """The shipData key a spawned object came from, or "" when it has none.

    NOT `data_tag`. That is what a first version read, and it answers None for a player
    ship - so the quantum and tricobalt gates below matched nothing and the two special
    rounds were granted to no one, silently, while everything still reported PASS.

    The attribute is not in one place either: `ship_key`, `key` and `art_id` are all used
    depending on how the object was made, with the blob as a last resort. Gamma with a Q
    worked this out for its hull audit; this is the same walk, in the mod that owns the
    hulls.
    """
    for attr in ("ship_key", "key", "art_id"):
        val = getattr(obj, attr, None)
        if val:
            return str(val)
    data = getattr(obj, "data_set", None)
    if data is not None:
        try:
            return str(data.get("ship_key", 0, "") or "")
        except Exception:                               # noqa: BLE001
            return ""
    return ""


def tng_torp_grant(ship_id):
    """Give a player ship whatever special ordnance its HULL earns.

    Called from two places on purpose - at spawn, and again on `ship_hull_changed`.

    A SPAWN-TIME CHECK ALONE IS WRONG for any mission that re-hulls. Gamma with a Q seats
    every crew in a story ship minutes after spawn, so a crew that ends up in a Defiant
    spawned as an Excelsior: the spawn route saw the roster's hull, matched nothing, and
    the quantum rounds went to nobody. Measured by printing the loadout and finding the
    hull was still the one the crew started in.

    Idempotent. `torpedo_make_available` is what LegendaryMissions' own grant loop calls,
    and re-granting a type a ship already has is a no-op with the capacity unchanged.
    """
    from sbs_utils.procedural.query import to_object
    from sbs_utils.procedural.roles import add_role, has_role
    from sbs_utils.procedural.torpedoes import torpedo_make_available

    ship = to_object(ship_id)
    if ship is None or not has_role(ship_id, "__player__"):
        return ""
    hull = tng_hull_of(ship)
    if not hull:
        return ""
    granted = []
    if hull in _QUANTUM_HULLS:
        add_role(ship_id, "quantum_armed")
        torpedo_make_available(ship_id, "Quantum", 4)
        granted.append("Quantum")
    if hull == _TRICOBALT_HULL:
        add_role(ship_id, "tricobalt_armed")
        torpedo_make_available(ship_id, "Tricobalt", 2)
        granted.append("Tricobalt")
    return ",".join(granted)


def tng_has_label(name):
    """True when some loaded add-on defines a top-level MAST label of this name.

    WHY THIS EXISTS. The three torpedo types below are declared by this mod but
    REGISTERED by LegendaryMissions: each one ends in `jump prefab_torpedo_type`, and
    that label lives in LM's prefabs/torpedo_prefabs.mast. A jump to a label nothing
    defines is not a compile error - it compiles clean and only fails if it ever runs -
    so the mod's own viewer, which loads sbs_utils and this add-on and nothing else,
    reported three runtime errors and a FAIL verdict on every headless run.

    This is the runtime half of an OPTIONAL dependency. A hard `requires` would be
    wrong here: it would take every mission that loads tng_races without LM straight to
    zero labels, which is the failure mode LM's own hangar add-on caused across 22
    missions. Asking whether the label is there is cheaper and degrades to "no custom
    torpedoes" instead of "no mission".

    Labels live in the story's own table keyed by name, which is what makes this a
    dict lookup rather than a guess.
    """
    from sbs_utils.helpers import FrameContext

    page = FrameContext.page
    story = getattr(page, "story", None) if page is not None else None
    if story is None:
        story = FrameContext.mast
    labels = getattr(story, "labels", None)
    if not labels:
        return False
    return name in labels
