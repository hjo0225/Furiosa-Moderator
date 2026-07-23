"use client";

// C-4 결과 대시보드 — 세션 목록 · 세션별 전사/요약/감정 · 집계 인사이트(recharts) + C-5 내보내기.
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Mic } from "lucide-react";

import { Button, Card, ErrorState, Skeleton } from "@/components/shared";
import { TranscriptView } from "@/components/response-viewer";
import {
  getDashboard,
  getGuide,
  getTurns,
  regenerateInsight,
  type Dashboard,
  type Insight,
  type InterviewGuide,
  type Session,
  type Turn,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const STATUS_LABEL: Record<Session["status"], string> = {
  consented: "동의만",
  active: "진행 중",
  pending: "미제출",
  completed: "완료",
  abandoned: "중단",
};

// 차트 색 — design.md §1 데이터 팔레트(차트는 CSS 변수를 못 읽어 리터럴로 둔다).
// 센티먼트: 긍정=mint · 중립=grey · 우려=orange · 부정=maroon(브랜드 red 와 충돌 회피).
const ACCENT = "#E21500";
const SENTIMENT_COLOR: Record<string, string> = {
  긍정: "#70E697",
  중립: "#7F7F7F",
  부정: "#6F2020",
  우려: "#FF9A52",
  positive: "#70E697",
  neutral: "#7F7F7F",
  negative: "#6F2020",
};

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function download(filename: string, content: string, mime: string) {
  // UTF-8 BOM — 엑셀이 BOM 없는 UTF-8 CSV 의 한글을 깨뜨린다.
  const blob = new Blob([mime.startsWith("text/csv") ? "﻿" + content : content], {
    type: `${mime};charset=utf-8`,
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function csvCell(v: unknown): string {
  const s = v === null || v === undefined ? "" : String(v);
  return `"${s.replace(/"/g, '""')}"`;
}

export function ResultsPanel({ projectId }: { projectId: string }) {
  const [data, setData] = useState<Dashboard | null>(null);
  const [guide, setGuide] = useState<InterviewGuide | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[] | null>(null);
  const [insightBusy, setInsightBusy] = useState(false);
  const [exporting, setExporting] = useState(false);

  const load = useCallback(() => {
    getDashboard(projectId)
      .then(setData)
      .catch(() => setError("결과를 불러오지 못했어요. 백엔드가 켜져 있는지 확인해 주세요."));
  }, [projectId]);

  useEffect(load, [load]);

  // 버킷 분포는 bucket_id 만 온다 — 라벨은 가이드의 response_buckets 로 매핑한다.
  // 가이드가 없거나 404 면 분포 섹션만 조용히 감춘다(대시보드 나머지는 그대로).
  useEffect(() => {
    getGuide(projectId)
      .then(setGuide)
      .catch(() => setGuide(null));
  }, [projectId]);

  // 세션 선택 → 전사 로드
  useEffect(() => {
    if (!selectedId) {
      setTurns(null);
      return;
    }
    let alive = true;
    setTurns(null);
    getTurns(projectId, selectedId)
      .then((t) => alive && setTurns(t))
      .catch(() => alive && setTurns([]));
    return () => {
      alive = false;
    };
  }, [projectId, selectedId]);

  const sessions = data?.sessions ?? [];
  const insight = data?.insight ?? null;
  const selected = sessions.find((s) => s.id === selectedId) ?? null;

  const themeData = useMemo(
    () =>
      (insight?.themes ?? []).map((t) => ({
        name: t.theme.length > 12 ? `${t.theme.slice(0, 12)}…` : t.theme,
        full: t.theme,
        count: t.mention_count,
      })),
    [insight],
  );

  const sentimentData = useMemo(
    () =>
      Object.entries(insight?.sentiment ?? {}).map(([name, count]) => ({
        name,
        count,
        fill: SENTIMENT_COLOR[name] ?? ACCENT,
      })),
    [insight],
  );

  // 문항별 응답 버킷 분포(F6.4) — DB 실측 카운트를 가이드 버킷 라벨과 합친다.
  // 아직 분류된 응답이 없는 문항(total 0)은 감춘다.
  const bucketSections = useMemo(() => {
    const dist = insight?.bucket_distribution ?? {};
    return (guide?.questions ?? [])
      .filter((q) => q.response_buckets.length > 0)
      .map((q) => {
        const counts = dist[q.id] ?? {};
        const total = q.response_buckets.reduce((sum, b) => sum + (counts[b.id] ?? 0), 0);
        return {
          id: q.id,
          text: q.text,
          total,
          bars: q.response_buckets.map((b) => {
            const count = counts[b.id] ?? 0;
            return {
              id: b.id,
              label: b.label,
              count,
              pct: total ? Math.round((count / total) * 100) : 0,
            };
          }),
        };
      })
      .filter((sec) => sec.total > 0);
  }, [guide, insight]);

  // 문항별 AI 요약(F6.3) — question_id → {headline, summary}.
  const summaryMap = useMemo(() => {
    const m = new Map<string, { headline: string; summary: string }>();
    for (const qs of insight?.question_summaries ?? []) {
      m.set(qs.question_id, { headline: qs.headline, summary: qs.summary });
    }
    return m;
  }, [insight]);

  // 요약과 버킷 분포를 문항 단위로 합친다. 버킷이 있는 문항엔 요약을 얹고,
  // 버킷은 없지만 요약만 있는 문항은 요약 전용 카드로 노출한다(요약이 묻히지 않게).
  const questionSections = useMemo(() => {
    type QBar = { id: string; label: string; count: number; pct: number };
    const withBuckets = bucketSections.map((sec) => ({
      ...sec,
      headline: summaryMap.get(sec.id)?.headline ?? "",
      summary: summaryMap.get(sec.id)?.summary ?? "",
    }));
    const covered = new Set(bucketSections.map((s) => s.id));
    const summaryOnly = (guide?.questions ?? [])
      .filter((q) => !covered.has(q.id) && summaryMap.has(q.id))
      .map((q) => {
        const s = summaryMap.get(q.id)!;
        return {
          id: q.id,
          text: q.text,
          total: 0,
          bars: [] as QBar[],
          headline: s.headline,
          summary: s.summary,
        };
      });
    return [...withBuckets, ...summaryOnly];
  }, [bucketSections, summaryMap, guide]);

  async function refreshInsight() {
    setInsightBusy(true);
    setError(null);
    try {
      const next: Insight = await regenerateInsight(projectId);
      setData((d) => (d ? { ...d, insight: next } : d));
    } catch {
      setError("인사이트 생성에 실패했어요.");
    } finally {
      setInsightBusy(false);
    }
  }

  /** 전 세션의 전사를 모아 내보낸다 (C-5). */
  async function exportAll(format: "csv" | "json") {
    if (!data) return;
    setExporting(true);
    setError(null);
    try {
      const all = await Promise.all(
        sessions.map(async (s) => ({
          session: s,
          turns: await getTurns(projectId, s.id).catch(() => [] as Turn[]),
        })),
      );
      const stamp = new Date().toISOString().slice(0, 10);
      if (format === "json") {
        download(
          `mindlens-${projectId}-${stamp}.json`,
          JSON.stringify({ project: data.project, insight: data.insight, sessions: all }, null, 2),
          "application/json",
        );
      } else {
        const header = [
          "session_id",
          "session_status",
          "started_at",
          "turn_no",
          "role",
          "text",
          "emotion",
          "emotion_confidence",
          "is_probe",
          "pii_masked",
        ];
        const rows = all.flatMap(({ session, turns: ts }) =>
          ts.map((t, i) =>
            [
              session.id,
              session.status,
              session.started_at,
              i + 1,
              t.role,
              t.text,
              t.emotion,
              t.emotion_confidence,
              t.is_probe,
              (t.pii_types ?? []).join("|"),
            ]
              .map(csvCell)
              .join(","),
          ),
        );
        download(
          `mindlens-${projectId}-${stamp}.csv`,
          [header.map(csvCell).join(","), ...rows].join("\r\n"),
          "text/csv",
        );
      }
    } catch {
      setError("내보내기에 실패했어요.");
    } finally {
      setExporting(false);
    }
  }

  if (error && !data) {
    return <ErrorState title="결과를 불러오지 못했어요" body={error} onRetry={load} />;
  }
  if (!data) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-40 w-full rounded-xl" />
        <Skeleton className="h-24 w-full rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 집계 인사이트 */}
      <section className="rounded-xl bg-surface p-5 shadow-card ring-1 ring-line">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lead font-medium">전체 인사이트</h2>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" onClick={refreshInsight} disabled={insightBusy}>
              {insightBusy ? "분석 중…" : insight ? "다시 분석" : "인사이트 생성"}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => exportAll("csv")} disabled={exporting}>
              {exporting ? "준비 중…" : "CSV 내보내기"}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => exportAll("json")} disabled={exporting}>
              JSON
            </Button>
          </div>
        </div>

        {!insight ? (
          <p className="mt-4 text-base text-ink-soft">
            아직 인사이트가 없어요. 응답이 몇 건 모이면 &lsquo;인사이트 생성&rsquo;을 눌러 주세요.
          </p>
        ) : (
          <>
            <p className="mt-3 whitespace-pre-line text-base leading-relaxed text-ink">
              {insight.overall || "요약이 아직 비어 있어요."}
            </p>
            <p className="mt-2 font-mono text-2xs text-ink-faint">
              응답 {insight.session_count}건 기준 · {formatDateTime(insight.generated_at)} 생성
            </p>

            {themeData.length > 0 && (
              <div className="mt-6">
                <h3 className="text-meta font-medium text-ink-soft">주제별 언급 수</h3>
                <div className="mt-2 h-64 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={themeData} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#E1E1E1" vertical={false} />
                      <XAxis
                        dataKey="name"
                        tick={{ fontSize: 11, fill: "#7F7F7F" }}
                        interval={0}
                        tickLine={false}
                        axisLine={{ stroke: "#D4D4D4" }}
                      />
                      <YAxis
                        allowDecimals={false}
                        tick={{ fontSize: 11, fill: "#7F7F7F" }}
                        tickLine={false}
                        axisLine={false}
                      />
                      <Tooltip
                        cursor={{ fill: "#FBEBE9" }}
                        contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #D4D4D4" }}
                        formatter={(v: number) => [`${v}회`, "언급"]}
                        labelFormatter={(_l, p) => p?.[0]?.payload?.full ?? ""}
                      />
                      <Bar dataKey="count" fill={ACCENT} radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            {sentimentData.length > 0 && (
              <div className="mt-6">
                <h3 className="text-meta font-medium text-ink-soft">감정 분포</h3>
                <div className="mt-2 h-48 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={sentimentData} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#E1E1E1" vertical={false} />
                      <XAxis
                        dataKey="name"
                        tick={{ fontSize: 11, fill: "#7F7F7F" }}
                        tickLine={false}
                        axisLine={{ stroke: "#D4D4D4" }}
                      />
                      <YAxis
                        allowDecimals={false}
                        tick={{ fontSize: 11, fill: "#7F7F7F" }}
                        tickLine={false}
                        axisLine={false}
                      />
                      <Tooltip
                        cursor={{ fill: "#E1E1E1" }}
                        contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #D4D4D4" }}
                      />
                      <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                        {sentimentData.map((d) => (
                          <Cell key={d.name} fill={d.fill} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            {questionSections.length > 0 && (
              <div className="mt-6">
                <h3 className="text-meta font-medium text-ink-soft">문항별 요약·분류</h3>
                <div className="mt-3 space-y-4">
                  {questionSections.map((sec) => (
                    <div key={sec.id} className="rounded-lg bg-bg p-4 ring-1 ring-line">
                      <div className="flex items-baseline justify-between gap-2">
                        <p className="text-meta font-medium text-ink">{sec.text}</p>
                        {sec.total > 0 && (
                          <span className="shrink-0 font-mono text-2xs text-ink-faint">
                            응답 {sec.total}건
                          </span>
                        )}
                      </div>
                      {(sec.headline || sec.summary) && (
                        <div className="mt-2">
                          {sec.headline && (
                            <p className="text-meta font-semibold text-ink">{sec.headline}</p>
                          )}
                          {sec.summary && (
                            <p className="mt-1 text-meta leading-relaxed text-ink-soft">
                              {sec.summary}
                            </p>
                          )}
                        </div>
                      )}
                      {sec.bars.length > 0 && (
                        <ul className="mt-3 space-y-2">
                          {sec.bars.map((bar) => (
                            <li key={bar.id}>
                              <div className="flex items-baseline justify-between gap-2 text-meta">
                                <span className="text-ink-soft">{bar.label}</span>
                                <span className="shrink-0 font-mono text-2xs text-ink-faint">
                                  {bar.count} · {bar.pct}%
                                </span>
                              </div>
                              <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-platinum">
                                <div
                                  className="h-full rounded-full bg-red transition-[width]"
                                  style={{ width: `${bar.pct}%` }}
                                />
                              </div>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {insight.themes.length > 0 && (
              <ul className="mt-6 space-y-3">
                {insight.themes.map((t) => (
                  <li key={t.theme} className="rounded-lg bg-bg p-4 ring-1 ring-line">
                    <div className="flex items-baseline justify-between gap-2">
                      <h4 className="text-base font-medium text-ink">{t.theme}</h4>
                      <span className="shrink-0 font-mono text-2xs text-ink-faint">
                        {t.mention_count}회 언급
                      </span>
                    </div>
                    <p className="mt-1 text-meta leading-relaxed text-ink-soft">{t.summary}</p>
                    {t.quotes.length > 0 && (
                      <ul className="mt-2 space-y-1">
                        {t.quotes.map((q, i) => (
                          <li
                            key={i}
                            className="border-l-2 border-accent/40 pl-3 text-meta italic text-ink-soft"
                          >
                            &ldquo;{q}&rdquo;
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
        {error && <p className="mt-3 text-meta text-nogo">{error}</p>}
      </section>

      {/* 세션 목록 + 전사 */}
      <section>
        <h2 className="text-lead font-medium">응답 {sessions.length}건</h2>
        {sessions.length === 0 ? (
          <p className="mt-3 rounded-xl bg-surface p-8 text-center text-base text-ink-soft shadow-card">
            아직 응답이 없어요. 배포한 링크를 응답자에게 보내 보세요.
          </p>
        ) : (
          <div className="mt-3 grid gap-4 lg:grid-cols-[260px,1fr]">
            <ul className="space-y-2 self-start">
              {sessions.map((s, i) => (
                <li key={s.id}>
                  <button
                    onClick={() => setSelectedId(s.id === selectedId ? null : s.id)}
                    className={cn(
                      "w-full rounded-xl px-4 py-3 text-left transition-colors",
                      s.id === selectedId
                        ? "bg-accent-solid text-accent-on"
                        : "bg-surface text-ink shadow-card ring-1 ring-line hover:bg-accent-wash",
                    )}
                  >
                    <span className="block text-base font-medium">
                      응답자 #{sessions.length - i}
                    </span>
                    <span
                      className={cn(
                        "mt-0.5 block font-mono text-2xs",
                        s.id === selectedId ? "text-accent-on/80" : "text-ink-faint",
                      )}
                    >
                      {formatDateTime(s.started_at)} · {STATUS_LABEL[s.status]} · {s.asked}문항
                    </span>
                  </button>
                </li>
              ))}
            </ul>

            <div className="min-w-0">
              {!selected ? (
                <Card className="p-8 text-center">
                  <p className="text-base text-ink-soft">
                    왼쪽에서 응답자를 선택하면 대화 전문이 보여요.
                  </p>
                </Card>
              ) : (
                <div className="space-y-3">
                  {selected.summary && (
                    <Card className="p-5">
                      <p className="text-meta font-medium text-ink">요약</p>
                      <p className="mt-2 whitespace-pre-line text-meta leading-relaxed text-ink-soft">
                        {selected.summary}
                      </p>
                    </Card>
                  )}
                  {selected.covered.length > 0 && (
                    <Card className="p-5">
                      <p className="text-meta font-medium text-ink">다룬 질문</p>
                      <p className="mt-1 font-mono text-2xs text-ink-faint">
                        {selected.covered.length}개 · {selected.covered.join(", ")}
                      </p>
                    </Card>
                  )}
                  <Card className="p-5">
                    <p className="mb-3 flex items-center gap-1.5 text-meta font-medium text-ink">
                      <Mic className="h-4 w-4" aria-hidden="true" />
                      인터뷰 대화 전사
                    </p>
                    {turns === null ? (
                      <div className="space-y-2">
                        <Skeleton className="h-4 w-full" />
                        <Skeleton className="h-4 w-5/6" />
                        <Skeleton className="h-4 w-2/3" />
                      </div>
                    ) : (
                      <TranscriptView turns={turns} />
                    )}
                  </Card>
                </div>
              )}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
