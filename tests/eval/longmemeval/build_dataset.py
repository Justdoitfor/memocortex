"""数据集构造脚本 — 一次性生成 30 题 LongMemEval-style 中文长记忆 JSON

设计原则:
  - 每个 question 都有 N 条 distractor 对话 + 1-3 条关键事实
  - 关键事实通过 sessions 注入 (会被 MemoCortex 写入)
  - distractor 用于检验"召回准确性"(top-K 不能被噪声淹没)
  - knowledge_update 子维度专门测试冲突仲裁

执行:
  uv run python -m tests.eval.longmemeval.build_dataset
"""

from __future__ import annotations

import json
from pathlib import Path

_OUT_DIR = Path(__file__).resolve().parent / "data"
_OUT_FILE = _OUT_DIR / "cn_30.json"


# ╔══════════════════════════════════════════════════════════════════════╗
# ║                  通用的 distractor 对话池                              ║
# ╚══════════════════════════════════════════════════════════════════════╝

DISTRACTORS = [
    "今天天气还不错, 风有点大",
    "我中午吃了一碗牛肉面",
    "周末打算去看个电影",
    "最近在追一部古装剧",
    "刚收到快递, 是上周买的耳机",
    "电脑突然蓝屏了, 重启好了",
    "公司楼下新开了一家咖啡店",
    "晚上跑步遇到了好多人",
    "明天有个产品评审会",
    "刚才喝了一杯美式, 很提神",
    "听说下周要降温",
    "刚看完一篇关于 AI 的论文",
    "地铁上特别挤, 站了一路",
    "新闻里说股市又跌了",
    "猫今天不肯吃饭, 不知道怎么回事",
]


def _mk_distractor_session(n: int, start: int = 0) -> list[dict]:
    """生成 n 轮无关闲聊."""
    out: list[dict] = []
    for i in range(n):
        out.append({"role": "user", "content": DISTRACTORS[(start + i) % len(DISTRACTORS)]})
        out.append({"role": "ai", "content": "嗯, 了解了"})
    return out


# ╔══════════════════════════════════════════════════════════════════════╗
# ║   Single-Session (SS) — 单轮长上下文中, 用户提到的事实能被准确回忆     ║
# ╚══════════════════════════════════════════════════════════════════════╝

SS_CASES = [
    {
        "user_id": "lme_user_ss_01",
        "fact": "我最喜欢的咖啡店是 Blue Bottle, 上海安福路那家",
        "question": "用户最喜欢的咖啡店是哪家",
        "expected_answer": "Blue Bottle",
        "must_contain": ["Blue Bottle"],
    },
    {
        "user_id": "lme_user_ss_02",
        "fact": "我家阳台上种了两盆薄荷和一盆迷迭香",
        "question": "用户家阳台种了什么植物",
        "expected_answer": "薄荷 迷迭香",
        "must_contain": ["薄荷"],
    },
    {
        "user_id": "lme_user_ss_03",
        "fact": "我的初代 iPhone 是高三那年买的 4S",
        "question": "用户的第一部 iPhone 是哪个型号",
        "expected_answer": "iPhone 4S",
        "must_contain": ["4S"],
    },
    {
        "user_id": "lme_user_ss_04",
        "fact": "我大学时主修计算机, 辅修了心理学",
        "question": "用户大学辅修什么专业",
        "expected_answer": "心理学",
        "must_contain": ["心理学"],
    },
    {
        "user_id": "lme_user_ss_05",
        "fact": "我家狗叫旺财, 是只 5 岁的柯基",
        "question": "用户养的是什么品种的狗",
        "expected_answer": "柯基",
        "must_contain": ["柯基"],
    },
    {
        "user_id": "lme_user_ss_06",
        "fact": "我去年生日是在京都过的, 还看到了樱花",
        "question": "用户上个生日在哪里过的",
        "expected_answer": "京都",
        "must_contain": ["京都"],
    },
    {
        "user_id": "lme_user_ss_07",
        "fact": "我现在用的相机是富士 X-T5, 配 35mm 定焦镜头",
        "question": "用户当前用的相机是哪款",
        "expected_answer": "富士 X-T5",
        "must_contain": ["X-T5"],
    },
    {
        "user_id": "lme_user_ss_08",
        "fact": "我对青霉素过敏, 每次去医院都要特别告知",
        "question": "用户对什么药物过敏",
        "expected_answer": "青霉素",
        "must_contain": ["青霉素"],
    },
    {
        "user_id": "lme_user_ss_09",
        "fact": "我目前在杭州滨江区的一家 AI 创业公司做算法工程师",
        "question": "用户在哪个城市工作",
        "expected_answer": "杭州",
        "must_contain": ["杭州"],
    },
    {
        "user_id": "lme_user_ss_10",
        "fact": "我老婆叫林晓, 是个产品经理, 在阿里工作",
        "question": "用户配偶的职业是什么",
        "expected_answer": "产品经理",
        "must_contain": ["产品经理"],
    },
]


