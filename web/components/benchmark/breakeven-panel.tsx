"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card } from "@/components/shared";
import type { BenchmarkResult } from "@/lib/api";

import { fmtNum } from "./format";

// 색 — design.md §1: 벤치마크는 NPU=brand-red, GPU=grey/silver(대조), 차트는 CSS 변수를
// 못 읽으므로 리터럴로 둔다(results-panel.tsx 의 기존 관례와 동일).
const NPU_COLOR = "#E21500";
const GPU_COLOR = "#7F7F7F";

/** 실측 전 스키매틱 곡선 — 값이 아니라 "두 비용선이 어딘가서 교차한다"는 형태만 보여준다.
 * 축 눈금을 숨겨 실측 데이터처럼 보이지 않게 한다(스펙 §8: 추정치 금지).
 * 모양은 스펙 §2 비용 모델(fixed + S*variable, 둘 다 단조 증가)을 따른다 — NPU는 카드
 * 감가상각·idle 고정비 때문에 시작이 높고 완만하게 오르고, 대조군은 시작이 낮지만
 * 세션당 변동비가 커서 가파르게 올라 결국 역전된다(방향이 반대로 그려지면 안 된다). */
const SCHEMATIC_CURVE = Array.from({ length: 11 }, (_, i) => ({
  x: i,
  npu: 6 + i * 0.15,
  gpu: 1 + i * 0.75,
}));

export function BreakevenPanel({ result }: { result: BenchmarkResult }) {
  const hasCurve = result.breakeven_curve.length > 1;
  const chartData = hasCurve
    ? result.breakeven_curve.map((p) => ({ x: p.sessions, npu: p.cost_rngd, gpu: p.cost_baseline }))
    : SCHEMATIC_CURVE;

  return (
    <Card as="section" className="p-6">
      <div className="flex flex-wrap items-center gap-2">
        <p className="eyebrow">손익분기</p>
        {!hasCurve && (
          <span className="inline-flex w-fit items-center rounded-md bg-platinum px-2 py-0.5 text-2xs font-medium text-grey">
            스키매틱 · 실측 아님
          </span>
        )}
      </div>
      <div className="mt-3 flex flex-col gap-6 md:flex-row md:items-center">
        <div className="shrink-0 md:w-64">
          <p className="font-telemetry text-score text-red">
            {result.s_breakeven === null ? "—" : fmtNum(result.s_breakeven)}
          </p>
          <p className="mt-1 text-meta text-charcoal">
            월 세션 수가 이 값을 넘으면 RNGD 총비용이 대조군보다 낮아집니다.
          </p>
          <p className="mt-2 text-2xs text-grey">
            {result.s_breakeven === null
              ? "실측 전 · 계측 하네스 실행 후 채워집니다."
              : "S* = 월 손익분기 세션 수"}
          </p>
        </div>

        <div className="min-w-0 flex-1">
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E1E1E1" vertical={false} />
                <XAxis
                  dataKey="x"
                  tick={hasCurve ? { fontSize: 11, fill: "#7F7F7F" } : false}
                  tickLine={false}
                  axisLine={{ stroke: "#D4D4D4" }}
                  label={
                    hasCurve
                      ? {
                          value: "월 세션 수",
                          position: "insideBottom",
                          offset: -4,
                          fontSize: 11,
                          fill: "#7F7F7F",
                        }
                      : undefined
                  }
                />
                <YAxis
                  tick={hasCurve ? { fontSize: 11, fill: "#7F7F7F" } : false}
                  tickLine={false}
                  axisLine={false}
                  width={hasCurve ? 40 : 0}
                />
                {hasCurve && (
                  <Tooltip
                    contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #D4D4D4" }}
                  />
                )}
                <Line
                  type="monotone"
                  dataKey="npu"
                  stroke={NPU_COLOR}
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="gpu"
                  stroke={GPU_COLOR}
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-1 flex flex-wrap items-center justify-between gap-2 text-2xs text-grey">
            <span className="flex items-center gap-1.5">
              <span className="h-1.5 w-3 rounded-full" style={{ background: NPU_COLOR }} />
              RNGD 총비용
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-1.5 w-3 rounded-full" style={{ background: GPU_COLOR }} />
              대조군 총비용
            </span>
          </div>
        </div>
      </div>
    </Card>
  );
}
