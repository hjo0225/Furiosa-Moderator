"""음성(TTS/STT) 스키마 — 구버전 mindlens_backend views/speech·stt 이식.

TTS: 안내문·문항 읽어주기. STT: 주관식 음성 답변 → 텍스트(+오디오 GCS 저장).
프론트와 camelCase alias 로 통신.
"""
from pydantic import BaseModel, ConfigDict, Field


class VoiceOut(BaseModel):
    """TTS 음성 1종 — 응답 페이지 음성 설정 드롭다운."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    language_code: str = Field(default="", alias="languageCode")
    gender: str = ""  # MALE | FEMALE | NEUTRAL


class SynthesizeIn(BaseModel):
    """읽어주기 — 텍스트 + 음성·속도·볼륨. 결과는 mp3 바이트 스트림."""

    model_config = ConfigDict(populate_by_name=True)

    text: str = Field(min_length=1)
    voice_name: str = Field(default="", alias="voiceName")
    language_code: str = Field(default="ko-KR", alias="languageCode")
    speaking_rate: float = Field(default=1.0, alias="speakingRate", ge=0.25, le=4.0)
    volume_gain_db: float = Field(default=0.0, alias="volumeGainDb", ge=-96.0, le=16.0)


class TranscribeOut(BaseModel):
    """음성 답변 전사 결과 — transcript(받아쓴 텍스트) + ref(오디오 GCS 객체 경로)."""

    model_config = ConfigDict(populate_by_name=True)

    transcript: str = ""
    ref: str = ""  # 답변 제출 시 answer.url 로 저장(조회 때 서명 URL 재발급)
    url: str = ""  # 즉시 재생 가능한 서명 URL(미리듣기)
    # [T-STT-FAILURE-SILENT] STT 엔진이 실제로 성공했는가. **빈 transcript 로는 구별이 안 된다** —
    # 무음 녹음(성공했는데 할 말이 없음)과 엔진 실패(400·권한·쿼터)가 똑같이 "" 로 보인다.
    # 이 갭 때문에 중국어 STT 400 이 한 달간 200+빈 전사로 조용히 저장됐다(T-STT-ZH-LANGCODE).
    # 상태코드를 바꾸면 폴백 계약·e2e 가 동시에 움직이므로 플래그로 **비파괴 확장**한다.
    # 기본 True — 이 필드를 모르는 구버전 프론트는 기존과 똑같이 동작한다.
    stt_ok: bool = Field(default=True, alias="sttOk")
