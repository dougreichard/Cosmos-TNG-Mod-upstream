"""A TNG yard stocks TNG rounds, fast - and leaves a stock station alone.

Measured on a live DS9 before this existed: `torpedo_types_available` came back as
`Homing,Photon,Nuke,Quantum,EMP,Tricobalt,Mine,PShock,Tag,Beacon` and Photon built at the
3-minute `default` rate, because TNG station art contains none of the stock class words
the build table matches on. Ten Photons is thirty minutes and a sitting is twenty-five.

The base-game guard is the test that matters most here. The playtest asked for this with
a condition - "don't break the base game doing this" - so a station that is not on one of
the mod's sides must come out of this untouched, byte for byte.
"""
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from sbs_utils.fs import test_set_exe_dir  # noqa: E402

test_set_exe_dir()

from cosmos_dev.mock import sbs as mock_sbs  # noqa: E402,F401
from sbs_utils.helpers import Context, FakeEvent, FrameContext  # noqa: E402
from sbs_utils.procedural.execution import set_shared_variable  # noqa: E402
from sbs_utils.procedural.inventory import get_inventory_value, set_inventory_value  # noqa: E402
from sbs_utils.procedural.query import get_data_set_value, set_data_set_value  # noqa: E402
from sbs_utils.procedural.spawn import npc_spawn  # noqa: E402
from sbs_utils.spaceobject import SpaceObject  # noqa: E402

import tng_stations as T  # noqa: E402

#: What LegendaryMissions leaves on a station: its own four rounds, its three specials,
#: and the mod's three. The shape the live probe found.
_ALL = ["Homing", "Photon", "Nuke", "Quantum", "EMP", "Tricobalt", "Mine",
        "PShock", "Tag", "Beacon"]
_BUILD = {"Homing": 3, "Photon": 3, "Nuke": 5, "Quantum": 6, "EMP": 4,
          "Tricobalt": 12, "Mine": 4, "PShock": 6, "Tag": 6, "Beacon": 6}


