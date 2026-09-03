"""What a TNG station stocks and how fast it builds it.

TNG SHIPS LIVE ON TORPEDOES. A Defiant carries Photon 10 and Quantum 4 and little else -
where a stock Artemis hull treats torpedoes as one option beside beams, a Trek ship treats
them as the weapon. That changes what a station has to be: rearming is not a top-up
between fights, it is the reason to go back.

Two things were wrong for that, both measured on a live DS9 (2026-09-03) rather than read:

* **A TNG station advertised all TEN torpedo types.** `torpedo_types_available` came back
  as `Homing,Photon,Nuke,Quantum,EMP,Tricobalt,Mine,PShock,Tag,Beacon` - every stock
  LegendaryMissions round plus its three specials, none of which any TNG hull can carry.
  That is not cosmetic: a station builds ONE type at a time
  (`docking_build_munition_queue_task` cancels the running build when the type changes),
  so a crew picks their round out of a ten-item menu, seven entries of which are dead.
* **It built at the `default:` rate, 3 minutes a Photon.** TNG station art
  (`tng_fed_ds9`, `tng_fed_comms_base`) contains none of the stock class words the build
  table matches on - "command", "industry", "civil", "science" - so every TNG station
  falls to `default` whatever it is meant to be. Ten Photons is thirty minutes, and a
  sitting is twenty-five.

WHY THIS IS A MOD FILE AND NOT A LIBRARY CHANGE. The playtest asked for this with a
condition attached - "don't break the base game doing this, suggest options if needed" -
and the base game's rates are right for the base game. Nothing here touches them: it
reshapes stations on the MOD'S OWN sides, leaving a TSN starbase in a stock mission
exactly as it was. Both dials are settings, so a mission can tune them without editing
the mod.

EVERY PUBLIC NAME IS PREFIXED `tng_`. A mastlib's .py files are exec'd into one shared
namespace and every function becomes a MAST global.
"""
from sbs_utils.procedural.execution import get_shared_variable
from sbs_utils.procedural.inventory import get_inventory_value, set_inventory_value
from sbs_utils.procedural.query import (get_data_set_value, set_data_set_value,
                                        to_object)

from tng_setup import FACTIONS

#: What a TNG station stocks, in engine order. Not "everything the story registered":
#: these are the rounds TNG hulls actually carry.
_DEFAULT_TYPES = "Photon,Quantum,Tricobalt"

#: Divides each type's declared build time. 3 turns a 3-minute Photon into 1 minute and a
#: 12-minute Tricobalt into 4, so the RELATIVE cost survives - a Tricobalt is still four
#: Photons' worth of yard time - while a crew can rearm inside a sitting.
_DEFAULT_SPEEDUP = 3.0

#: How much production a station is assumed to have banked before the crew arrives, in
#: minutes. Seeding from this rather than from a flat number scales with the type: at the
#: default rates it is 10 Photons, 5 Quantum, 2 Tricobalt.
_DEFAULT_HEADSTART = 10.0


def _setting(key, default):
    value = get_shared_variable(key, None)
    return default if value is None or value == "" else value


def tng_station_torp_types():
    """The types a TNG station stocks, as a list. Setting: TNG_STATION_TORP_TYPES."""
    raw = _setting("TNG_STATION_TORP_TYPES", _DEFAULT_TYPES)
    if not isinstance(raw, str):
        raw = ",".join(str(x) for x in raw)
    return [t.strip() for t in raw.split(",") if t.strip()]


def tng_station_build_speedup():
    """Divisor on each type's build time. Setting: TNG_STATION_BUILD_SPEEDUP."""
    try:
        return max(0.1, float(_setting("TNG_STATION_BUILD_SPEEDUP", _DEFAULT_SPEEDUP)))
    except (TypeError, ValueError):
        return _DEFAULT_SPEEDUP


def tng_station_headstart_minutes():
    """Minutes of production a station starts with. Setting: TNG_STATION_TORP_HEADSTART."""
    try:
        return max(0.0, float(_setting("TNG_STATION_TORP_HEADSTART", _DEFAULT_HEADSTART)))
    except (TypeError, ValueError):
        return _DEFAULT_HEADSTART


def tng_is_mod_side(id_or_obj):
    """Whether this object flies for one of the mod's own factions.

    The gate that keeps this off the base game. A TSN starbase in a stock mission is not
    a TNG station however many TNG addons are loaded, and reshaping it would be exactly
    the "breaking the base game" the report asked us not to do.
    """
    so = to_object(id_or_obj)
    if so is None:
        return False
    side = str(getattr(so, "side", "") or "").strip().lower()
    return side in {f.lower() for f in FACTIONS}


def tng_station_setup_torpedoes(id_or_obj):
    """Restrict a TNG station to TNG rounds, speed them up, and give it a head start.

    Returns a short status string, or "" when the station is not ours.

    IDEMPOTENT, and it takes work to be. The obvious version divides
    `{key}_BUILD_SPEED` by the speedup - which reads the value it wrote LAST time, so a
    second pass gives a ninth of the build time and three times the stock. A `//spawn`
    route is not guaranteed to fire once (a re-spawn, a second route, a reloaded map),
    and compounding here would quietly turn a yard into a torpedo fountain. So the
    declared time is recorded once as `{key}_BUILD_BASE` and every pass derives from
    that.
    """
    so = to_object(id_or_obj)
    if so is None or not tng_is_mod_side(so):
        return ""

    wanted = tng_station_torp_types()
    if not wanted:
        return ""
    speedup = tng_station_build_speedup()
    headstart = tng_station_headstart_minutes()

    # Keep only the types this station should carry, in the order the setting names them -
    # which is also the order the comms menu and the ship-data widget will show.
    keep = []
    for key in wanted:
        # A type nothing registered cannot be built; listing it would put a dead row in
        # the menu, which is the fault being fixed rather than a new one.
        base = get_inventory_value(so, f"{key}_BUILD_BASE")
        if base is None:
            base = get_inventory_value(so, f"{key}_BUILD_SPEED")
            if base is None:
                continue
            set_inventory_value(so, f"{key}_BUILD_BASE", base)
        keep.append(key)
        minutes = max(0.1, float(base) / speedup)
        set_inventory_value(so, f"{key}_BUILD_SPEED", minutes)
        set_data_set_value(so, f"{key}_NUM", int(max(1, headstart // minutes)))

    if not keep:
        return ""

    # Drop the rest. The stock rounds are still REGISTERED - a stock hull in a mixed game
    # can still be given them - they are simply not something a TNG yard makes.
    for key in (get_inventory_value(so, "torpedo_production_keys") or []):
        if key not in keep:
            set_data_set_value(so, f"{key}_NUM", 0)

    set_inventory_value(so, "torpedo_production_keys", keep)
    set_data_set_value(so, "torpedo_types_available", ",".join(keep))
    return (f"tng station {so.name}: {','.join(keep)} at 1/{speedup:g} build time, "
            f"{headstart:g}min head start")
