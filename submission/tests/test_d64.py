"""d64: from ENDGAME_DAYS out the layer passes once a game day, not once every two. The scored final stretch is
read day by day: a pass that skips a day cannot see that day's stock reach zero, and the coverage share counts
it. Both of this line's bad open games in the official draw were late supply dips (a MY1 and an OP1 game at
tier 1, about 85 each): survival and wellbeing were clean, the stock hit zero on days nobody was looking. One
extra pass a day for the last 64 days costs seconds of wall time."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import overseer, resp  # noqa: E402
from overseer.harness import ENDGAME_DAYS  # noqa: E402


class D64(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_one_day_a_pass_in_the_final_stretch(self):
        ov, _ = overseer(resp(ENDGAME_DAYS, 336 - ENDGAME_DAYS, food=60))
        self.assertEqual(ov.step_days(), 1)

    def test_two_days_a_pass_before_it(self):
        ov, _ = overseer(resp(ENDGAME_DAYS + 1, 336 - ENDGAME_DAYS - 1, food=60))
        self.assertEqual(ov.step_days(), 2)

    def test_a_lab_keeps_its_pace(self):
        # a lab never reaches step_days through quiet_days (no open play, no lockdown); the days_left gate does not
        # change that: this is the layer's own answer, and quiet_days' open_play() check still guards the call
        ov, _ = overseer(resp(40, 20, food=60, hands_off=19))
        self.assertFalse(ov.open_play())
        self.assertEqual(ov.step_days(), 1)      # the gate would say one; the caller never asks a lab


if __name__ == "__main__":
    unittest.main()
