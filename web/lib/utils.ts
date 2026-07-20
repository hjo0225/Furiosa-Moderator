import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/**
 * 커스텀 폰트크기 토큰(text-meta·text-lead·text-title …)을 twMerge 의 `font-size` 그룹으로 등록.
 * 등록하지 않으면 twMerge 가 이들을 `text-색상`으로 오인해, 버튼처럼
 * `text-accent-on`(색) + `text-lead`(크기)가 함께 오는 경우 색 클래스를 제거한다
 * → 색 채운 버튼 글자가 검게 보이던 원인. (tailwind.config fontSize 토큰과 동기화)
 */
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [{ text: ["2xs", "meta", "lead", "title", "score", "display", "hero"] }],
    },
  },
});

/** Tailwind 클래스 병합 유틸 (조건부 + 충돌 해결) */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