# ╔══════════════════════════════════════════════════════════════════════╗
# ║   Multi-Session (MS) — 信息分布在多个 session, 召回时跨段拼接          ║
# ╚══════════════════════════════════════════════════════════════════════╝

MS_CASES = [
    {
        "user_id": "lme_user_ms_01",
        "facts": [
            "我在准备去日本旅游, 已经买了机票",
            "酒店订的是大阪心斋桥附近的",
            "我的航班是 5 月 12 号下午的",
        ],
        "question": "用户什么时候出发去日本",
        "expected_answer": "5 月 12 号",
        "must_contain": ["5 月 12"],
    },
    {
        "user_id": "lme_user_ms_02",
        "facts": [
            "我最近在学吉他",
            "目前主要练的是民谣指弹",
            "老师说我的右手节奏感不错",
        ],
        "question": "用户在学什么乐器",
        "expected_answer": "吉他",
        "must_contain": ["吉他"],
    },
    {
        "user_id": "lme_user_ms_03",
        "facts": [
            "我打算今年减肥",
            "目标是从 75 公斤降到 65 公斤",
            "已经开始每周三次健身房",
        ],
        "question": "用户的目标体重是多少",
        "expected_answer": "65 公斤",
        "must_contain": ["65"],
    },
    {
        "user_id": "lme_user_ms_04",
        "facts": [
            "我打算考研",
            "目标是清华的计算机系",
            "今年 12 月就考试了",
        ],
        "question": "用户考研的目标学校是哪所",
        "expected_answer": "清华",
        "must_contain": ["清华"],
    },
    {
        "user_id": "lme_user_ms_05",
        "facts": [
            "我最近搬到了北京",
            "租了海淀区的一个一居室",
            "离地铁 4 号线很近",
        ],
        "question": "用户租的房子在哪个区",
        "expected_answer": "海淀",
        "must_contain": ["海淀"],
    },
    {
        "user_id": "lme_user_ms_06",
        "facts": [
            "我家有两个孩子",
            "大的叫小宇, 7 岁了上小学一年级",
            "小的叫小雯, 才 3 岁",
        ],
        "question": "用户两个孩子的名字分别是什么",
        "expected_answer": "小宇 小雯",
        "must_contain": ["小宇"],
    },
    {
        "user_id": "lme_user_ms_07",
        "facts": [
            "我下个月要结婚了",
            "婚礼定在三亚的海边",
            "婚纱已经选好了, 是 Vera Wang 的",
        ],
        "question": "用户的婚礼在哪里举办",
        "expected_answer": "三亚",
        "must_contain": ["三亚"],
    },
    {
        "user_id": "lme_user_ms_08",
        "facts": [
            "我打算自己装一台台式机",
            "CPU 选的是 AMD 7950X",
            "显卡用的是 4090",
        ],
        "question": "用户打算配什么型号的显卡",
        "expected_answer": "4090",
        "must_contain": ["4090"],
    },
    {
        "user_id": "lme_user_ms_09",
        "facts": [
            "我最近在创业",
            "做的是 AI 教育方向的产品",
            "团队目前 5 个人, 都是技术",
        ],
        "question": "用户创业的方向是什么",
        "expected_answer": "AI 教育",
        "must_contain": ["AI"],
    },
    {
        "user_id": "lme_user_ms_10",
        "facts": [
            "我家在上海有套房",
            "已经付完首付了, 总价 800 万",
            "贷款 300 万, 月供 1.7 万",
        ],
        "question": "用户房子的总价是多少",
        "expected_answer": "800 万",
        "must_contain": ["800"],
    },
]


