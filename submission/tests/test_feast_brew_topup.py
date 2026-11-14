import unittest
from support import overseer, resp

class FeastBrewTopup(unittest.TestCase):
    def state(self,days=216,left=8,food=65,drink=326,plants=6,barrels=13):
        ov,g=overseer(resp(left,207,food,drink,cit=17,plants=plants),herd=[])
        ov.days=days;ov.st.update(plants_brewable=plants,barrels_empty=barrels)
        return ov,g
    def brews(self,g):
        return [x for x in g.tools('add_order') if x.get('recipe')=='brew_drink']
    def test_actual_feast_requests_finite_two_job_topup(self):
        ov,g=self.state();ov.feast();rows=self.brews(g)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['amount'],2);self.assertNotIn('repeat',rows[0])
        self.assertNotIn('when',rows[0])
    def test_finite_order_omits_repeat_only_conditions(self):
        ov,g=self.state();ov.feast();self.assertNotIn('when',self.brews(g)[0]);self.assertNotIn('repeat',self.brews(g)[0])
    def test_acknowledged_success_not_duplicated_on_stale_views(self):
        ov,g=self.state();ov.feast_brew_topup();ov.feast_brew_topup();self.assertEqual(len(self.brews(g)),1)
    def test_refused_order_retries_at_interval_and_stops_after_three(self):
        ov,g=self.state();g.refuse.add(('add_order',None))
        for day in [207,207,208,209,211,213,215]:
            ov.now=day*1200;ov.feast_brew_topup()
        self.assertEqual(len(self.brews(g)),3);self.assertNotIn('o_feast_brew_topup',ov.done)
    def test_refusal_can_be_followed_by_one_acknowledged_retry(self):
        ov,g=self.state();g.refuse.add(('add_order',None));ov.feast_brew_topup();g.refuse.clear();ov.now+=2400;ov.feast_brew_topup();ov.now+=2400;ov.feast_brew_topup();self.assertEqual(len(self.brews(g)),2);self.assertIn('o_feast_brew_topup',ov.done)
    def test_year_and_unknown_horizons_keep_legacy_policy(self):
        for days in [336,672,None,0,-1,'216',True,216.0]:
            with self.subTest(days=days):
                ov,g=self.state(days=days);ov.feast_brew_topup();self.assertEqual(self.brews(g),[])
    def test_outside_feast_and_too_late_do_not_request(self):
        for left in [15,1,0,-1]:
            with self.subTest(left=left):
                ov,g=self.state(left=left);ov.feast_brew_topup();self.assertEqual(self.brews(g),[])
    def test_food_plants_barrels_and_drink_guards(self):
        for kw in [dict(food=50),dict(plants=1),dict(barrels=0),dict(drink=374)]:
            with self.subTest(kw=kw):
                ov,g=self.state(**kw);ov.feast_brew_topup();self.assertEqual(self.brews(g),[])
    def test_unbuilt_still_and_lab_are_excluded(self):
        ov,g=self.state();next(w for w in ov.o['workshops']if w['type']=='Still')['built']=False;ov.feast_brew_topup();self.assertEqual(self.brews(g),[])
        ov,g=self.state();ov.hands_off=5;ov.feast_brew_topup();self.assertEqual(self.brews(g),[])
    def test_inherited_feast_stop_remains_authoritative(self):
        ov,g=self.state();ov.brew_stopped=True;ov.feast_brew_topup();self.assertEqual(self.brews(g),[])
    def test_boundary_resources_allow_exactly_one_request(self):
        ov,g=self.state(food=51,plants=2,barrels=1,drink=373,left=2);ov.feast_brew_topup();self.assertEqual(len(self.brews(g)),1)

if __name__=='__main__':unittest.main()
