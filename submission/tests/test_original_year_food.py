import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from overseer.year import YearOverseer
from overseer.frontier import Overseer as FrontierOverseer
class OriginalFood(unittest.TestCase):
 def test_full_year_uses_exact_promoted_endgame_food_method(self):
  self.assertIs(YearOverseer.endgame_supply,FrontierOverseer.endgame_supply)
if __name__=="__main__":unittest.main()
