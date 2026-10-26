"""Put baseline/ and baseline/tests/ on sys.path, so tests run from any directory:
    python3 -m unittest discover -s baseline/tests -t baseline"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
for p in (BASE, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)
