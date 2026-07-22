"""업로드 자료 → 텍스트 추출 (가이드 생성 프롬프트 주입용).

검색(RAG)이 아니라 통째 주입(b1)이다. 인터뷰 중 도메인 검색(brief)은 별개 작업.
"""
from __future__ import annotations

import io

MATERIAL_CHAR_CAP = 8000
# 이보다 길면 통째 주입 대신 LLM 으로 요약한다(자르면 뒷부분 도메인 맥락이 통째로 사라지므로).
SUMMARIZE_THRESHOLD = 8000
# 요약본 목표 길이(대략). 프롬프트 지시용 — 정확한 상한은 cap() 이 최종 보장한다.
SUMMARY_TARGET_CHARS = 2000
_TEXT_EXT = (".txt", ".md")


class MaterialError(ValueError):
    """추출 실패 — 라우터가 400 으로 변환한다."""


def extract_text(filename: str, raw: bytes) -> str:
    name = (filename or "").lower()
    if name.endswith(_TEXT_EXT):
        return _decode(raw)
    if name.endswith(".pdf"):
        return _extract_pdf(raw)
    raise MaterialError(f"지원하지 않는 형식입니다(.txt/.md/.pdf): {filename}")


def _decode(raw: bytes) -> str:
    for enc in ("utf-8", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise MaterialError("텍스트 인코딩을 인식할 수 없습니다(UTF-8/CP949).")


def _extract_pdf(raw: bytes) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(raw))
        # 스캔 PDF 는 텍스트 레이어가 없어 각 페이지가 "" 를 반환한다 — 에러가 아니다.
        pages = [(p.extract_text() or "") for p in reader.pages]
    except Exception as e:  # noqa: BLE001 — pypdf 는 다양한 예외를 던진다(깨진 PDF)
        raise MaterialError(f"PDF 를 읽을 수 없습니다: {e}") from e
    return "\n".join(pages).strip()


def cap(text: str) -> tuple[str, bool]:
    truncated = len(text) > MATERIAL_CHAR_CAP
    return text[:MATERIAL_CHAR_CAP], truncated


_ANGLE_LABELS = {"현상": "현상·실태", "원인": "원인·동인", "활용": "활용·응용"}


def summarize_slot(texts: list[str]) -> str:
    """슬롯 자료들을 하나의 요약으로. 빈 입력이면 ''. LLM 실패는 호출부가 처리."""
    joined = "\n\n".join(t for t in texts if t and t.strip())
    if not joined:
        return ""
    from .llm_client import get_llm
    from ..prompts.material import MATERIAL_SUMMARY_SYSTEM, material_summary_user

    out, _ = get_llm().text(MATERIAL_SUMMARY_SYSTEM, material_summary_user(joined), max_tokens=2048)
    return out.strip()


def compose_guide_material(summaries: dict[str, str]) -> str:
    """슬롯 요약 3개 → 가이드 생성 프롬프트에 넣을 단일 문자열. 빈 슬롯은 생략.

    반환값은 guide_user(material=...) 로 넘어가 기존 [참고 자료] 인젝션 가드를 그대로 탄다.
    """
    blocks: list[str] = []
    for angle in ("현상", "원인", "활용"):
        s = (summaries.get(angle) or "").strip()
        if s:
            blocks.append(f"[{_ANGLE_LABELS[angle]}]\n{s}")
    return "\n\n".join(blocks)
