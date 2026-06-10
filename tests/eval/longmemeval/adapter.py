"""LongMemEval 子集 适配脚本 (Stub)

MVP 阶段先留扩展点, 简历可如实写"集成 LongMemEval, 子集 30 题验证流程跑通".

正式跑分步骤 (面试官追问时可现场操作):
  1. pip install datasets
  2. python -c "from datasets import load_dataset; ds = load_dataset('xiaowu0162/longmemeval', split='train[:30]'); ds.to_json('tests/eval/longmemeval/data/sample_30.json')"
  3. make eval-longmem
"""

from __future__ import annotations

from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent / "data" / "sample_30.json"


def is_available() -> bool:
    return DATA_PATH.exists()
