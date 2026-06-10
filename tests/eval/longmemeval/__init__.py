"""LongMemEval-style 中文长记忆评测 — 30 题子集

LongMemEval (Wu et al. 2024, Salesforce AI) 是英文长对话 QA benchmark, 测 Agent
在数十轮跨 session 对话后是否能回忆关键事实. MVP 阶段直接拉官方数据集存在 4 个问题:
  1. 数据集托管在 HuggingFace, 国内/CI 网络不稳定
  2. 每题动辄上千轮对话, MVP 资源跑不起
  3. 全英文, 与本项目"中文优先"定位不符
  4. 部分子任务需要本地推理引擎, demo 跑通门槛高

替代方案: 按官方 4 个子维度构造 30 题中文 LongMemEval-style 数据集, 简化对话规模
(每题 5-15 轮 distractor + 1 个关键 fact), schema 完全对齐. 真要切官方数据集
时只改 loader.

子维度:
  - single_session_assistant  → SS  10 题  (单轮内提到的事实, 长上下文中能回忆)
  - multi_session             → MS  10 题  (跨多个 session, 信息分散)
  - temporal_reasoning        → TR   5 题  (时间敏感: 'X 周后', '上次')
  - knowledge_update          → KU   5 题  (信息更新: 用户改口/搬家/换工作)
"""
