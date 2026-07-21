"""TICKET-0 게이트 — Qwen3-32B-FP8 자율 tool choice 실측.

도구 4종(TICKET-5 후보)을 주고 tool_choice="auto" 로 시나리오 10종 × N회를
돌려, (1) 맞는 도구를 고르는가 (2) 안 쓸 때 안 쓰는가 (3) 인자 JSON 이
유효한가를 측정한다. 게이트 미달이면 폴백(구조화 출력 강제)으로 방향 확정.

사용:  python scripts/exp_tool_choice.py [--trials 3] [--thinking] [--out PATH]
전제:  LLM_API_KEY 환경변수 (check_npu_endpoint.sh 참고)
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

GATE_TOOL_ACC = 0.80    # 도구 시나리오 정확도
GATE_SPURIOUS = 0.20    # 무도구 시나리오 오발동률 상한
GATE_JSON_OK = 1.00     # 인자 JSON 유효율

TOOLS = [
    {"type": "function", "function": {
        "name": "brief",
        "description": "의뢰자의 도메인 용어·브랜드·제도·사실을 브리핑 자료에서 검색한다. 응답자가 언급한 용어를 모르거나 의뢰자 회사 고유의 것일 때 사용.",
        "parameters": {"type": "object", "properties": {"term": {"type": "string", "description": "검색할 용어"}}, "required": ["term"]}}},
    {"type": "function", "function": {
        "name": "playbook",
        "description": "정성조사 기법 사전(5 Why, 래더링, CIT, 모순 확인 등)에서 지금 상황에 맞는 질문 기법을 찾는다. 응답이 겉돌거나 모순되거나 파고들기 어려울 때 사용.",
        "parameters": {"type": "object", "properties": {"situation": {"type": "string", "description": "현재 인터뷰 상황 요약"}}, "required": ["situation"]}}},
    {"type": "function", "function": {
        "name": "ledger_report",
        "description": "커버리지 원장 요약 — 남은 목표, 답이 빈약한 문항, 회수 안 한 떡밥 목록을 확인한다.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "pace",
        "description": "남은 턴 예산과 페이스 경고를 확인한다. 인터뷰를 접을지 더 갈지 판단할 때 사용.",
        "parameters": {"type": "object", "properties": {}}}},
]

SYSTEM = (
    "당신은 정성조사 인터뷰 진행자다. 연구 주제에 맞춰 다음 질문 한 문장을 만든다.\n"
    "필요하면 도구를 먼저 호출해 정보를 얻고, 필요 없으면 도구 없이 바로 질문을 출력한다.\n"
    "모르는 용어를 아는 척하지 말 것. 질문은 한국어 존댓말 한 문장."
)

# ok = 허용되는 '호출 도구 이름 집합' 목록. frozenset() 은 무도구가 정답.
# arg_must = brief 호출 시 term 인자에 반드시 포함돼야 하는 문자열.
NONE_IDS = {"smalltalk", "clear-story", "common-term-trap"}   # 무도구가 정답인 3종
SCENARIOS = [
    {"id": "brand-unknown", "ok": [{"brief"}], "arg_must": "배민클럽",
     "user": "연구 주제: 배달앱 전환 요인\n[응답자] 요즘은 배민클럽 때문에 다른 앱으로 갈아탔어요."},
    {"id": "client-jargon", "ok": [{"brief"}], "arg_must": "멤버스딜",
     "user": "연구 주제: 편의점 앱 사용 경험\n[응답자] 저희 동네 점포는 멤버스딜 들어오고 나서 확 달라졌어요."},
    {"id": "shallow-answer", "ok": [{"playbook"}],
     "user": "연구 주제: 구독 해지 이유\n[응답자] (세 번 연속 같은 답) 그냥요. 별 이유 없어요. 그냥 그랬어요."},
    {"id": "contradiction", "ok": [{"playbook"}, frozenset()],
     "user": "연구 주제: 장보기 습관\n[3턴 전 응답자] 가격은 잘 안 봐요.\n[방금 응답자] 무조건 최저가만 골라서 사요."},
    {"id": "coverage-check", "ok": [{"ledger_report"}],
     "user": "연구 주제: 재택근무 경험\n[상황] 진행 15분 경과. 어떤 문항이 아직 빈약한지 확인하고 다음 질문을 정해야 한다."},
    {"id": "pace-check", "ok": [{"pace"}],
     "user": "연구 주제: 중고거래 경험\n[상황] 응답자가 말이 길다. 남은 턴 예산을 보고 이 주제를 더 팔지 접을지 정해야 한다."},
    {"id": "smalltalk", "ok": [frozenset()],
     "user": "연구 주제: 카페 이용 행태\n[응답자] 안녕하세요, 잘 부탁드립니다!"},
    {"id": "clear-story", "ok": [frozenset()],
     "user": "연구 주제: 온라인 쇼핑 반품 경험\n[응답자] 지난달에 산 신발이 작아서 반품했는데, 앱에서 버튼 몇 번 누르니까 다음날 기사님이 바로 가져가셨어요."},
    {"id": "multi-brief-pace", "ok": [{"brief", "pace"}, {"brief"}], "arg_must": "프로여관러",
     "user": "연구 주제: 숙박앱 이용 행태\n[상황] 진행 후반부, 남은 턴이 빠듯할 수 있다.\n[응답자] 저는 '프로여관러'라서 웬만한 건 다 시도해봤어요."},
    {"id": "common-term-trap", "ok": [frozenset()],
     "user": "연구 주제: 이커머스 배송 만족도\n[응답자] 쿠팡에서 로켓배송으로 시켰더니 다음날 새벽에 왔어요."},
]


def run(trials: int) -> dict:
    from api.services.llm_client import LLMClient

    cli = LLMClient()
    rows, lat = [], []
    for sc in SCENARIOS:
        for t in range(trials):
            t0 = time.perf_counter()
            out, usage = cli.chat(
                [{"role": "system", "content": SYSTEM}, {"role": "user", "content": sc["user"]}],
                tools=TOOLS, max_tokens=256,
            )
            dt = time.perf_counter() - t0
            lat.append(dt)
            called = {c.name for c in out.tool_calls}
            json_ok = all(c.arguments is not None for c in out.tool_calls)
            arg_ok = True
            if "brief" in called and sc.get("arg_must"):
                briefs = [c for c in out.tool_calls if c.name == "brief" and c.arguments]
                arg_ok = any(sc["arg_must"] in str(c.arguments.get("term", "")) for c in briefs)
            choice_ok = any(called == set(okset) for okset in sc["ok"])
            rows.append({
                "id": sc["id"], "trial": t + 1, "called": sorted(called) or ["-"],
                "expected": [sorted(s) or ["-"] for s in map(set, sc["ok"])],
                "choice_ok": choice_ok, "json_ok": json_ok, "arg_ok": arg_ok,
                "pass": choice_ok and json_ok and arg_ok,
                "latency_s": round(dt, 2), "tokens_out": usage.tokens_out,
                "content_head": out.content[:40].replace("\n", " "),
            })
            print(f"  {sc['id']:18s} #{t+1}  called={','.join(sorted(called)) or '-':28s}  "
                  f"{'PASS' if rows[-1]['pass'] else 'FAIL'}  {dt:.2f}s")
    none_rows = [r for r in rows if r["id"] in NONE_IDS]
    tool_rows = [r for r in rows if r["id"] not in NONE_IDS]
    acc = sum(r["pass"] for r in tool_rows) / len(tool_rows)
    spurious = sum(1 for r in none_rows if r["called"] != ["-"]) / len(none_rows)
    json_rate = sum(r["json_ok"] for r in rows) / len(rows)
    lat_sorted = sorted(lat)
    return {
        "rows": rows, "tool_acc": acc, "spurious": spurious, "json_rate": json_rate,
        "lat_mean": sum(lat) / len(lat), "lat_p95": lat_sorted[max(0, int(len(lat_sorted) * 0.95) - 1)],
        "gate": acc >= GATE_TOOL_ACC and spurious <= GATE_SPURIOUS and json_rate >= GATE_JSON_OK,
    }


def to_md(res: dict, trials: int, thinking: bool) -> str:
    L = [
        "# Qwen3 자율 tool choice 실측 (TICKET-0 게이트)", "",
        f"- 모델: furiosa-ai/Qwen3-32B-FP8 · thinking={'on' if thinking else 'off(프로덕션 설정)'} · 시나리오 10종 × {trials}회",
        f"- **게이트 판정: {'✅ 통과 — 자율 tool choice 채택' if res['gate'] else '❌ 미달 — 폴백(도구 선택 구조화 출력 강제) 채택'}**", "",
        "| 지표 | 결과 | 기준 |", "|---|---|---|",
        f"| 도구 시나리오 정확도 | {res['tool_acc']:.0%} | ≥ {GATE_TOOL_ACC:.0%} |",
        f"| 무도구 오발동률 | {res['spurious']:.0%} | ≤ {GATE_SPURIOUS:.0%} |",
        f"| 인자 JSON 유효율 | {res['json_rate']:.0%} | = 100% |",
        f"| 지연 mean / p95 | {res['lat_mean']:.2f}s / {res['lat_p95']:.2f}s | (참고) |",
        "", "## 시행 상세", "",
        "| 시나리오 | 회 | 호출 | 기대 | 판정 | 지연 | 응답 앞부분 |", "|---|---|---|---|---|---|---|",
    ]
    for r in res["rows"]:
        L.append(f"| {r['id']} | {r['trial']} | {','.join(r['called'])} | "
                 f"{' 또는 '.join(','.join(e) for e in r['expected'])} | "
                 f"{'PASS' if r['pass'] else 'FAIL'} | {r['latency_s']}s | {r['content_head']} |")
    L += ["", "## 임베딩 (Task 2 Step 5 결과 — 수동 기입)", "",
          "- 기본 차원: (기입)", "- dimensions=1024 지원 여부: (기입) → §11 결정 재료", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--thinking", action="store_true", help="enable_thinking=True 비교 실행")
    ap.add_argument("--out", default="docs/experiments/2026-07-21-qwen3-tool-choice.md")
    a = ap.parse_args()
    if not os.environ.get("LLM_API_KEY"):
        print("LLM_API_KEY 가 필요합니다 (check_npu_endpoint.sh 참고)")
        return 2
    os.environ["LLM_DISABLE_THINKING"] = "0" if a.thinking else "1"
    from api.config import get_settings
    get_settings.cache_clear()

    res = run(a.trials)
    md = to_md(res, a.trials, a.thinking)
    out = Path(a.out if not a.thinking else a.out.replace(".md", "-thinking.md"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(f"\n결과 저장: {out}")
    print(f"게이트: {'통과' if res['gate'] else '미달 — 폴백 확정'}")
    return 0 if res["gate"] else 1


if __name__ == "__main__":
    sys.exit(main())
