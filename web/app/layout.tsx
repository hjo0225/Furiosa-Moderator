import type { Metadata, Viewport } from "next";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: "mindlens — AI 음성 인터뷰",
  description: "주제만 정하면 AI 진행자가 응답자와 1:1 음성 인터뷰를 진행하고, 전사·요약·인사이트까지 정리해 드립니다.",
};

// 모바일 우선 — 응답자는 대부분 휴대폰이다. 입력 포커스 시 자동 확대만 막고 확대 자체는 허용(a11y).
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <head>
        <link
          rel="stylesheet"
          href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css"
        />
      </head>
      <body className="min-h-screen bg-bg text-ink antialiased">{children}</body>
    </html>
  );
}
