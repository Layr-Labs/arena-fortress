import unittest
from support import overseer,quiet,beast,hold,locked,DAY

class YearWildRefuge(unittest.TestCase):
    def state(self,days=336,day=100,alert=False,inside=0,doors=None):
        kwargs=dict(drink=100,alert=alert,inside=inside)
        if doors is not None:kwargs['doors']=doors
        r=quiet(day,[beast('CRETACEOUS_CARNOTAURUS',60)],**kwargs)
        r['days_left']=days-day if type(days)is int and days>day else 100
        o,g=overseer(r);o.days=days;g.others=r['others'];return o,g,r
    def test_qualified_year_predator_does_not_start_optional_hold(self):
        o,g,r=self.state();o.defend();self.assertIsNone(o.lock);self.assertEqual(g.tools('civilian_alert'),[]);self.assertEqual(g.tools('lock_door'),[]);self.assertEqual(o.year_wild_skip_day,100);self.assertTrue(o.beast_seen)
    def test_short_task_keeps_alert_then_physical_close(self):
        o,g,r=self.state(days=216);o.defend();self.assertIsNotNone(o.lock);self.assertEqual(g.tools('civilian_alert'),[dict(on=True)])
        r=quiet(101,[beast('CRETACEOUS_CARNOTAURUS',60)],drink=100,alert=True,inside=10);r['days_left']=115;o.load(r);o.count=0;g.others=r['others'];o.defend();self.assertTrue(any(x.get('locked')is True for x in g.tools('lock_door')))
    def test_owned_lock_cleanup_precedes_skip(self):
        o,g,r=self.state(doors=locked(14));o.own_locks={14};o.defend();self.assertIn(dict(locked=False,door_id=14),g.tools('lock_door'));self.assertFalse(hasattr(o,'year_wild_skip_day'))
    def test_existing_held_lock_still_closes_and_is_not_abandoned(self):
        o,g,r=self.state(alert=True,inside=10);o.lock=hold(99,beast=99*DAY);o.defend();self.assertEqual(o.lock['phase'],'hold');self.assertTrue(any(x.get('locked')is True for x in g.tools('lock_door')));self.assertFalse(hasattr(o,'year_wild_skip_day'))
    def test_invalid_horizon_and_clock_do_not_enable_new_policy(self):
        for days in [None,0,-1,True,216,336.0,'336']:
            o,g,r=self.state();o.days=days;self.assertFalse(o.skip_year_wild_refuge())
        for left in [None,0,-1,True,1.5,'100']:
            o,g,r=self.state();o.days_left=left;self.assertFalse(o.skip_year_wild_refuge())
    def test_laboratory_and_goal_policies_excluded(self):
        for attr,value in [('lab',True),('hands_off',10),('surge',True),('beds_first',True),('drink_growth',True)]:
            o,g,r=self.state();setattr(o,attr,value);self.assertFalse(o.skip_year_wild_refuge())
    def test_unqualified_quiet_and_unsealed_cases_do_not_log_eligible_skip(self):
        o,g,r=self.state();g.others=[];o.defend();self.assertFalse(hasattr(o,'year_wild_skip_day'))
        o,g,r=self.state();o.o['doors']['list']=[];o.defend();self.assertFalse(hasattr(o,'year_wild_skip_day'))
    def test_repeated_eligible_start_suppression_does_not_own_alarm_or_hatch(self):
        o,g,r=self.state();o.defend();o.count=0;o.defend();self.assertIsNone(o.lock);self.assertFalse(o.own_locks);self.assertFalse(o.alert_pending);self.assertEqual(g.tools('civilian_alert'),[]);self.assertEqual(g.tools('lock_door'),[])
