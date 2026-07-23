// 벤치마크 뷰 공용 포맷터 — design.md §5 "벤치마크": 미측정=`—`, 추정치 금지(스펙 §8).
// 숫자 렌더는 항상 이 함수를 거친다 — 컴포넌트에서 직접 toFixed 하지 않는다(null 누락 방지).
import type { BenchmarkResult } from "@/lib/api";

/** null|undefined|NaN → `—`. 그 외엔 천단위 콤마 + 고정 소수 자리. */
export function fmtNum(
  v: number | null | undefined,
  opts?: { digits?: number; unit?: string; signed?: boolean },
): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const digits = opts?.digits ?? 0;
  const body = v.toLocaleString("ko-KR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  const signed = opts?.signed && v > 0 ? `+${body}` : body;
  return opts?.unit ? `${signed}${opts.unit}` : signed;
}

/** ms → 초 문자열. null 은 `—`. */
export function fmtSec(ms: number | null | undefined, digits = 2): string {
  if (ms === null || ms === undefined || Number.isNaN(ms)) return "—";
  return `${(ms / 1000).toFixed(digits)}s`;
}

/** 0~1 비율 → 퍼센트 문자열. null 은 `—`. */
export function fmtPct(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

/** 문자열 메타 필드 — 빈 문자열/공백도 미측정으로 취급. */
export function fmtStr(v: string | null | undefined): string {
  return v && v.trim().length > 0 ? v : "—";
}

/** M1 판정 표시. 스펙 §1: 전 구간 SLA 미달이면 0 이 아니라 "미달"로 적는다 —
 *  "카드가 못 버틴다"와 "카드는 노는데 파이프라인이 못 따라간다"는 다른 결론이기 때문. */
export function fmtM1(v: BenchmarkResult["m1_sessions_per_card"]): string {
  if (v === null || v === undefined) return "—";
  if (v === "unmet") return "미달";
  return `${v} 세션/카드`;
}

/** 아직 어떤 측정도 실행되지 않았는가 — 배너·플레이스홀더 분기용. */
export function isUnmeasured(result: BenchmarkResult): boolean {
  return result.measured_at === null;
}
