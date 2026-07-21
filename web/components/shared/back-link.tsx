import Link from "next/link";

import { cn } from "@/lib/utils";
import { buttonVariants } from "./button";

// 뒤로가기·브레드크럼 링크 — 디자인시스템 ghost 버튼으로 통일(화살표 + 라벨).
// -ml-3 으로 버튼 좌측 패딩만큼 당겨, 라벨이 콘텐츠 좌측선에 맞게 정렬된다.
export function BackLink({
  href,
  children,
  className,
}: {
  href: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Link
      href={href}
      className={cn(buttonVariants({ variant: "ghost", size: "sm" }), "-ml-3", className)}
    >
      <span aria-hidden="true">←</span>
      {children}
    </Link>
  );
}
