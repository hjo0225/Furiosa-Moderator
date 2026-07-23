"use client";

// 벤치마크 뷰 — NPU vs GPU 손익분기(Task 7). design.md §5 "벤치마크"·계측 스펙
// docs/specs/2026-07-23-rngd-benchmark-instrumentation.md §7 출력물을 소비만 한다(계산 안 함).
// null-우선: 실측 전에도 화면이 "고장" 이 아니라 "의도된 상태"로 보여야 한다(브리프 요구사항).
import { useEffect, useState } from "react";
import { Cpu } from "lucide-react";

import { Container, Skeleton } from "@/components/shared";
import { fetchBenchmarkResult, type BenchmarkResult } from "@/lib/api";

import { BreakevenPanel } from "./breakeven-panel";
import { HonestyBanner } from "./honesty-banner";
import { MetricCards } from "./metric-cards";
import { PowerTimeseriesChart } from "./power-chart";
import { ResultsTable } from "./results-table";
import { RunMetadataAppendix } from "./run-metadata";

export function BenchmarkView() {
  const [result, setResult] = useState<BenchmarkResult | null>(null);

  useEffect(() => {
    let alive = true;
    fetchBenchmarkResult().then((r) => {
      if (alive) setResult(r);
    });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <main className="py-10 md:py-16">
      <Container className="max-w-5xl">
        <div className="flex items-center gap-2">
          <Cpu className="h-5 w-5 text-red" aria-hidden="true" />
          <h1 className="text-title text-obsidian">성능 · 벤치마크</h1>
        </div>
        <p className="mt-2 max-w-2xl text-base text-charcoal">
          &ldquo;누가 토큰을 빨리 뽑나&rdquo;가 아니라, 저부하·긴 컨텍스트·짧은 출력 구간에서
          월 몇 세션부터 RNGD가 대조군보다 유리해지는지를 봅니다.
        </p>

        {!result ? (
          <div className="mt-6 space-y-4" aria-hidden="true">
            <Skeleton className="h-20 w-full rounded-card" />
            <Skeleton className="h-40 w-full rounded-card" />
            <div className="grid gap-4 md:grid-cols-3">
              <Skeleton className="h-44 w-full rounded-card" />
              <Skeleton className="h-44 w-full rounded-card" />
              <Skeleton className="h-44 w-full rounded-card" />
            </div>
            <Skeleton className="h-64 w-full rounded-card" />
          </div>
        ) : (
          <div className="mt-6 space-y-6">
            <HonestyBanner result={result} />
            <BreakevenPanel result={result} />
            <MetricCards result={result} />
            <ResultsTable rows={result.rows} />
            <PowerTimeseriesChart result={result} />
            <RunMetadataAppendix result={result} />
          </div>
        )}
      </Container>
    </main>
  );
}
