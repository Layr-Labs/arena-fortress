"""d67: the aggressive endgame supply runs through ALL of the scored final stretch. The stretch is the last quarter
of the run (84 days on OP1, 54 on MY1) and it is scored on its supply slope: a decline built in the days before the
endgame orders started caps the projection, however good the last weeks are. With 64 days the first 20 days of
OP1's window ran on the ordinary orders only."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import overseer, resp  # noqa: E402
from overseer.harness import ENDGAME_DAYS  # noqa: E402


class D67(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_the_endgame_covers_the_whole_final_quarter(self):
        self.assertGreaterEqual(ENDGAME_DAYS, 84)          # OP1's quarter

    def test_eighty_five_days_out_is_endgame(self):
        ov, _ = overseer(resp(85, 336 - 85, food=60))
        self.assertTrue(ov.in_endgame())

    def test_ninety_one_days_out_is_not(self):
        ov, _ = overseer(resp(ENDGAME_DAYS + 1, 336 - ENDGAME_DAYS - 1, food=60))
        self.assertFalse(ov.in_endgame())


if __name__ == "__main__":
    unittest.main()
