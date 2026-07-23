// 벤치마크 뷰 공용 포맷터 — design.md §5 "벤치마크": 미측정=`—`, 추정치 금지(스펙 §8).
// 숫자 렌더는 항상 이 함수를 거친다 — 컴포넌트에서 직접 toFixed 하지 않는다(null 누락 방지).
import type { BenchmarkResult, BenchmarkRow } from "@/lib/api";

export type GateStatus = "unmeasured" | "pass" | "fail";

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

/** 0~1 비율 → 퍼센트 문자열. null 은 `—`. */
export function fmtPct(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

/** 문자열 메타 필드 — 빈 문자열/공백도 미측정으로 취급. */
export function fmtStr(v: string | null | undefined): string {
  return v && v.trim().length > 0 ? v : "—";
}

/** M1/M3 헤드라인 카드가 참조하는 기준 행. 스펙 §5: M1 은
 *  governor=Performance·prefix caching=on 조합에서만 구한다 — 그 행을 대표값으로 쓴다. */
export function primaryRow(result: BenchmarkResult): BenchmarkRow | null {
  return result.rows.find((r) => r.config === "rngd_perf_cache_on") ?? null;
}

/** M3 게이트(스펙 §1): RNGD 행 중 하나라도 κ<0.75 또는 Δκ<−0.05 면 M1·M2 전체 무효.
 *  κ 실측이 하나도 없으면 "미측정"(fail 로 단정하지 않는다 — 없는 데이터를 나쁜 데이터로 취급 금지). */
export function gateStatus(result: BenchmarkResult): GateStatus {
  const measured = result.rows.filter((r) => r.hardware === "rngd" && r.kappa !== null);
  if (measured.length === 0) return "unmeasured";
  const failed = measured.some(
    (r) =>
      (r.kappa as number) < 0.75 || (r.delta_kappa !== null && (r.delta_kappa as number) < -0.05),
  );
  return failed ? "fail" : "pass";
}
