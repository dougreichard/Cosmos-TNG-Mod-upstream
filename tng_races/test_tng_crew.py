"""The canonical crews, as data.

Sitting at engineering on a Galaxy-class should make you Geordi. That is a `Hull:`-bound
roster and nothing else, so the ways it fails are authoring ways: a hull key that is not in
the ship table binds to nothing, a portrait key that is not on the sheet just never draws,
and a duplicate member key silently replaces a person. None of them raise.

Static: it reads the .amd and the two JSON tables beside it. No engine, no page, no client.

    python -m unittest test_tng_crew
"""
import json
import os
import unittest

from sbs_utils.fs import test_set_exe_dir
test_set_exe_dir()

from sbs_utils.procedural.amd import amd_read_text
from sbs_utils.procedural.amd_doc import amd_document
from sbs_utils.procedural.amd_crew import amd_crew_data, crew_from_document
import sbs_utils.procedural.crew as crew


HERE = os.path.dirname(os.path.abspath(__file__))
CREWS = os.path.join(HERE, "tng_crew.amd")
PORTRAITS = os.path.join(HERE, "tng_portraits.json")
SHIPS = os.path.join(os.path.dirname(HERE), "media", "tng_ships.json")

#: How a portrait is addressed once `tng_register_portraits` has cut the sheet.
DOMAIN = "tng:"


def _load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


class TngCrewCase(unittest.TestCase):
    def setUp(self):
        self.rosters = crew_from_document(
            amd_document(amd_read_text(CREWS), data_parser=amd_crew_data))
        self.by_key = {r.key: r for r in self.rosters}
        self.members = [m for r in self.rosters for m in r.members]


class TestTheCasts(TngCrewCase):
    def test_all_four_ships_are_declared(self):
        self.assertEqual(set(self.by_key),
                         {"tng_enterprise_d", "tng_voyager", "tng_defiant", "tng_enterprise"})

    def test_every_bridge_station_is_crewed(self):
        """The five a player actually opens, plus the captain's screen. A station this
        misses falls through to an automatic name, which on a canonical ship reads as the
        cast being incomplete rather than as a deliberate gap."""
        for key, roster in self.by_key.items():
            named = {m.console for m in roster.members if m.console}
            self.assertTrue(
                {"mainscreen", "helm", "weapons", "science", "engineering", "comms"} <= named,
                f"{key} leaves {'mainscreen helm weapons science engineering comms'.split()} "
                f"short: {sorted(named)}")

    def test_nobody_shares_a_key_within_a_roster(self):
        for key, roster in self.by_key.items():
            keys = [m.key for m in roster.members]
            self.assertEqual(sorted(keys), sorted(set(keys)), key)

    def test_worf_serves_twice_under_different_keys(self):
        """He is on both ships, and a pick is stored as `<roster>:<member>` - so the two
        have to be separate members, not one shared key."""
        worf = [m for m in self.members if m.name == "Worf"]
        self.assertEqual(len(worf), 2)
        self.assertEqual(len({m.key for m in worf}), 2)


class TestItBindsToRealThings(TngCrewCase):
    def test_every_hull_is_in_the_ship_table(self):
        keys = {e["key"] for e in _load(SHIPS)["#ship-list"]}
        for roster in self.rosters:
            for hull in roster.hull:
                self.assertIn(hull, keys,
                              f"{roster.key} binds {hull}, which no ship has - it can never "
                              "crew anything")

    def test_every_portrait_is_on_the_sheet(self):
        names = set(_load(PORTRAITS))
        for m in self.members:
            self.assertTrue(m.portrait.startswith(DOMAIN), f"{m.key}: {m.portrait!r}")
            self.assertIn(m.portrait[len(DOMAIN):], names, m.key)

    def test_nobody_carries_a_face_string(self):
        """A face needs allFaceFiles.txt edited by hand, which a mastlib cannot do, so it
        would silently fail to draw on most installs. Portraits ship with the mod."""
        self.assertEqual([m.key for m in self.members if m.face], [])


class TestItResolves(TngCrewCase):
    def setUp(self):
        super().setUp()
        crew.crew_clear()
        crew.crew_names_clear()
        crew.crew_declare(self.rosters)
        self.addCleanup(crew.crew_clear)
        self.addCleanup(crew.crew_names_clear)

    def test_a_galaxy_class_seats_geordi_at_engineering(self):
        roster, source = crew.crew_roster_for(None, "tng_fed_galaxy")
        self.assertEqual(source, "hull")
        post = crew.crew_resolve(1, None, "engineering", hull="tng_fed_galaxy")
        self.assertEqual(post.name, "Geordi La Forge")
        self.assertEqual(post.portrait, "tng:geordi")

    def test_an_intrepid_seats_torres_instead(self):
        post = crew.crew_resolve(1, None, "engineering", hull="tng_fed_intrepid")
        self.assertEqual(post.name, "B'Elanna Torres")

    def test_a_hull_nobody_wrote_for_gets_an_automatic_crew(self):
        post = crew.crew_resolve(1, None, "engineering", hull="tng_fed_sovereign")
        self.assertEqual(post.source, "library")
        self.assertTrue(post.name)


if __name__ == "__main__":
    unittest.main()
