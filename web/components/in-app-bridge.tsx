"use client";

// 카톡 등 인앱 브라우저 안내 브릿지 — 응답자 경로(survey-public) 전체를 감싸는 layout 에서 mount.
// 인앱 웹뷰는 구글 로그인(OAuth 정책 차단)·마이크(getUserMedia 미노출)가 막혀 응답이 불가하다.
// 감지되면 "링크 복사 → 크롬/사파리에서 열기"를 안내한다(링크 복사가 OS 메뉴 위치 편차를 우회하는 확실한 경로).

import { useEffect, useState } from "react";
import { Check, Globe } from "lucide-react";

import { Button, Card } from "@/components/shared";
import { isInAppBrowser } from "@/lib/in-app-browser";

export function InAppBridge() {
  const [show, setShow] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (typeof navigator === "undefined") return;
    if (isInAppBrowser(navigator.userAgent)) setShow(true);
  }, []);

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2500);
    } catch {
      // clipboard 불가 — 주소창에서 직접 복사하도록.
      setCopied(false);
    }
  }

  if (!show) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="브라우저 변경 안내"
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-5"
    >
      <Card className="w-full max-w-sm p-6 text-center">
        <div className="flex justify-center text-ink">
          <Globe className="h-9 w-9" aria-hidden="true" />
        </div>
        <h2 className="mt-3 text-lg font-bold text-ink">브라우저를 변경해 주세요</h2>
        <p className="mt-0.5 text-sm font-medium text-ink-soft">Please open in another browser</p>
        <p className="mt-3 text-sm leading-relaxed text-ink-soft">
          카카오톡 안에서는 로그인·음성 답변이 막혀요.
          <br />
          링크를 복사해 <b className="text-ink">크롬·사파리</b>에서 열어주세요.
        </p>
        <p className="mt-2 text-xs leading-relaxed text-ink-soft">
          Login and voice answers are blocked in this in-app browser.
          <br />
          Copy the link and open it in <b className="text-ink">Chrome / Safari</b>.
        </p>
        <Button type="button" onClick={copyLink} className="mt-5 w-full">
          {copied && <Check className="h-4 w-4" aria-hidden="true" />}
          {copied ? "복사됨 / Copied" : "링크 복사하기 / Copy link"}
        </Button>
      </Card>
    </div>
  );
}
