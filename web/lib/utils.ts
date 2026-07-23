import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/**
 * 커스텀 폰트크기 토큰(text-meta·text-lead·text-title …)을 twMerge 의 `font-size` 그룹으로 등록.
 * 등록하지 않으면 twMerge 가 이들을 `text-색상`으로 오인해, 버튼처럼
 * `text-accent-on`(색) + `text-lead`(크기)가 함께 오는 경우 색 클래스를 제거한다
 * → 색 채운 버튼 글자가 검게 보이던 원인. (tailwind.config fontSize 토큰과 동기화)
 *
 * `rounded-card`(커스텀 borderRadius 토큰)도 같은 이유로 `rounded` 그룹에 등록한다 — twMerge
 * 의 기본 borderRadius 검증기는 t-shirt 사이즈(sm/md/lg/xl/2xl…)와 대괄호 임의값만 인식해서,
 * 이름 있는 커스텀 키는 그룹 밖 취급되어 `<Card className="rounded-xl">` 같은 덮어쓰기가
 * 충돌 해소 없이 두 라디우스를 동시에 남긴다(웜 카드 rounded-xl 오버라이드가 깨지는 원인).
 *
 * 커스텀 boxShadow 키(shadow-card/elevated/soft/lift/edge)도 마찬가지 — 미등록 시 twMerge 가
 * `shadow-color` 그룹(어떤 문자열도 허용하는 `isAny`)으로 잘못 분류해 `shadow-none` 같은
 * `shadow` 그룹 클래스와 충돌 해소되지 않는다(<Card className="shadow-none"> 이 shadow-card 를
 * 못 지우는 원인).
 */
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [{ text: ["2xs", "meta", "lead", "title", "score", "display", "hero"] }],
      rounded: [{ rounded: ["card"] }],
      shadow: [{ shadow: ["card", "elevated", "soft", "lift", "edge"] }],
    },
  },
});

/** Tailwind 클래스 병합 유틸 (조건부 + 충돌 해결) */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
