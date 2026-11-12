"""cx profession match. DF's combat reports name a citizen by a noun that can differ from the observation's
profession (dfhack.units.getProfessionName): hint hard OP1-2 on 7fa625d "The stray blue peahen snatches at the
diagnostician" with the citizen's profession "Diagnoser", and hard MY1-4 on cf32708 "The buzzard bites the
diagnostician". Both now count as citizen fights for stray_cull and combat_species; animals and caravan visitors
still do not. No game."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_danger_marks import Quiet  # noqa: E402
from test_stray_cull import ANIMALS, look  # noqa: E402
from test_grazer_shaft import AnimalGame  # noqa: E402
from overseer import harness  # noqa: E402

# every profession the 281 hint api logs' observations showed (lowercase)
PROFS = {"administrator", "animal caretaker", "animal dissector", "animal trainer", "armorer", "axedwarf",
         "beekeeper", "blacksmith", "bone carver", "bone doctor", "bookbinder", "bowyer", "brewer", "butcher",
         "carpenter", "cheesemaker", "clerk", "clothier", "cook", "craftsdwarf", "diagnoser", "doctor",
         "dwarven child", "dyer", "engraver", "expedition leader", "farmer", "fish cleaner", "fish dissector",
         "fisherdwarf", "furnace operator", "gelder", "gem cutter", "gem setter", "glassmaker", "glazer",
         "hammerdwarf", "herbalist", "hunter", "jeweler", "king", "king consort", "leatherworker", "lye maker",
         "manager", "marksdwarf", "mason", "mechanic", "metalcrafter", "metalsmith", "militia commander", "milker",
         "miller", "miner", "papermaker", "peasant", "planter", "potash maker", "potter", "presser", "pump operator",
         "queen", "queen consort", "ranger", "recruit", "shearer", "siege engineer", "siege operator", "soap maker",
         "speardwarf", "spinner", "stone carver", "stonecrafter", "stonecutter", "stoneworker", "strand extractor",
         "surgeon", "swordsdwarf", "tanner", "thresher", "trader", "trapper", "wax worker", "weaponsmith", "weaver",
         "wood burner", "woodcrafter", "woodcutter", "woodworker", "wrestler"} | harness.CITIZEN_WORDS
# every combat-report noun of those logs that is not a listed profession (animals, visitors, the odd phrase)
NOT_CITIZENS = ["kea", "rhesus macaque", "alligator", "gray langur", "longnose gar", "buzzard", "carp", "raven",
                "badger sow", "badger boar", "pike", "emu", "sea lamprey", "wild boar sow", "river otter",
                "outpost liaison", "kangaroo doe", "great horned owl", "hippo", "opossum", "giant kea", "piglet",
                "alligator snapping turtle", "carnotaurus", "kangaroo buck", "rhesus macaque's throat", "merchant",
                "wolf", "wild boar", "groundhog", "milkfish", "kea's throat", "doe rabbit", "dog", "kestrel",
                "two-humped camel", "sturgeon", "poult", "turkey hen", "keet", "kingsnake", "tiercel peregrine",
                "willow logs", "tigerfish", "coati", "blue peacock", "rattlesnake", "giant buzzard", "barn owl",
                "ram", "guineacock", "sparrow woman", "stray guineahen", "stray dog", "keet (tame)"]


class Nouns(unittest.TestCase):
    def test_the_diagnostician_is_the_diagnoser(self):
        self.assertTrue(harness.citizen_noun("diagnostician", PROFS))
        self.assertFalse(harness.citizen_noun("diagnostician", PROFS - {"diagnoser"}))   # no such citizen here

    def test_exact_and_citizen_words(self):
        for n in ("carpenter", "furnace operator", "militia commander", "macedwarf", "dwarf"):
            self.assertTrue(harness.citizen_noun(n, PROFS), n)

    def test_no_report_animal_or_visitor_is_a_citizen(self):
        for n in NOT_CITIZENS:
            self.assertFalse(harness.citizen_noun(n, PROFS), n)

    def test_stem_needs_a_long_common_start_and_a_short_tail(self):
        self.assertTrue(harness.citizen_noun("stone-worker", {"stoneworker"}))
        self.assertFalse(harness.citizen_noun("stonecutter", {"stonecrafter"}))
        self.assertFalse(harness.citizen_noun("woodcutter", {"woodcrafter"}))


class Uses(Quiet):
    def test_combat_species_sees_the_buzzard_fight(self):
        ov = harness.Overseer(AnimalGame([]), days=336)
        obs = {"dwarves": [{"profession": "Diagnoser"}, {"profession": "Miner"}]}
        self.assertEqual(ov.combat_species(obs, ["The buzzard bites the diagnostician in the left lower arm!"]),
                         ["buzzard"])

    def test_learn_marks_marks_the_buzzard_that_bit_the_diagnostician(self):
        ov = harness.Overseer(AnimalGame([]), days=336)
        ov.marked.pop("buzzard", None)
        obs = {"dwarves": [{"profession": "Diagnoser"}],
               "recent_events": ["The buzzard bites the diagnostician in the left lower arm!",
                                 "The stray blue peahen snatches at the diagnostician in the right upper leg!"]}
        found = ov.learn_marks(obs)
        self.assertIn(("buzzard", "combat"), [(n, src) for n, src, _ in found])
        self.assertEqual(ov.marked.get("buzzard"), "combat")
        self.assertNotIn("blue peahen", ov.marked)   # a stray is the fortress's own: never a species mark
        self.assertNotIn("diagnostician", ov.marked)

    def test_learn_marks_leaves_a_fight_between_animals(self):
        ov = harness.Overseer(AnimalGame([]), days=336)
        ov.marked.pop("buzzard", None)
        ov.learn_marks({"dwarves": [{"profession": "Diagnoser"}],
                        "recent_events": ["The buzzard bites the kestrel in the head!"]})
        self.assertNotIn("buzzard", ov.marked)

    def test_stray_cull_takes_the_peahen_that_struck_the_diagnostician(self):
        game = AnimalGame(ANIMALS)
        ov = harness.Overseer(game, days=336)
        r = look(329, ["The stray blue peahen snatches at the diagnostician in the right upper leg with her first "
                       "toe, right foot, bruising the fat!"])
        r["observation"]["dwarves"].append({"id": 904, "profession": "Diagnoser", "x": 1, "y": 1, "z": 168})
        ov.load(r)
        ov.count = 0
        game.calls.clear()
        ov.stray_cull()
        self.assertEqual([a["unit_id"] for t, a in game.calls if t == "slaughter"], [107])


if __name__ == "__main__":
    unittest.main()
