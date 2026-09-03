"""Which hulls get the special ordnance, and when.

The Federation had one torpedo type - `Homing` - shared with every TSN light cruiser.
Photon replaces it, and two rarer rounds are gated by hull: Quantum on the late-era
heavies, Tricobalt on Voyager and nothing else.

The two things pinned here are the two that were WRONG in a first version and silent
both times: reading the hull off the wrong field, and checking it only at spawn.
"""
import os
import sys
import unittest

from sbs_utils.fs import test_set_exe_dir
test_set_exe_dir()

import cosmos_dev.mock.sbs as mock
sys.modules.setdefault("sbs", mock)
sys.path.insert(0, os.path.dirname(__file__))
import tng_ordnance as ORD

from sbs_utils.agent import Agent, clear_shared
from sbs_utils.helpers import Context, FakeEvent, FrameContext
from sbs_utils.procedural.query import to_object
from sbs_utils.procedural.roles import has_role
from sbs_utils.procedural.spawn import npc_spawn, player_spawn
from sbs_utils.procedural.torpedoes import torpedo_get_count_for_ship
from sbs_utils.spaceobject import SpaceObject


class OrdnanceBase(unittest.TestCase):
    def setUp(self):
        mock.create_new_sim()
        Agent.clear()
        clear_shared()
        SpaceObject.clear()
        FrameContext.context = Context(mock.sim, mock, FakeEvent(1))

    def tearDown(self):
        FrameContext.context = None

    def player(self, hull):
        # `player_spawn`'s last argument IS the hull key - there is no behaviour slot.
        return to_object(player_spawn(0, 0, 0, "Ship", "federation", hull))


class TestWhoCarriesWhat(OrdnanceBase):
    def test_voyager_alone_gets_the_tricobalt(self):
        self.assertEqual(ORD.tng_tricobalt_hull(), "tng_fed_intrepid")
        self.assertNotIn("tng_fed_intrepid", ORD.tng_quantum_hulls())

    def test_quantum_is_the_late_era_heavies_only(self):
        hulls = ORD.tng_quantum_hulls()
        self.assertIn("tng_fed_sovereign", hulls)
        self.assertIn("tng_fed_defiant", hulls)
        self.assertNotIn("tng_fed_constellation", hulls,
                         "a Constellation is the wrong century for a quantum torpedo")
        self.assertNotIn("tng_fed_excelsior_refit", hulls)


class TestTheHullRead(OrdnanceBase):
    def test_IT_IS_NOT_data_tag(self):
        """The field a first version read. It answers None for a player ship, so both
        gates matched nothing and the two rounds went to nobody - silently, with the run
        still reporting PASS."""
        ship = self.player("tng_fed_intrepid")
        self.assertEqual(ORD.tng_hull_of(ship), "tng_fed_intrepid")

    def test_an_object_with_no_hull_is_not_an_error(self):
        self.assertEqual(ORD.tng_hull_of(None), "")


class TestTheGrant(OrdnanceBase):
    def held(self, ship, key):
        return torpedo_get_count_for_ship(ship.id, key)[1]

    def test_voyager_is_given_the_tricobalt(self):
        ship = self.player("tng_fed_intrepid")
        ORD.tng_torp_grant(ship.id)
        self.assertTrue(has_role(ship.id, "tricobalt_armed"))
        self.assertEqual(self.held(ship, "Tricobalt"), 2)

    def test_and_nobody_else_is(self):
        ship = self.player("tng_fed_excelsior_refit")
        ORD.tng_torp_grant(ship.id)
        self.assertFalse(has_role(ship.id, "tricobalt_armed"))
        self.assertEqual(self.held(ship, "Tricobalt"), 0)

    def test_a_defiant_gets_quantum(self):
        ship = self.player("tng_fed_defiant")
        ORD.tng_torp_grant(ship.id)
        self.assertEqual(self.held(ship, "Quantum"), 4)

    def test_AND_AGAIN_AFTER_A_RE_HULL(self):
        """The second thing a first version got wrong. Gamma with a Q seats every crew in
        a story ship MINUTES after spawn, so a spawn-time check saw the roster's hull and
        matched nothing. `ship_hull_changed` is the hook; this is what it calls."""
        ship = self.player("tng_fed_excelsior_refit")
        ORD.tng_torp_grant(ship.id)
        self.assertEqual(self.held(ship, "Quantum"), 0, "not a heavy yet")
        ship.set_ship_data_key("tng_fed_defiant")
        ORD.tng_torp_grant(ship.id)
        self.assertEqual(self.held(ship, "Quantum"), 4)

    def test_granting_twice_changes_nothing(self):
        """Both routes can fire for one ship, and re-granting must not stack capacity."""
        ship = self.player("tng_fed_intrepid")
        ORD.tng_torp_grant(ship.id)
        ORD.tng_torp_grant(ship.id)
        self.assertEqual(self.held(ship, "Tricobalt"), 2)

    def test_an_npc_gets_nothing(self):
        foe = to_object(npc_spawn(1000, 0, 0, "Foe", "klingon", "tng_fed_intrepid",
                                  "behav_npcship"))
        self.assertEqual(ORD.tng_torp_grant(foe.id), "")


if __name__ == "__main__":
    unittest.main()
