// [T-VOICE-FIRST] 주관식 음성 우선 입력의 폴백 상태 머신 — React 비의존 순수 로직.
// 기본은 음성(voice)이 유일한 입력 UI. 응답 유실을 막아야 하는 세 경로에서만 텍스트로 폴백:
// ① 녹음 미지원(useRecorder.supported=false) ② 마이크 권한 거부 ③ 전사 실패 2회 연속.
// 한번 텍스트로 내려가면 세션 내 유지 — 입력 UI가 오락가락하지 않게(폴백은 편도).
// [T-VOICE-TEXT-TOGGLE] 위 자동 폴백에 더해, 사용자가 직접 키보드 입력을 고르는 경로(choose_text)도 둔다.
// 텍스트 분기에는 이미 음성 녹음 버튼이 있어(page.tsx) 전환 후에도 음성은 그대로 쓸 수 있다.

export type VoiceInputState = {
  mode: "voice" | "text";
  failures: number; // 연속 전사 실패 수(성공 시 리셋)
};

export type VoiceInputEvent =
  | { type: "unsupported" }
  | { type: "permission_denied" }
  | { type: "transcribe_failed" }
  | { type: "transcribe_ok" }
  | { type: "choose_text" }; // 사용자가 명시적으로 키보드 입력 선택

export const initialVoiceInput: VoiceInputState = { mode: "voice", failures: 0 };

export function reduceVoiceInput(
  state: VoiceInputState,
  event: VoiceInputEvent,
): VoiceInputState {
  if (state.mode === "text") return state;
  switch (event.type) {
    case "choose_text":
    case "unsupported":
    case "permission_denied":
      return { ...state, mode: "text" };
    case "transcribe_failed": {
      const failures = state.failures + 1;
      return { mode: failures >= 2 ? "text" : "voice", failures };
    }
    case "transcribe_ok":
      return { ...state, failures: 0 };
  }
}
