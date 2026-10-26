"""dfbench runner library (runner/README.md): one game per Compose project, suites, trusted scoring."""
import os

RUNNER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(RUNNER)
RUNNER_VERSION = "s0-runner/1"
