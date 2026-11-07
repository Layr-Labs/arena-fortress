"""Validate generated controller orders against the organiser's actual public argument converter.
Run from the repository root; no game, network or private data is read.
"""
import io
import os
import sys
import unittest
from pathlib import Path
from contextlib import redirect_stdout
ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
VARIANT = Path(os.environ.get("FORTRESS_VARIANT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(VARIANT))
from overseer.harness import Overseer
from gameapi.facts.tools import order_spec, Rejected

class ContractGame:
    def __init__(self): self.calls=[]
    def act(self, tool, args):
        if tool == "add_order": order_spec(args)
        self.calls.append((tool,dict(args)))
        return {"ok":True,"result":{"order_id":len(self.calls)}}

class OrderContract(unittest.TestCase):
    def test_generated_orders_fit_actual_public_converter_across_population_and_stock_ranges(self):
        bad=[];cases=0
        for pop in [7,18,24,25,30,39,43,46,49,53,80,120]:
            for beds in [0,8,18,21,22,30,40,60,100,130]:
                for left in [None,39,14,1,0]:
                    cases += 1
                    g=ContractGame();o=Overseer(g)
                    o.load({"tick":0,"hands_off_in_days":left,"observation":{
                        "administrators":{"citizens":pop},
                        "stocks":{"beds":beds,"tables":1,"chairs":1,"logs_usable":100},
                        "orders":[{"recipe":r,"repeat":"daily"} for r in ["brew_drink","make_barrel","cook_meal"]]}})
                    o.count=0
                    try:
                        with redirect_stdout(io.StringIO()):o.supply()
                    except Rejected as e:bad.append((pop,beds,left,str(e)))
        self.assertEqual(cases,600)
        self.assertEqual(bad,[],str(bad[:5]))

if __name__ == "__main__": unittest.main()
