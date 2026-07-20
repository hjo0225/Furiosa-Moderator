/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Cloud Run 용 — node_modules 를 통째로 싣지 않고 필요한 것만 묶는다.
  output: "standalone",
  // _reference/ 는 "읽고 다시 짜는" 참고본이라 빌드에서 제외한다(tsconfig exclude 와 짝).
  eslint: { ignoreDuringBuilds: true },
};

module.exports = nextConfig;
