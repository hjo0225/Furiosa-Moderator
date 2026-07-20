// 인앱 브라우저 감지 — 카톡 등 인앱 웹뷰는 구글 OAuth(정책 차단)·마이크(getUserMedia 미노출)가
// 막혀 응답 자체가 불가하다. 이를 감지해 "외부 브라우저로 여세요" 안내(브릿지)를 띄운다.
//
// 감지는 **화이트리스트(확진 토큰)만** 쓴다 — "정식 브라우저가 아니면 인앱"식 denylist 는
// 삼성인터넷·웨일·PWA·크롬 커스텀탭을 오탐해 정상 사용자를 잠근다(council 리스크 렌즈). 그래서
// 잡을 수 있는 인앱만 명시적으로 잡고, 애매하면 통과시킨다(빈 값·미상 = false).

// 확진 인앱 토큰만. 카톡이 1순위, 나머지는 국내 주요 인앱(마이크·OAuth 동일 제약).
const IN_APP_TOKENS: RegExp[] = [
  /KAKAOTALK/i, // 카카오톡 (구 iOS 는 소문자 kakaotalk 도 있어 대소문자 무시)
  /NAVER\(inapp/i, // 네이버 앱 인앱
  /DaumApps/i, // 다음 앱
  /\bLine\//i, // 라인
  /Instagram/i, // 인스타그램
  /FBAN|FBAV|FB_IAB/, // 페이스북(iOS/Android 인앱)
];

/** UA 가 알려진 인앱 브라우저인가 — 확진 토큰만 매칭(오탐 방지). 빈 값/미상은 false. */
export function isInAppBrowser(ua: string | undefined | null): boolean {
  if (!ua) return false;
  return IN_APP_TOKENS.some((re) => re.test(ua));
}
