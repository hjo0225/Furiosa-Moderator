"""솔루션 2 — 음성(TTS/STT) 엔드포인트.

구버전 mindlens_backend views/speech(TTS)·views/stt(STT) 이식. 단, 실시간 WebSocket
스트리밍 대신 **녹음 → 업로드 → 일괄 전사**(단순·견고·테스트 가능). 음성 답변은
오디오를 GCS 에 저장하고 텍스트로 받아쓴다.

graceful — Google Cloud 자격증명/버킷 미설정 시:
- voices: 빈 목록(프론트가 읽어주기 비활성)
- synthesize: 503(오디오가 실제로 필요)
- transcribe: 200 + 빈 transcript(응답자가 직접 타이핑 가능, 흐름 비차단)
"""
import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from ..config import get_settings
from ..schemas.speech import SynthesizeIn, TranscribeOut, VoiceOut
from .auth import rate_limit_respondent, verify_respondent

logger = logging.getLogger(__name__)

# STT/TTS — 응답자당 분당 레이트리밋(감사 #8, 비용 방지). 라우터 레벨.
router = APIRouter(prefix="/speech", tags=["speech"], dependencies=[Depends(rate_limit_respondent("speech"))])

_MAX_AUDIO_BYTES = 15 * 1024 * 1024  # 음성 답변 15MB
_AUDIO_EXT = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
}


def _tts_client():
    """TextToSpeechClient — 자격증명 미설정/라이브러리 부재 시 None(graceful)."""
    try:
        from google.cloud import texttospeech

        return texttospeech.TextToSpeechClient()
    except Exception as exc:  # noqa: BLE001 — 자격증명/라이브러리 문제도 여기서 조용히 삼켜지던 지점
        logger.warning("[TTS] client init 실패: %s", str(exc)[:200])
        return None


@router.get("/voices", response_model=list[VoiceOut])
def list_voices(
    language_code: str = "ko-KR",
    _claims: dict = Depends(verify_respondent),
) -> list[VoiceOut]:
    """언어별 TTS 음성 목록 — 미설정 시 빈 목록(읽어주기 비활성)."""
    client = _tts_client()
    if client is None:
        return []
    from google.cloud import texttospeech

    try:
        resp = client.list_voices(language_code=language_code)
    except Exception as exc:  # noqa: BLE001 — 권한/설정 실패가 빈 목록으로 삼켜지던 지점(읽어주기 무음 비활성)
        logger.warning("[TTS] list_voices 실패 lang=%s: %s", language_code, str(exc)[:200])
        return []
    out: list[VoiceOut] = []
    for v in resp.voices:
        out.append(
            VoiceOut(
                name=v.name,
                language_code=v.language_codes[0] if v.language_codes else "",
                gender=texttospeech.SsmlVoiceGender(v.ssml_gender).name,
            )
        )
    return out


@router.post("/synthesize")
def synthesize(
    body: SynthesizeIn,
    _claims: dict = Depends(verify_respondent),
) -> Response:
    """텍스트 → mp3 음성. 미설정/실패 시 503(오디오가 실제로 필요해 폴백 무의미)."""
    client = _tts_client()
    if client is None:
        raise HTTPException(status_code=503, detail="음성 합성이 설정되지 않았어요.")
    from google.cloud import texttospeech

    voice_kwargs = {"language_code": body.language_code}
    if body.voice_name:
        voice_kwargs["name"] = body.voice_name
    try:
        resp = client.synthesize_speech(
            input=texttospeech.SynthesisInput(text=body.text),
            voice=texttospeech.VoiceSelectionParams(**voice_kwargs),
            audio_config=texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=body.speaking_rate,
                volume_gain_db=body.volume_gain_db,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail="음성 합성에 실패했어요.") from exc
    return Response(content=resp.audio_content, media_type="audio/mpeg")


# 전사 보정(T-STT-SPELLFIX) — 맞춤법·띄어쓰기만. 의미·어휘를 바꾸면 응답 데이터 오염이라 금지.
_SPELLFIX_SYSTEM = """
너는 음성 전사(STT) 텍스트 교정기다. 입력된 전사 텍스트의 맞춤법과 띄어쓰기만 고쳐 돌려준다.

원칙:
- 의미·어휘·문장을 추가/삭제/변경하지 않는다 — 표기 교정만 한다.
- 원문 언어를 그대로 유지한다(번역 금지).
- 교정된 텍스트만 출력한다(설명·따옴표·마크다운 금지).
""".strip()


