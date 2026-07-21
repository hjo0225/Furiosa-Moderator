"""음성 API — STT/TTS.

`transcribe` 는 엔진 실패를 200 으로 감추지 않는다. `_reference/speech_router.py` 의
교훈: 빈 transcript 만으로는 무음(성공)과 엔진실패를 구별할 수 없어, 중국어 STT 400 이
한 달간 조용히 저장된 실장애가 있었다. ok 플래그를 응답에 실어 프런트가 구별하게 한다.
"""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from ..services import speech

router = APIRouter(prefix="/api/speech", tags=["speech"])


class TranscribeOut(BaseModel):
    text: str
    ok: bool


class SynthesizeIn(BaseModel):
    text: str
    voice: str = ""


@router.post("/transcribe", response_model=TranscribeOut)
async def transcribe(
    file: UploadFile = File(...),
    lang: str = Form("ko-KR"),
    project_id: str = Form(""),
) -> TranscribeOut:
    audio = await file.read()
    if (reason := speech.guard_audio(file.content_type, len(audio))):
        raise HTTPException(400, reason)

    # 이 조사에서 나올 어휘를 STT 에 넘긴다. 주제를 아는 건 우리뿐이고 STT 는 모른다.
    # project_id 가 없으면 힌트 없이 진행한다 — 인식을 막을 이유는 없다.
    vocabulary: list[str] = []
    if project_id:
        guide = store.get_guide(project_id)
        if guide:
            vocabulary = list(guide.vocabulary)

    text, ok = speech.transcribe(
        audio, mime=file.content_type or "audio/webm", lang=lang, vocabulary=vocabulary
    )
    if not ok:
        # 엔진 실패는 502 로 올린다. 프런트의 '전사 2회 실패 → 텍스트 폴백' 이 여기에 걸린다.
        raise HTTPException(502, "음성 인식에 실패했습니다. 텍스트로 입력해 주세요.")
    return TranscribeOut(text=speech.spellfix(text) if text else "", ok=True)


@router.post("/synthesize")
def synthesize(body: SynthesizeIn) -> Response:
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(400, "합성할 텍스트가 없습니다.")
    if len(text) > 2000:
        raise HTTPException(400, "텍스트가 너무 깁니다(최대 2000자).")
    audio = speech.synthesize(text, voice=body.voice or None)
    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/voices")
def voices(language_code: str = "ko-KR") -> dict:
    return {"voices": speech.list_voices(language_code)}