# ╔══════════════════════════════════════════════════════════════════════╗
# ║   Temporal (TR) — 时间敏感问题                                        ║
# ╚══════════════════════════════════════════════════════════════════════╝

TR_CASES = [
    {
        "user_id": "lme_user_tr_01",
        "facts": ["我每周三晚上 7 点会去打羽毛球", "通常打 2 小时"],
        "question": "用户每周固定哪天打羽毛球",
        "expected_answer": "周三",
        "must_contain": ["周三"],
    },
    {
        "user_id": "lme_user_tr_02",
        "facts": ["我每年 11 月体检", "今年特别加了肠胃镜"],
        "question": "用户什么月份体检",
        "expected_answer": "11 月",
        "must_contain": ["11"],
    },
    {
        "user_id": "lme_user_tr_03",
        "facts": ["我上次出国是 2024 年 3 月去的泰国", "下次准备明年春天去欧洲"],
        "question": "用户上次出国去了哪里",
        "expected_answer": "泰国",
        "must_contain": ["泰国"],
    },
    {
        "user_id": "lme_user_tr_04",
        "facts": ["我每天早上 6 点起床跑 5 公里", "已经坚持 3 年了"],
        "question": "用户坚持晨跑多少年了",
        "expected_answer": "3 年",
        "must_contain": ["3 年"],
    },
    {
        "user_id": "lme_user_tr_05",
        "facts": ["我今年春节是在老家武汉过的", "陪了爸妈一周"],
        "question": "用户春节去了哪个城市",
        "expected_answer": "武汉",
        "must_contain": ["武汉"],
    },
]


# ╔══════════════════════════════════════════════════════════════════════╗
# ║   Knowledge Update (KU) — 信息更新, 测冲突仲裁能力                    ║
# ╚══════════════════════════════════════════════════════════════════════╝

KU_CASES = [
    {
        "user_id": "lme_user_ku_01",
        "old_fact": "我目前在腾讯做后端",
        "new_fact": "我跳槽到了字节, 现在做基础架构",
        "question": "用户目前在哪家公司",
        "expected_answer": "字节",
        "must_contain": ["字节"],
        "must_not_contain": ["腾讯"],
    },
    {
        "user_id": "lme_user_ku_02",
        "old_fact": "我女朋友叫小雪",
        "new_fact": "我们分手了, 现在的女朋友叫莉莉",
        "question": "用户现在的女朋友叫什么",
        "expected_answer": "莉莉",
        "must_contain": ["莉莉"],
        "must_not_contain": ["小雪"],
    },
    {
        "user_id": "lme_user_ku_03",
        "old_fact": "我的车是大众朗逸",
        "new_fact": "上个月换了车, 现在开特斯拉 Model Y",
        "question": "用户现在开什么车",
        "expected_answer": "特斯拉 Model Y",
        "must_contain": ["Model Y"],
        "must_not_contain": ["大众朗逸"],
    },
    {
        "user_id": "lme_user_ku_04",
        "old_fact": "我体重 80 公斤",
        "new_fact": "经过半年健身, 现在 70 公斤了",
        "question": "用户当前体重是多少",
        "expected_answer": "70 公斤",
        "must_contain": ["70"],
        "must_not_contain": ["80 公斤"],
    },
    {
        "user_id": "lme_user_ku_05",
        "old_fact": "我手机是 iPhone 14",
        "new_fact": "我换手机了, 用的是 iPhone 16 Pro",
        "question": "用户当前用什么手机",
        "expected_answer": "iPhone 16 Pro",
        "must_contain": ["iPhone 16"],
        "must_not_contain": ["iPhone 14"],
    },
]


# ╔══════════════════════════════════════════════════════════════════════╗
# ║                    生成数据集                                         ║
# ╚══════════════════════════════════════════════════════════════════════╝