def _spellfix(transcript: str) -> str:
    """전사 텍스트 경량 LLM(haiku 급) 맞춤법·띄어쓰기 보정 — best-effort.

    키 미설정/호출 실패/빈 결과는 전부 원문 반환(보정 실패가 전사를 죽이면 안 된다).
    빈 전사는 LLM 을 호출하지 않는다(비용 0)."""
    if not transcript.strip():
        return transcript
    s = get_settings()
    if not s.anthropic_api_key:
        return transcript
    try:
        from ..services.llm_client import get_llm

        fixed, _usage = get_llm().text(
            _SPELLFIX_SYSTEM, transcript, max_tokens=2000, model=s.panel_model
        )
        return fixed.strip() or transcript
    except Exception as exc:  # noqa: BLE001 — 보정은 부가 기능. 실패 원인만 로깅하고 원문으로.
        logger.warning("[STT] 맞춤법 보정 실패 — 원문 반환: %s", str(exc)[:200])
        return transcript


def _recognize_raw(content: bytes, language_code: str) -> str:
    """오디오 → 텍스트(Speech v2, 자동 디코딩). **실패하면 예외를 던진다** — 삼키지 않는다.

    [T-STT-FAILURE-SILENT] 예전엔 여기서 모든 예외를 삼키고 "" 를 반환해, STT 엔진 실패가
    HTTP 200 으로 나갔다. 프론트는 `!res.ok` 만 실패로 보므로 **실서버에서 폴백이 영원히
    발동하지 않았고**, 중국어 400 이 한 달간 빈 전사로 조용히 저장됐다. 이제 실패는 위로
    올려서 호출부(`_recognize`)가 **성공 여부를 함께 반환**한다.
    """
    s = get_settings()
    if not s.gcp_project_id:
        return ""
    from google.cloud.speech_v2 import SpeechClient
    from google.cloud.speech_v2.types import cloud_speech

    client = SpeechClient()
    config = cloud_speech.RecognitionConfig(
        auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
        language_codes=[language_code],
        model="long",
    )
    request = cloud_speech.RecognizeRequest(
        recognizer=f"projects/{s.gcp_project_id}/locations/global/recognizers/_",
        config=config,
        content=content,
    )
    resp = client.recognize(request=request)
    return " ".join(r.alternatives[0].transcript for r in resp.results if r.alternatives).strip()


def _recognize(content: bytes, language_code: str) -> tuple[str, bool]:
    """(전사, STT 성공 여부). 실패해도 예외를 밖으로 내지 않는다 — 오디오 저장은 계속돼야 한다.

    성공 여부를 **따로** 돌려주는 게 핵심이다: 빈 transcript 만으로는 무음 녹음(성공)과
    엔진 실패(400·권한·쿼터)를 구별할 수 없어, 프론트의 폴백이 발동할 수가 없었다.
    """
    try:
        return _recognize_raw(content, language_code), True
    except Exception as exc:  # noqa: BLE001 — 흐름은 막지 않되(오디오 보존) 실패는 **알린다**.
        logger.warning("[STT] 전사 실패 lang=%s: %s", language_code, str(exc)[:280])
        return "", False


@router.post("/transcribe", response_model=TranscribeOut)
async def transcribe(
    file: UploadFile = File(...),
    language_code: str = Form("ko-KR"),
    claims: dict = Depends(verify_respondent),
) -> TranscribeOut:
    """음성 답변 오디오 → 전사 텍스트 + GCS 저장(ref). 응답 제출 시 ref 를 answer.url 로 보낸다.

    STT 미설정이면 transcript 만 비고(응답자가 직접 타이핑), GCS 미설정이면 ref/url 만 빈다.
    """
    from ..services import gcs_storage

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="빈 오디오예요.")
    if len(raw) > _MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="오디오가 너무 깁니다 (최대 15MB).")

    # STT·GCS·LLM 은 블로킹 네트워크 호출 — 단일 워커 이벤트루프 비차단을 위해 스레드풀 오프로드.
    transcript, stt_ok = await run_in_threadpool(_recognize, raw, language_code)
    if transcript:
        # 반환 전 경량 LLM 맞춤법·띄어쓰기 보정(T-STT-SPELLFIX) — 실패 시 원문(best-effort).
        transcript = await run_in_threadpool(_spellfix, transcript)

    content_type = (file.content_type or "audio/webm").split(";")[0].lower()
    ext = _AUDIO_EXT.get(content_type, ".webm")
    uid = claims.get("uid") or "anon"
    path = f"survey-audio/{uid}/{uuid.uuid4().hex}{ext}"
    gcs_uri = await run_in_threadpool(gcs_storage.upload_bytes, path, raw, content_type)
    ref = path if gcs_uri else ""
    url = (await run_in_threadpool(gcs_storage.signed_url, path, 7) or "") if gcs_uri else ""
    return TranscribeOut(transcript=transcript, ref=ref, url=url, stt_ok=stt_ok)
