import { Card } from "@/components/shared";
import type { BenchmarkResult } from "@/lib/api";

import { fmtStr } from "./format";

// 부록 · 실행 메타데이터 — 계측 스펙 §4 "실행 메타데이터"(재현성). 자동 생성 값을 그대로
// 보여주기만 한다 — 모르는 값은 `—`(스펙 §8: 추정 금지).
export function RunMetadataAppendix({ result }: { result: BenchmarkResult }) {
  const { meta } = result;
  const items: Array<[string, string | null]> = [
    ["SDK 버전", meta.sdk_version],
    ["펌웨어", meta.firmware_version],
    ["드라이버", meta.driver_version],
    ["양자화", meta.quantization],
    ["governor", meta.governor],
    ["prefix caching", meta.prefix_caching],
    ["tensor parallel", meta.tensor_parallel_size],
    ["코퍼스 해시", meta.corpus_hash],
    ["프롬프트 템플릿 해시", meta.prompt_template_hash],
    ["캐시 히트율", meta.cache_hit_rate],
    ["코드 리비전", meta.code_revision],
    ["측정 시각", result.measured_at],
  ];

  return (
    <Card as="section" className="bg-paper p-6 shadow-none">
      <p className="eyebrow">부록 · 실행 메타데이터</p>
      <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-3 text-meta sm:grid-cols-3">
        {items.map(([label, value]) => (
          <div key={label} className="min-w-0">
            <dt className="text-2xs text-grey">{label}</dt>
            <dd className="truncate font-telemetry text-obsidian" title={fmtStr(value)}>
              {fmtStr(value)}
            </dd>
          </div>
        ))}
      </dl>
      {/* 모델 배치 — 스펙 §5. 역할별 모델이 다르면 수치를 같은 표에서 비교할 수 없어
          화면에 항상 적는다(2026-07-23 런은 전 역할 8B 였다). */}
      <div className="mt-4 border-t border-platinum pt-3">
        <p className="text-2xs text-grey">모델 배치 (역할별)</p>
        {result.model_placement.length === 0 ? (
          <p className="mt-1 font-telemetry text-meta text-obsidian">—</p>
        ) : (
          <dl className="mt-1.5 space-y-1">
            {result.model_placement.map((m) => (
              <div key={m.role} className="flex flex-wrap gap-x-2 text-2xs">
                <dt className="text-grey">{m.role}</dt>
                <dd className="font-telemetry text-obsidian">{m.model}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>

      <p className="mt-4 border-t border-platinum pt-3 text-2xs text-grey">
        데이터 소스 · furiosa-smi 카드 센서 1s · furiosa-metrics-exporter → Prometheus ·
        furiosa-llm /metrics · NTP 100ms 이내 동기
      </p>
    </Card>
  );
}
