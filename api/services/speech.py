"""STT/TTS — Google Cloud Speech-to-Text v2 + Text-to-Speech.

_reference/speech_router.py 에서 건진 3가지를 그대로 반영했다:

  1. `(전사, 성공여부)` 튜플 반환 — 빈 transcript 만으로는 '무음(성공)'과 '엔진실패'를
     구별할 수 없다. 원본 운영에서 중국어 STT 400 이 한 달간 조용히 저장된 실장애가 있었다.
     **transcribe 200 ≠ 성공.** 엔진을 바꿔도 유효한 교훈이라 계약을 유지한다.
  2. `_spellfix()` — STT 맞춤법 보정. "의미·어휘 변경 금지, 표기만 교정".
     엔진 무관이라 그대로 재사용한다.
  3. 오디오 크기·MIME 가드.
"""
from __future__ import annotations

import logging

from ..config import get_settings
from .llm_client import LLMError, get_llm

log = logging.getLogger(__name__)

_ALLOWED_MIME = (
    "audio/webm",
    "audio/ogg",
    "audio/mp4",
    "audio/mpeg",
    "audio/wav",
    "audio/x-wav",
    "audio/aac",
)

_SPELLFIX_SYSTEM = (
    "당신은 음성인식(STT) 결과의 표기를 교정합니다.\n"
    "**의미와 어휘를 바꾸지 마세요.** 맞춤법·띄어쓰기·문장부호 표기만 교정합니다.\n"
    "- 단어를 다른 단어로 바꾸지 마세요. 내용을 추가·삭제하지 마세요.\n"
    "- 구어체 말투는 그대로 둡니다.\n"
    "- 교정할 게 없으면 입력을 그대로 돌려주세요.\n"
    "- 교정된 문장만 출력하세요. 설명 금지."
)


def guard_audio(content_type: str | None, size: int) -> str | None:
    """오디오 가드 — 문제가 있으면 사유 문자열, 없으면 None."""
    s = get_settings()
    if size <= 0:
        return "빈 오디오입니다."
    if size > s.max_audio_bytes:
        return f"오디오가 너무 큽니다({size} bytes). 최대 {s.max_audio_bytes} bytes."
    if content_type:
        base = content_type.split(";")[0].strip().lower()
        if base and not base.startswith("audio/"):
            return f"지원하지 않는 형식입니다: {base}"
    return None


def spellfix(text: str) -> str:
    """STT 표기 교정. 실패하면 원문을 그대로 돌려준다(교정은 부가기능이다)."""
    t = (text or "").strip()
    if len(t) < 2:
        return t
    try:
        out, _ = get_llm().text(_SPELLFIX_SYSTEM, t, max_tokens=len(t) * 2 + 100)
    except LLMError as e:
        log.warning("spellfix 실패, 원문 사용: %s", e)
        return t
    fixed = (out or "").strip()
    # 교정본이 원문 대비 지나치게 짧아지면 모델이 요약해버린 것 — 원문을 쓴다.
    if not fixed or len(fixed) < len(t) * 0.5:
        return t
    return fixed


# STT v2 는 BCP-47 전체 코드만 받는다. 프런트는 인터뷰 언어를 "ko"/"en" 으로 넘기므로
# 여기서 정규화한다. 클라이언트만 고치면 다른 호출부에서 같은 실수가 또 난다.
_LANG_ALIAS = {"ko": "ko-KR", "en": "en-US", "ja": "ja-JP", "zh": "cmn-Hans-CN"}


def normalize_lang(lang: str | None) -> str:
    s = get_settings()
    v = (lang or "").strip()
    if not v:
        return s.stt_language
    return _LANG_ALIAS.get(v.lower(), v)


def transcribe(audio: bytes, *, mime: str = "audio/webm", lang: str | None = None) -> tuple[str, bool]:
    """음성 → 텍스트. 반환 (전사, 성공여부).

    성공여부가 False 면 엔진이 실패한 것이다. 빈 전사와 반드시 구별해서 다뤄야 한다.

    모델은 "long" 을 쓴다. "short" 는 실측에서 두 문장짜리 발화의 **뒷문장을 조용히 버렸다**
    ("배달비가 비싸서 부담됩니다. 포장하러 갑니다." → 앞 문장만 반환). 인터뷰 답변은
    한 문장으로 끝나지 않으므로 short 는 쓸 수 없다. 에러가 아니라 데이터가 사라지는 쪽이라
    더 위험하다.

    위치는 "global" 이다 — asia-northeast3 에는 STT v2 엔드포인트가 없다.
    """
    from google.cloud import speech_v2
    from google.cloud.speech_v2.types import cloud_speech

    s = get_settings()
    if not s.gcp_project:
        log.error("GCP_PROJECT 미설정 — STT 불가")
        return "", False

    try:
        client = speech_v2.SpeechClient()
        config = cloud_speech.RecognitionConfig(
            auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
            language_codes=[normalize_lang(lang)],
            model="long",
            features=cloud_speech.RecognitionFeatures(enable_automatic_punctuation=True),
        )
        req = cloud_speech.RecognizeRequest(
            recognizer=f"projects/{s.gcp_project}/locations/global/recognizers/_",
            config=config,
            content=audio,
        )
        resp = client.recognize(request=req)
    except Exception as e:  # 엔진 실패는 반드시 False 로 올린다
        log.exception("STT 실패: %s", e)
        return "", False

    parts = [
        r.alternatives[0].transcript
        for r in resp.results
        if r.alternatives and r.alternatives[0].transcript
    ]
    return " ".join(parts).strip(), True


def synthesize(text: str, *, voice: str | None = None) -> bytes:
    """텍스트 → MP3 바이트."""
    from google.cloud import texttospeech

    s = get_settings()
    client = texttospeech.TextToSpeechClient()
    v = voice or s.tts_voice
    lang_code = "-".join(v.split("-")[:2]) if "-" in v else "ko-KR"
    resp = client.synthesize_speech(
        input=texttospeech.SynthesisInput(text=text),
        voice=texttospeech.VoiceSelectionParams(language_code=lang_code, name=v),
        audio_config=texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=1.05,  # 대화 체감 속도 — 기본값은 인터뷰에 조금 느리다
        ),
    )
    return resp.audio_content


def list_voices(language_code: str = "ko-KR") -> list[dict]:
    from google.cloud import texttospeech

    client = texttospeech.TextToSpeechClient()
    resp = client.list_voices(language_code=language_code)
    return [
        {"name": v.name, "label": f"{v.name} ({v.ssml_gender.name.lower()})"}
        for v in resp.voices
    ]
