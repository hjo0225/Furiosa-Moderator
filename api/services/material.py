"""업로드 자료 → 텍스트 추출 (가이드 생성 프롬프트 주입용).

검색(RAG)이 아니라 통째 주입(b1)이다. 인터뷰 중 도메인 검색(brief)은 별개 작업.
"""
from __future__ import annotations

import io

MATERIAL_CHAR_CAP = 8000
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
        return "\n".join((p.extract_text() or "") for p in reader.pages).strip()
    except Exception as e:  # noqa: BLE001 — pypdf 는 다양한 예외를 던진다(깨진 PDF)
        raise MaterialError(f"PDF 를 읽을 수 없습니다: {e}") from e


def cap(text: str) -> tuple[str, bool]:
    truncated = len(text) > MATERIAL_CHAR_CAP
    return text[:MATERIAL_CHAR_CAP], truncated
