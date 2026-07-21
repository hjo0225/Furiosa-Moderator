"""업로드 자료 텍스트 추출 — 형식·인코딩·캡."""
from __future__ import annotations

import pytest

from api.services.material import MATERIAL_CHAR_CAP, MaterialError, cap, extract_text


def test_extract_txt_utf8():
    assert extract_text("brief.txt", "배민클럽".encode("utf-8")) == "배민클럽"


def test_extract_md_cp949_fallback():
    assert extract_text("brief.md", "한글자료".encode("cp949")) == "한글자료"


def test_extract_unknown_ext_raises():
    with pytest.raises(MaterialError):
        extract_text("data.bin", b"\x00\x01")


def test_extract_pdf_joins_pages(monkeypatch):
    class FakePage:
        def __init__(self, t):
            self._t = t

        def extract_text(self):
            return self._t

    class FakeReader:
        def __init__(self, *a, **k):
            self.pages = [FakePage("배민클럽 "), FakePage("구독 멤버십")]

    monkeypatch.setattr("pypdf.PdfReader", FakeReader)
    out = extract_text("brief.pdf", b"%PDF-1.4 fake")
    assert "배민클럽" in out and "구독 멤버십" in out


def test_extract_scanned_pdf_returns_empty(monkeypatch):
    class FakePage:
        def extract_text(self):
            return None

    class FakeReader:
        def __init__(self, *a, **k):
            self.pages = [FakePage()]

    monkeypatch.setattr("pypdf.PdfReader", FakeReader)
    assert extract_text("scan.pdf", b"%PDF") == ""


def test_cap_truncates_over_limit():
    text, truncated = cap("가" * (MATERIAL_CHAR_CAP + 100))
    assert len(text) == MATERIAL_CHAR_CAP
    assert truncated is True


def test_cap_keeps_short_text():
    text, truncated = cap("짧은 자료")
    assert text == "짧은 자료"
    assert truncated is False
