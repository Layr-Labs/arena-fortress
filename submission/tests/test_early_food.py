import unittest
from unittest.mock import Mock
from overseer.harness import Overseer

class EarlyFood(unittest.TestCase):
    def make(self,food):
        o=Overseer(Mock());o.cit=14;o.st={"food_edible":food};o.people=[];o.orders=[];o.now=0;o.count=0
        o.standing=lambda recipe:True;o.logs=lambda:0;o.butcher=Mock()
        o.zones=[];o.free={};o.o={"furniture":[]};return o
    def test_low_stock_requests_food_before_final_window(self):
        o=self.make(27);o.supply();o.butcher.assert_called_once_with(prefer_food=True)
    def test_two_units_per_citizen_does_not_trigger(self):
        o=self.make(28);o.supply();o.butcher.assert_not_called()
    def test_unknown_food_stock_does_not_trigger(self):
        o=self.make(None);o.supply();o.butcher.assert_not_called()
