"""Entry point for aaw CLI — invoked by aaw-workflow skill."""
import sys
from pathlib import Path

# Ensure the skill's cli package is importable
sys.path.insert(0, str(Path(__file__).parent))

# Shared install lock + residue recovery BEFORE importing CLI business modules
# (docs/auto-update-design.md §4.3): no directory swap can happen underneath
# module imports, definitions reads or workflow writes.
from cli import bootstrap

bootstrap.startup(__file__)

import cli.main

cli.main.app()
