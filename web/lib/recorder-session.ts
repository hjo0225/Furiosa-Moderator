// [T-AUDIO-APPEND] pause/resume 단일 녹음 세션의 순수 로직 — React·MediaRecorder 비의존.
// 경과 시간 계산(일시정지 구간 제외)과 pause 지원 감지를 useRecorder 에서 분리해 vitest 로 검증한다.

/** 경과 타이머 — 닫힌(일시정지로 확정된) 구간 합 + 진행 중 구간 시작 시각. */
export type ElapsedTimer = {
  accumulatedMs: number;
  runningSince: number | null; // null = 일시정지/종료 상태
};

export const initialTimer: ElapsedTimer = { accumulatedMs: 0, runningSince: null };

/** 진행 시작/재개 — 이미 진행 중이면 멱등(시작점 유지). */
export function timerStart(t: ElapsedTimer, now: number): ElapsedTimer {
  if (t.runningSince !== null) return t;
  return { ...t, runningSince: now };
}

/** 일시정지 — 진행 중 구간을 누적으로 확정. 이미 정지면 멱등. */
export function timerPause(t: ElapsedTimer, now: number): ElapsedTimer {
  if (t.runningSince === null) return t;
  return { accumulatedMs: t.accumulatedMs + (now - t.runningSince), runningSince: null };
}

export function elapsedMs(t: ElapsedTimer, now: number): number {
  return t.accumulatedMs + (t.runningSince !== null ? now - t.runningSince : 0);
}

export function elapsedSeconds(t: ElapsedTimer, now: number): number {
  return Math.floor(elapsedMs(t, now) / 1000);
}

/** iOS 사파리 등 MediaRecorder pause 미지원 감지 — 프로토타입의 pause/resume 함수 존재 확인. */
export function recorderSupportsPause(proto: unknown): boolean {
  if (!proto || typeof proto !== "object") return false;
  const p = proto as { pause?: unknown; resume?: unknown };
  return typeof p.pause === "function" && typeof p.resume === "function";
}

// ── [T-VOICE-STOP-DEADLOCK] 정지 ──

/** MediaRecorder 중 정지에 필요한 최소 계약 — 실제 MediaRecorder 가 그대로 대입되고,
    테스트에선 가짜 객체로 대체 가능하다. `state` 는 안 쓰지만 가짜가 실물을 흉내내게 열어둔다. */
export type StoppableRecorder = {
  state?: string;
  mimeType?: string;
  stream: { getTracks(): Array<{ stop(): void }> };
  stop(): void;
  onstop: ((ev: Event) => unknown) | null;
};

/** 기본 정지 대기 한도 — 이 안에 onstop 이 안 오면 지금까지의 조각으로 마감한다. */
export const STOP_TIMEOUT_MS = 3_000;

/** 녹음 정지 — **어떤 경우에도 reject 하지 않고 반드시 resolve 한다.**
 *
 * 이 계약이 이 함수의 존재 이유다(T-VOICE-STOP-DEADLOCK, 2026-07-17 실사고):
 * MediaRecorder 는 마이크를 뺏기면(전화 수신·앱 전환·타 앱 점유·권한 회수) 우리가 모르는 사이
 * `inactive` 가 된다. 그 뒤 `rec.stop()` 을 부르면 **InvalidStateError 를 동기 throw** 하는데,
 * 이게 Promise executor 안이면 **promise 가 reject** 되고 호출부의 상태 정리(`setRecordingFor(null)`)가
 * 통째로 스킵된다 → `audioBusy` 영구 true → 다음·제출 버튼 영구 잠금 → 새로고침 외 탈출 불가
 * (= 그 설문 답변 전량 유실). `onstop` 이 영영 안 오는 경우도 같은 결말이라 타임아웃으로 끊는다.
 *
 * 그래서 여기서는 **실패해도 조각을 살려 resolve** 한다 — 33초짜리 녹음이 있는데 상태 정리에
 * 실패했다는 이유로 통째로 버리는 게 최악이다. */
export function stopRecording(
  rec: StoppableRecorder,
  chunks: Blob[],
  timeoutMs: number = STOP_TIMEOUT_MS,
): Promise<Blob | null> {
  return new Promise((resolve) => {
    let settled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const finish = () => {
      if (settled) return; // onstop 과 타임아웃이 겹쳐도 정리는 한 번만
      settled = true;
      if (timer !== null) clearTimeout(timer);
      try {
        rec.stream.getTracks().forEach((t) => t.stop()); // 마이크를 켜둔 채 끝내지 않는다
      } catch {
        /* 트랙 정리 실패는 삼킨다 — 블롭 회수가 우선 */
      }
      resolve(chunks.length ? new Blob(chunks, { type: rec.mimeType || "audio/webm" }) : null);
    };

    rec.onstop = finish;
    timer = setTimeout(finish, timeoutMs);
    try {
      rec.stop(); // paused 상태에서도 유효 — 지금까지의 조각으로 최종 블롭 1개
    } catch {
      finish(); // 이미 inactive — 여기서 throw 를 흘리면 호출부가 영구 교착된다
    }
  });
}
