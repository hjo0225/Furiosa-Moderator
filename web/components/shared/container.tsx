import { cn } from "@/lib/utils";

/** 콘텐츠 최대폭 래퍼 */
export function Container({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("mx-auto w-full max-w-content px-6 md:px-10", className)}>{children}</div>
  );
}