class StationTest(unittest.TestCase):
    def setUp(self):
        mock_sbs.create_new_sim()
        SpaceObject.clear()
        FrameContext.context = Context(mock_sbs.sim, mock_sbs, FakeEvent())
        for key in ("TNG_STATION_TORP_TYPES", "TNG_STATION_BUILD_SPEEDUP",
                    "TNG_STATION_TORP_HEADSTART"):
            set_shared_variable(key, None)

    def _station(self, side):
        so = npc_spawn(0, 0, 0, "Yard", side + ", station", "tng_fed_ds9", "behav_station")
        so = getattr(so, "py_object", so)
        so.side = side.lower()
        for key in _ALL:
            set_inventory_value(so, f"{key}_BUILD_SPEED", _BUILD[key])
            set_data_set_value(so, f"{key}_NUM", 2)
        set_inventory_value(so, "torpedo_production_keys", list(_ALL))
        set_data_set_value(so, "torpedo_types_available", ",".join(_ALL))
        return so

    # --- the gate ---------------------------------------------------------------------
    def test_a_stock_station_is_left_completely_alone(self):
        """The condition the report attached: do not break the base game."""
        so = self._station("tsn")
        self.assertEqual(T.tng_station_setup_torpedoes(so), "")
        self.assertEqual(get_data_set_value(so, "torpedo_types_available"), ",".join(_ALL))
        self.assertEqual(get_inventory_value(so, "Photon_BUILD_SPEED"), 3)
        self.assertEqual(get_data_set_value(so, "Homing_NUM"), 2)

    def test_a_mod_side_station_is_ours(self):
        self.assertTrue(T.tng_is_mod_side(self._station("federation")))
        self.assertTrue(T.tng_is_mod_side(self._station("Dominion")))

    def test_a_side_the_mod_does_not_own_is_not(self):
        self.assertFalse(T.tng_is_mod_side(self._station("borg")))
        self.assertFalse(T.tng_is_mod_side(self._station("tsn")))

    # --- what it does -----------------------------------------------------------------
    def test_it_keeps_only_the_tng_rounds(self):
        so = self._station("federation")
        T.tng_station_setup_torpedoes(so)
        self.assertEqual(get_data_set_value(so, "torpedo_types_available"),
                         "Photon,Quantum,Tricobalt")
        self.assertEqual(get_inventory_value(so, "torpedo_production_keys"),
                         ["Photon", "Quantum", "Tricobalt"])

    def test_the_dropped_rounds_are_emptied_not_just_hidden(self):
        """A stock round left in stock would still transfer to a hull that can hold it."""
        so = self._station("federation")
        T.tng_station_setup_torpedoes(so)
        for key in ("Homing", "Nuke", "EMP", "Mine"):
            self.assertEqual(get_data_set_value(so, f"{key}_NUM"), 0, key)

    def test_build_times_come_down_but_keep_their_ratio(self):
        """A Tricobalt stays four Photons' worth of yard time."""
        so = self._station("federation")
        T.tng_station_setup_torpedoes(so)
        photon = get_inventory_value(so, "Photon_BUILD_SPEED")
        self.assertAlmostEqual(photon, 1.0)
        self.assertAlmostEqual(get_inventory_value(so, "Quantum_BUILD_SPEED"), 2.0)
        self.assertAlmostEqual(get_inventory_value(so, "Tricobalt_BUILD_SPEED"), 4.0)

    def test_a_crew_arriving_finds_rounds_already_built(self):
        so = self._station("federation")
        T.tng_station_setup_torpedoes(so)
        self.assertEqual(get_data_set_value(so, "Photon_NUM"), 10)
        self.assertEqual(get_data_set_value(so, "Quantum_NUM"), 5)
        self.assertEqual(get_data_set_value(so, "Tricobalt_NUM"), 2)

    def test_running_it_twice_changes_nothing(self):
        """It writes absolute values, so a re-spawn or a second route cannot compound."""
        so = self._station("federation")
        T.tng_station_setup_torpedoes(so)
        first = (get_inventory_value(so, "Photon_BUILD_SPEED"),
                 get_data_set_value(so, "Photon_NUM"))
        T.tng_station_setup_torpedoes(so)
        self.assertEqual((get_inventory_value(so, "Photon_BUILD_SPEED"),
                          get_data_set_value(so, "Photon_NUM")), first)

    def test_a_type_nothing_registered_is_not_listed(self):
        """Listing a round no prefab defined would put a dead row in the comms menu -
        which is the fault being fixed, not a new one."""
        set_shared_variable("TNG_STATION_TORP_TYPES", "Photon,Polaron")
        so = self._station("federation")
        T.tng_station_setup_torpedoes(so)
        self.assertEqual(get_data_set_value(so, "torpedo_types_available"), "Photon")

    # --- the dials --------------------------------------------------------------------
    def test_the_type_list_is_a_setting(self):
        set_shared_variable("TNG_STATION_TORP_TYPES", "Photon")
        so = self._station("federation")
        T.tng_station_setup_torpedoes(so)
        self.assertEqual(get_data_set_value(so, "torpedo_types_available"), "Photon")

    def test_the_speedup_is_a_setting(self):
        set_shared_variable("TNG_STATION_BUILD_SPEEDUP", 6)
        so = self._station("federation")
        T.tng_station_setup_torpedoes(so)
        self.assertAlmostEqual(get_inventory_value(so, "Photon_BUILD_SPEED"), 0.5)

    def test_the_head_start_is_a_setting(self):
        set_shared_variable("TNG_STATION_TORP_HEADSTART", 0)
        so = self._station("federation")
        T.tng_station_setup_torpedoes(so)
        self.assertEqual(get_data_set_value(so, "Photon_NUM"), 1,
                         "a station should still have one round, not zero")

    def test_a_junk_setting_falls_back_rather_than_raising(self):
        set_shared_variable("TNG_STATION_BUILD_SPEEDUP", "fast")
        self.assertAlmostEqual(T.tng_station_build_speedup(), 3.0)


if __name__ == "__main__":
    unittest.main()
