import unittest
from support import overseer, quiet, beast, WAGON
from overseer.beasts import in_sight, TROOP_NAMES

class ShortKea(unittest.TestCase):
    def state(self,days=216,food=60,dist=60,**kw):
        r=quiet(100,[beast('BIRD_KEA',dist,**kw)],drink=100)
        r['observation']['stocks']['food_edible']=food;ov,g=overseer(r);ov.days=days;g.others=r['others'];return ov,g
    def test_short_kea_starts_existing_alert(self):
        ov,g=self.state();ov.defend();self.assertIsNotNone(ov.lock);self.assertEqual(g.tools('civilian_alert'),[{'on':True}])
    def test_no_quick_lock_while_citizens_gather(self):
        ov,g=self.state(dist=9);ov.defend();self.assertEqual(g.tools('lock_door'),[]);self.assertIsNone(ov.lock['due'])
    def test_existing_hatch_closes_after_gathering(self):
        ov,g=self.state();ov.defend();r=quiet(101,[beast('BIRD_KEA',60)],drink=100,inside=10,alert=True);ov.load(r);ov.count=0;g.others=r['others'];ov.defend();self.assertTrue(any(x.get('locked')for x in g.tools('lock_door')))
    def test_year_unknown_and_invalid_horizons_keep_legacy(self):
        for days in [336,672,None,0,-1,True,216.0,'216']:
            with self.subTest(days=days):
                ov,g=self.state(days=days);ov.defend();self.assertIsNone(ov.lock);self.assertEqual(g.tools('civilian_alert'),[])
    def test_lab_excludes_short_kea(self):
        ov,g=self.state();ov.hands_off=20;ov.defend();self.assertIsNone(ov.lock)
    def test_food_floor_and_unsealed_hatch_guards_remain(self):
        ov,g=self.state(food=2);ov.defend();self.assertIsNone(ov.lock)
        ov,g=self.state();ov.o['doors']['list']=[];ov.defend();self.assertIsNone(ov.lock)
    def test_default_detector_ignores_kea_without_explicit_scope(self):
        self.assertEqual(in_sight([beast('BIRD_KEA',9)],1,WAGON),([],True))
        found,sure=in_sight([beast('BIRD_KEA',9)],1,WAGON,TROOP_NAMES);self.assertTrue(sure);self.assertEqual(found[0]['race'],'BIRD_KEA')
    def test_tame_hostile_and_visitor_kea_are_not_added(self):
        for flag in ['tame','hostile','visitor']:
            with self.subTest(flag=flag):self.assertEqual(in_sight([beast('BIRD_KEA',9,**{flag:True})],1,WAGON,TROOP_NAMES),([],True))
    def test_exact_species_only_not_giant_kea_or_other_troops(self):
        for race in ['GIANT_KEA','BIRD_BUZZARD','GRAY_LANGUR','WOLF']:
            with self.subTest(race=race):self.assertEqual(in_sight([beast(race,9)],1,WAGON,TROOP_NAMES),([],True))
    def test_large_predators_and_lurker_scaling_are_unchanged(self):
        rows=[beast('ALLIGATOR',30)];self.assertEqual(in_sight(rows,1,WAGON),in_sight(rows,1,WAGON,TROOP_NAMES));self.assertEqual(in_sight(rows,1,WAGON)[0][0]['dist'],150)

if __name__=='__main__':unittest.main()
