"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card } from "@/components/shared";
import type { BenchmarkResult } from "@/lib/api";

import { fmtNum, fmtPct } from "./format";

// idle 지배 분석 — 계측 스펙 §2·§7 "표 3".
// 손익분기 S* 를 대체한다: 대조군 비용과 벽면 전력이 없으면 교차점을 계산할 수 없고,
// 추정 상수로 곡선을 그리는 순간 실측 문서가 아니게 된다(스펙 §9). 대신 실측만으로
// 성립하는 같은 논증을 한다 — 세션당 에너지는 하드웨어가 아니라 가동률이 정한다.
//
// 색 — design.md §1: NPU=brand-red. 차트는 CSS 변수를 못 읽어 리터럴로 둔다.
const NPU_COLOR = "#E21500";
const IDLE_COLOR = "#7F7F7F";

export function IdleDominancePanel({ result }: { result: BenchmarkResult }) {
  const measured = result.energy.filter((r) => r.wh_per_session !== null);
  const hasCurve = measured.length > 1;
  const chartData = measured.map((r) => ({
    x: r.sessions_per_day,
    wh: r.wh_per_session,
    idle: r.idle_share === null ? null : Math.round(r.idle_share * 100),
  }));

  // 헤드라인 = 최저·최고 가동률 사이의 배수. 이 화면이 말하려는 것 자체다.
  const first = measured[0]?.wh_per_session ?? null;
  const last = measured[measured.length - 1]?.wh_per_session ?? null;
  const ratio = first !== null && last !== null && last > 0 ? first / last : null;

  return (
    <Card as="section" className="p-6">
      <div className="flex flex-wrap items-center gap-2">
        <p className="eyebrow">M2 · idle 지배</p>
        <span className="inline-flex w-fit items-center rounded-md bg-platinum px-2 py-0.5 text-2xs font-medium text-grey">
          카드 센서 기준 하한값 · CPU/NIC/팬 미포함
        </span>
      </div>

      <p className="mt-3 text-title text-obsidian">
        <span className="font-telemetry text-red">
          {ratio === null ? "—" : `${ratio.toFixed(0)}배`}
        </span>
        <span className="ml-2 text-lead font-normal text-charcoal">
          세션당 에너지 차이 (가동률만으로)
        </span>
      </p>
      <p className="mt-2 max-w-2xl text-meta text-charcoal">
        이 워크로드는 참가자가 말하고 생각하는 동안 카드가 논다. 그래서 총 에너지를 유휴 전력이
        지배하고, 세션당 에너지는 하드웨어가 아니라 <b className="text-obsidian">가동률</b>이 정한다.
        &ldquo;몇 배 빠른가&rdquo;가 아니라 &ldquo;몇 세션부터 유리한가&rdquo;로 물어야 하는 이유다.
      </p>

      {hasCurve ? (
        <div className="mt-5 h-56 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
              <CartesianGrid stroke="#E1E1E1" strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="x"
                tick={{ fontSize: 11, fill: "#7F7F7F" }}
                tickLine={false}
                axisLine={{ stroke: "#D4D4D4" }}
                label={{ value: "하루 세션 수", position: "insideBottom", offset: -4, fontSize: 11, fill: "#7F7F7F" }}
              />
              <YAxis
                tick={{ fontSize: 11, fill: "#7F7F7F" }}
                tickLine={false}
                axisLine={{ stroke: "#D4D4D4" }}
                width={44}
              />
              <Tooltip
                contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #D4D4D4" }}
                formatter={(value, name) => {
                  const v = typeof value === "number" ? value : null;
                  return name === "wh"
                    ? [`${fmtNum(v, { digits: 1 })} Wh/세션`, "세션당"]
                    : [fmtPct(v === null ? null : v / 100), "idle 비중"];
                }}
                labelFormatter={(x) => `하루 ${x}세션`}
              />
              <Line type="monotone" dataKey="wh" stroke={NPU_COLOR} strokeWidth={2} dot />
              <Line
                type="monotone"
                dataKey="idle"
                stroke={IDLE_COLOR}
                strokeWidth={1.5}
                strokeDasharray="4 3"
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="mt-5 rounded-lg bg-paper px-4 py-6 text-center text-meta text-grey">
          아직 측정된 에너지 데이터가 없습니다.
        </p>
      )}

      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[560px] border-collapse text-left text-meta">
          <thead>
            <tr className="border-b border-silver text-2xs uppercase tracking-wide text-grey">
              <th className="py-2 pr-4 font-medium">하루 세션 수</th>
              <th className="py-2 pr-4 font-medium">active Wh</th>
              <th className="py-2 pr-4 font-medium">idle Wh</th>
              <th className="py-2 pr-4 font-medium">세션당 Wh</th>
              <th className="py-2 font-medium">idle 비중</th>
            </tr>
          </thead>
          <tbody>
            {result.energy.map((r) => (
              <tr key={r.sessions_per_day} className="border-b border-platinum last:border-0">
                <td className="py-2.5 pr-4 font-telemetry text-obsidian">
                  {fmtNum(r.sessions_per_day)}
                </td>
                <td className="py-2.5 pr-4 font-telemetry text-obsidian">
                  {fmtNum(r.active_wh, { digits: 1 })}
                </td>
                <td className="py-2.5 pr-4 font-telemetry text-obsidian">
                  {fmtNum(r.idle_wh, { digits: 1 })}
                </td>
                <td className="py-2.5 pr-4 font-telemetry text-obsidian">
                  {fmtNum(r.wh_per_session, { digits: 1 })}
                </td>
                <td className="py-2.5 font-telemetry text-obsidian">{fmtPct(r.idle_share)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
