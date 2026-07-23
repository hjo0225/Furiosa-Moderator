"use client";

import { Activity } from "lucide-react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card } from "@/components/shared";
import type { BenchmarkResult } from "@/lib/api";

// design.md §1: NPU=brand-red(전력선), 동시 세션 바는 중립 grey/silver — 두 색을 하나의 대조
// 팔레트로 굳이 늘리지 않는다(벤치마크는 NPU/GPU 대비만 vibrant, 그 외는 중립).
const POWER_COLOR = "#E21500";
const SESSIONS_COLOR = "#D4D4D4";

// 전력 시계열 — 계측 스펙 §7 "차트 2": 상단 카드 W, 하단 동시 세션, idle 바닥선.
// 벽면 PDU 는 범위 밖(§9)이라 카드 센서 값을 쓴다 — 하한값이라는 표시를 화면에 남긴다.
// 데이터가 없을 때도 "깨진 화면"이 아니라 의도된 플레이스홀더로 보이게 한다(브리프 요구사항).
export function PowerTimeseriesChart({ result }: { result: BenchmarkResult }) {
  const hasData = result.power_timeseries.length > 1;

  return (
    <Card as="section" className="p-6">
      <p className="eyebrow">24h 전력 시계열</p>
      {!hasData ? (
        <div className="mt-3 flex h-56 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-silver bg-paper px-6 text-center">
          <Activity className="h-5 w-5 text-grey" aria-hidden="true" />
          <p className="text-meta text-charcoal">24h 계측 대기 중</p>
          <p className="max-w-sm text-2xs text-grey">
            furiosa-smi·metrics-exporter 연결 후 카드 W·동시 세션·idle 바닥선이 채워집니다. 가속
            리플레이는 하지 않습니다(계측 스펙 §8) — 유휴 시간이 이 지표의 본질입니다.
          </p>
        </div>
      ) : (
        <div className="mt-3 h-64">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart
              data={result.power_timeseries}
              margin={{ top: 8, right: 12, bottom: 8, left: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#E1E1E1" vertical={false} />
              <XAxis
                dataKey="t"
                tick={{ fontSize: 10, fill: "#7F7F7F" }}
                tickLine={false}
                axisLine={{ stroke: "#D4D4D4" }}
                minTickGap={40}
              />
              <YAxis
                yAxisId="power"
                tick={{ fontSize: 11, fill: "#7F7F7F" }}
                tickLine={false}
                axisLine={false}
                width={40}
                label={{ value: "W", angle: -90, position: "insideLeft", fontSize: 10, fill: "#7F7F7F" }}
              />
              <YAxis
                yAxisId="sessions"
                orientation="right"
                tick={{ fontSize: 11, fill: "#7F7F7F" }}
                tickLine={false}
                axisLine={false}
                width={32}
              />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #D4D4D4" }} />
              {result.idle_baseline_w !== null && (
                <ReferenceLine
                  yAxisId="power"
                  y={result.idle_baseline_w}
                  stroke="#7F7F7F"
                  strokeDasharray="4 4"
                  label={{ value: "idle", fontSize: 10, fill: "#7F7F7F", position: "insideTopLeft" }}
                />
              )}
              <Bar yAxisId="sessions" dataKey="concurrent_sessions" fill={SESSIONS_COLOR} barSize={4} />
              <Line
                yAxisId="power"
                type="monotone"
                dataKey="card_power_w"
                stroke={POWER_COLOR}
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
          <div className="mt-1 flex items-center justify-between text-2xs text-grey">
            <span className="flex items-center gap-1.5">
              <span className="h-1.5 w-3 rounded-full" style={{ background: POWER_COLOR }} />
              카드 W
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-1.5 w-3 rounded-full" style={{ background: SESSIONS_COLOR }} />
              동시 세션
            </span>
          </div>
        </div>
      )}
    </Card>
  );
}
