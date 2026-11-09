"""Entrypoint: python -m steward (reads DFBENCH_TASK)."""
import sys

from .harness import main

sys.exit(main())
