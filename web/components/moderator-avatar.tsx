// 진행자 아바타 — 작은 웜 오브(peach→red 라디얼, design.md §5 "인터뷰(응답자, 웜)"). 말하는 동안
// 살짝 맥동해 "지금 듣고/말하고 있다"는 인상을 준다. 압도하지 않게 소형 — 이모지 아님(design.md §4).
//
// interview-flow.tsx 상단 진행자 라벨 옆에 배선되어 있다(tts.speaking 을 speaking prop 으로 전달).
//
// 맥동은 커스텀 키프레임(.animate-moderator-pulse, globals.css)을 쓴다 — Tailwind 기본
// animate-pulse 는 불투명도 펄스라 오브가 깜빡이며 사라지는 느낌이라 "숨쉬는 오브"엔 안 맞는다.
// prefers-reduced-motion 은 여기서 따로 분기하지 않는다 — globals.css 전역 규칙이 모든
// animation-duration 을 0.01ms 로 낮춰 이미 처리한다(states.tsx 의 Skeleton 과 동일 패턴).
//
// 순수 장식 그래픽이라 aria-hidden — 실제 레이블("진행자")은 이 컴포넌트를 쓰는 쪽의 인접 텍스트가 맡는다.
import { cn } from "@/lib/utils";

export function ModeratorAvatar({
  speaking = false,
  size = 40,
}: {
  /** 진행자가 말하는 중인가 — true 면 오브가 살짝 맥동한다. */
  speaking?: boolean;
  /** 오브 지름(px). 인터뷰 상단처럼 소형으로 쓰는 걸 기본값으로 둔다. */
  size?: number;
}) {
  return (
    <span
      aria-hidden="true"
      className="relative inline-flex shrink-0 items-center justify-center rounded-full"
      style={{ width: size, height: size }}
    >
      {/* 소프트 링 — 오브 밖으로 은은하게 번지는 테두리(design.md §5: 압도하지 않게) */}
      <span className="absolute inset-0 rounded-full ring-2 ring-red/20" />
      {/* 오브 본체 — peach→red 라디얼. peach 스톱은 Furiosa peach 토큰(design.md, #FEC2A0) */}
      <span
        className={cn(
          "absolute inset-[3px] rounded-full",
          speaking && "animate-moderator-pulse",
        )}
        style={{
          background: "radial-gradient(circle at 38% 32%, #FEC2A0, #E21500 90%)",
          boxShadow: "0 2px 10px rgba(226, 21, 0, 0.22)",
        }}
      />
    </span>
  );
}
