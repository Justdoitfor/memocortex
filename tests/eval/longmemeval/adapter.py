"""LongMemEval adapter — 数据集存在性检查与官方数据集切换接口

MVP 默认用 build_dataset.py 生成的 cn_30.json. 真要切官方英文 LongMemEval
只需:
  1. pip install datasets
  2. uv run python -c "
       from datasets import load_dataset
       ds = load_dataset('xiaowu0162/longmemeval', split='train[:30]')
       ds.to_json('tests/eval/longmemeval/data/longmem_30.json')
     "
  3. 改 runner.DATA_PATH 指向 longmem_30.json + 写 schema converter
"""

from __future__ import annotations

from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent / "data" / "cn_30.json"


def is_available() -> bool:
    return DATA_PATH.exists()
