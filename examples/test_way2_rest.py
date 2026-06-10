"""方式 2 测试: REST API 调用

前提: 先启动 API server
    make api    # 或 uvicorn app.api.main:app --host 127.0.0.1 --port 8765

跑法:
    uv run python examples/test_way2_rest.py
"""

from __future__ import annotations

import json
import sys
import time

import httpx

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8765"
USER = "bob"


def pretty(label: str, obj) -> None:
    print(f"\n--- {label} ---")
    print(json.dumps(obj, ensure_ascii=False, indent=2)[:600])


def main() -> None:
    print("\n========== 方式 2: REST API 调用 ==========\n")

    with httpx.Client(base_url=BASE, timeout=120.0) as c:
        # ── 0. 健康检查 ──
        r = c.get("/health")
        print(f"[0] GET /health  → status={r.status_code}  {r.json()}")
        assert r.status_code == 200, "服务未启动?"

        # ── 1. 写 3 条记忆 ──
        for content, mtype in [
            ("我对花生过敏", "semantic"),
            ("我现在住在杭州滨江区, 在一家 AI 创业公司工作", "semantic"),
            ("昨晚跟朋友去吃了川菜火锅, 喝了两瓶啤酒", "episodic"),
        ]:
            r = c.post(
                "/v1/memories",
                json={"user_id": USER, "content": content, "type": mtype},
            )
            res = r.json()
            print(f"[1] POST /v1/memories  status={r.status_code}  "
                  f"id={res['memory_id'][:8]} type={res['routed_type']}  "
                  f"← '{content[:25]}'")

        # 等异步 episodic→semantic 抽取
        print("\n[2] sleep 8s 让后台 semantic 抽取跑完...")
        time.sleep(8)

        # ── 3. 召回 ──
        r = c.post("/v1/memories/search", json={
            "user_id": USER, "query": "用户的饮食限制和居住地", "top_k": 5,
        })
        data = r.json()
        print(f"\n[3] POST /v1/memories/search  status={r.status_code}  "
              f"latency={data['latency_ms']}ms")
        for item in data["results"]:
            sig = item["signals"]
            print(f"    [{item['rank']}] {item['record']['type']:10}  "
                  f"score={sig['final_score']:.3f}  → {item['record']['content'][:45]}")

        # ── 4. 用户画像 ──
        r = c.get(f"/v1/users/{USER}/profile", params={"auto_refresh": True})
        pretty("[4] GET /v1/users/bob/profile", r.json())

        # ── 5. KG 实体 ──
        r = c.get(f"/v1/users/{USER}/entities/user")
        pretty("[5] GET /v1/users/bob/entities/user", r.json())

        # ── 6. 仲裁审计 ──
        r = c.get(f"/admin/arbitrations/{USER}")
        print(f"\n[6] GET /admin/arbitrations/bob  {r.json()['count']} 条审计记录")

        # ── 7. Metrics ──
        r = c.get("/metrics")
        m = r.json()
        print(f"\n[7] GET /metrics")
        print(f"    counters: {m['counters']}")
        if "recall.total.latency" in m["histograms"]:
            h = m["histograms"]["recall.total.latency"]
            print(f"    recall latency: P50={h['p50_ms']}ms  P95={h['p95_ms']}ms  count={h['count']}")

        # ── 8. Swagger 文档可访问 ──
        r = c.get("/docs")
        print(f"\n[8] GET /docs  status={r.status_code}  "
              f"(Swagger UI 可在浏览器打开 {BASE}/docs)")

    print("\n[OK] 方式 2 测试通过 — REST API 全部接口可用\n")


if __name__ == "__main__":
    main()
