// SSE 파서 — fetch + ReadableStream. EventSource 는 POST 를 못 보내서 쓸 수 없다.
// 서버 포맷은 api/services/progress.py 의 sse(): `data: {json}\n\n`.

/** 버퍼에서 완성된 프레임의 data 페이로드만 뽑고, 남은 꼬리를 돌려준다(순수 함수). */
export function parseSseBuffer(buffer: string): { payloads: string[]; rest: string } {
  const frames = buffer.split("\n\n");
  // 마지막 조각은 아직 안 끝난 프레임일 수 있으므로 버퍼에 남긴다.
  const rest = frames.pop() ?? "";
  const payloads: string[] = [];
  for (const frame of frames) {
    for (const line of frame.split("\n")) {
      if (line.startsWith("data:")) payloads.push(line.slice(5).trim());
    }
  }
  return { payloads, rest };
}

/** SSE 를 끝까지 읽으며 이벤트마다 onEvent 를 부른다. 중단은 signal 로. */
export async function streamSse<T>(
  url: string,
  init: RequestInit,
  onEvent: (event: T) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(url, { ...init, signal, cache: "no-store" });
  if (!res.ok || !res.body) {
    throw new Error(`${init.method ?? "GET"} ${url} → ${res.status}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parsed = parseSseBuffer(buffer);
    buffer = parsed.rest;
    for (const payload of parsed.payloads) {
      if (!payload) continue;
      onEvent(JSON.parse(payload) as T);
    }
  }
}
