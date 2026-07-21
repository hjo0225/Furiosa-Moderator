"""TICKET-5 검증 — brief 검색 품질 (DB 없이 임베딩+코사인만). 전제: EMBED_API_KEY."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DOC = """배민클럽은 배달의민족의 구독형 멤버십으로, 월 구독료를 내면 배달비가 무료가 된다.

멤버스딜은 CU 편의점 앱의 회원 전용 특가 프로그램으로, 주 1회 대표 상품을 반값에 판다.

로켓와우는 쿠팡의 유료 멤버십으로 로켓배송 무료·쿠팡이츠 할인·쿠팡플레이를 묶었다.

우리 회사의 '번쩍배달'은 1.5km 이내 단건 배달을 15분 안에 보장하는 자체 서비스다.

포인트락은 자사 앱에서 적립 포인트를 7일간 잠갔다가 이자처럼 5%를 얹어 돌려주는 실험 기능이다."""

QUERIES = [
    ("배민클럽", "배민클럽"), ("멤버스딜", "멤버스딜"), ("로켓와우", "로켓와우"),
    ("번쩍배달", "번쩍배달"), ("포인트락이 뭐예요", "포인트락"),
    ("배달비 무료 구독", "배민클럽"),                       # 동의어 우회 검색
]


def cos(a, b):
    num = sum(x * y for x, y in zip(a, b))
    den = (sum(x * x for x in a) ** 0.5) * (sum(y * y for y in b) ** 0.5)
    return num / den if den else 0.0


def main() -> int:
    if not os.environ.get("EMBED_API_KEY"):
        print("EMBED_API_KEY 필요")
        return 2
    from api.briefing.pipeline import chunk_text
    from api.services.embeddings import embed_texts

    chunks = chunk_text(DOC)
    cvecs = embed_texts(chunks)
    qvecs = embed_texts([q for q, _ in QUERIES])
    ok = 0
    for (q, expect), qv in zip(QUERIES, qvecs):
        scored = sorted(((cos(qv, cv), c) for cv, c in zip(cvecs, chunks)), reverse=True)
        top_s, top_c = scored[0]
        hit = expect in top_c
        ok += hit
        print(f"  {'PASS' if hit else 'FAIL'}  {q:14s} top1={top_s:.3f}  2위와 격차 {top_s - scored[1][0]:+.3f}  {top_c[:30]}")
    print(f"\ntop-1 적중 {ok}/{len(QUERIES)} = {ok / len(QUERIES):.0%} (기대 >= 5/6)")
    return 0 if ok >= 5 else 1


if __name__ == "__main__":
    sys.exit(main())
