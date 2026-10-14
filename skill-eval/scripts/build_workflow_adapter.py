"""Run from the installed Skill Eval environment; does not fetch or update Skills."""

import argparse
from pathlib import Path

from aaw_skill_eval.services.catalog.workflow_adapter import build_workflow_adapter

parser = argparse.ArgumentParser(description="打包当前仓库的 AAW 三入口评测候选及依赖")
parser.add_argument("--repository", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
print(build_workflow_adapter(args.repository, args.output))
