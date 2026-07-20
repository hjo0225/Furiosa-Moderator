import { useEffect, useRef, useState } from "react";

/* 바닥 따라가기 — 위로 스크롤하면 해제, resumeLatest 로 복귀.
   streamRef 는 호출부(page)의 스크롤 컨테이너 div 에 그대로 장착해야 한다(round-trip).
   deps 는 "바닥 고정을 다시 트리거할 값들"(트리거일 뿐, 클로저로 잡지 않는다 — 효과 본문은 ref 만 읽음). */
export function useStickToBottom(deps: unknown[]) {
  const streamRef = useRef<HTMLDivElement>(null);
  const followRef = useRef(true);
  const [follow, setFollow] = useState(true);

  useEffect(() => {
    if (!followRef.current) return;
    const el = streamRef.current;
    if (el) el.scrollTop = el.scrollHeight;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    const el = streamRef.current;
    if (!el) return;
    const set = (v: boolean) => {
      if (followRef.current === v) return;
      followRef.current = v;
      setFollow(v);
    };
    const nearBottom = () => el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    // 사용자 제스처로 위로 벗어나면 팔로우 해제 — 프로그램 스크롤(바닥 고정)과 구분.
    const onUserScroll = () => {
      if (!nearBottom()) set(false);
    };
    // 다시 바닥 근처로 돌아오면 재무장.
    const onScroll = () => {
      if (nearBottom()) set(true);
    };
    el.addEventListener("wheel", onUserScroll, { passive: true });
    el.addEventListener("touchmove", onUserScroll, { passive: true });
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      el.removeEventListener("wheel", onUserScroll);
      el.removeEventListener("touchmove", onUserScroll);
      el.removeEventListener("scroll", onScroll);
    };
  }, []);

  const resumeLatest = () => {
    followRef.current = true;
    setFollow(true);
    const el = streamRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  };

  return { streamRef, follow, resumeLatest };
}
