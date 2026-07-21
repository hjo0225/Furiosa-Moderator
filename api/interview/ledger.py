"""원장 갱신 — 순수 함수. T2 는 listen 노드 내에서 호출, T4 에 슬로우패스로 이사."""
from __future__ import annotations

from .state import CoverageEntry

_ORDER = ["pending", "touched", "satisfied", "saturated"]


def update_ledger(
    ledger: dict[str, CoverageEntry], qid: str, coverage: str, facts: list[str], hooks: list[str]
) -> dict[str, CoverageEntry]:
    """직전 문항(qid)의 취재 결과를 반영한 새 원장을 돌려준다(원본 불변).

    - facts/hooks 는 중복 없이 누적
    - status 는 후퇴 금지 (satisfied 를 touched 로 강등하지 않는다)
    """
    new = {
        k: CoverageEntry(status=e["status"], facts=list(e["facts"]), hooks=list(e["hooks"]))
        for k, e in ledger.items()
    }
    if not qid or qid not in new:
        return new
    e = new[qid]
    e["facts"] += [f for f in facts if f and f not in e["facts"]]
    e["hooks"] += [h for h in hooks if h and h not in e["hooks"]]
    if coverage in _ORDER and _ORDER.index(coverage) > _ORDER.index(e["status"]):
        e["status"] = coverage
    return new
