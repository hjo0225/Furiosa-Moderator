"""ledger_report — 원장 요약 (결정론). 남은 goal·빈약 문항·미회수 떡밥."""
from __future__ import annotations


def ledger_report(guide: dict, ledger: dict, qid: str = "") -> str:
    qs = {q["id"]: q for q in guide.get("questions", []) if q.get("id")}
    if qid and qid in qs:
        e = ledger.get(qid, {})
        facts = "\n".join(f"  - {f}" for f in e.get("facts", [])) or "  (없음)"
        hooks = "\n".join(f"  - {h}" for h in e.get("hooks", [])) or "  (없음)"
        return (f"[{qid} 취재 상세] {qs[qid]['text']} (알아낼 것: {qs[qid].get('goal', '')})\n"
                f" 알아낸 사실:\n{facts}\n 미회수 떡밥:\n{hooks}")
    pending = [f"- {i}: {q['text']}" for i, q in qs.items() if ledger.get(i, {}).get("status") == "pending"]
    thin, hooks_left = [], []
    for i, q in qs.items():
        e = ledger.get(i, {})
        if e.get("status") == "touched":
            thin.append(f"- {i}: {q['text']} (사실 {len(e.get('facts', []))}건)")
        hooks_left += [f"- ({i}) {h}" for h in e.get("hooks", [])]
    return ("[남은 goal]\n" + ("\n".join(pending) or "(없음)")
            + "\n[답이 얕은 문항]\n" + ("\n".join(thin) or "(없음)")
            + "\n[미회수 떡밥]\n" + ("\n".join(hooks_left) or "(없음)"))