def build_ss(case: dict, idx: int) -> dict:
    """SS: 关键 fact 夹在 distractor 中间."""
    sessions = _mk_distractor_session(3, start=idx)
    sessions.append({"role": "user", "content": case["fact"]})
    sessions.append({"role": "ai", "content": "好的, 记住了"})
    sessions.extend(_mk_distractor_session(3, start=idx + 5))
    return {
        "question_id": f"cn_ss_{idx:02d}",
        "subtype": "single_session",
        "user_id": case["user_id"],
        "sessions": sessions,
        "question": case["question"],
        "expected_answer": case["expected_answer"],
        "must_contain": case["must_contain"],
        "must_not_contain": [],
    }


def build_ms(case: dict, idx: int) -> dict:
    """MS: 多个 fact 分布在不同对话片段, 中间穿插 distractor."""
    sessions: list[dict] = []
    for i, fact in enumerate(case["facts"]):
        sessions.extend(_mk_distractor_session(2, start=idx * 3 + i * 2))
        sessions.append({"role": "user", "content": fact})
        sessions.append({"role": "ai", "content": "了解"})
    sessions.extend(_mk_distractor_session(2, start=idx * 5 + 10))
    return {
        "question_id": f"cn_ms_{idx:02d}",
        "subtype": "multi_session",
        "user_id": case["user_id"],
        "sessions": sessions,
        "question": case["question"],
        "expected_answer": case["expected_answer"],
        "must_contain": case["must_contain"],
        "must_not_contain": [],
    }


def build_tr(case: dict, idx: int) -> dict:
    """TR: 时间相关 fact + distractor."""
    sessions = _mk_distractor_session(2, start=idx)
    for fact in case["facts"]:
        sessions.append({"role": "user", "content": fact})
        sessions.append({"role": "ai", "content": "嗯"})
    sessions.extend(_mk_distractor_session(2, start=idx + 5))
    return {
        "question_id": f"cn_tr_{idx:02d}",
        "subtype": "temporal_reasoning",
        "user_id": case["user_id"],
        "sessions": sessions,
        "question": case["question"],
        "expected_answer": case["expected_answer"],
        "must_contain": case["must_contain"],
        "must_not_contain": [],
    }


def build_ku(case: dict, idx: int) -> dict:
    """KU: 先说旧事实, distractor 隔开, 再更新为新事实."""
    sessions: list[dict] = []
    sessions.append({"role": "user", "content": case["old_fact"]})
    sessions.append({"role": "ai", "content": "好的"})
    sessions.extend(_mk_distractor_session(3, start=idx + 3))
    sessions.append({"role": "user", "content": case["new_fact"]})
    sessions.append({"role": "ai", "content": "明白了, 已经更新"})
    sessions.extend(_mk_distractor_session(2, start=idx + 7))
    return {
        "question_id": f"cn_ku_{idx:02d}",
        "subtype": "knowledge_update",
        "user_id": case["user_id"],
        "sessions": sessions,
        "question": case["question"],
        "expected_answer": case["expected_answer"],
        "must_contain": case["must_contain"],
        "must_not_contain": case["must_not_contain"],
    }


def build_all() -> list[dict]:
    dataset: list[dict] = []
    for i, c in enumerate(SS_CASES, 1):
        dataset.append(build_ss(c, i))
    for i, c in enumerate(MS_CASES, 1):
        dataset.append(build_ms(c, i))
    for i, c in enumerate(TR_CASES, 1):
        dataset.append(build_tr(c, i))
    for i, c in enumerate(KU_CASES, 1):
        dataset.append(build_ku(c, i))
    return dataset


def main() -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = build_all()
    with open(_OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)
    subtype_counts: dict[str, int] = {}
    for item in dataset:
        subtype_counts[item["subtype"]] = subtype_counts.get(item["subtype"], 0) + 1
    print(f"已生成 {_OUT_FILE} ({len(dataset)} 题):")
    for k, v in subtype_counts.items():
        print(f"  {k}: {v} 题")


if __name__ == "__main__":
    main()
