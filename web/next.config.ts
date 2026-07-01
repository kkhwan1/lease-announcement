import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 로컬 SQLite(data/lease.db)를 /api 라우트 서버리스 번들에 포함.
  // 코드가 import하지 않는 데이터 파일이라 명시하지 않으면 Vercel 빌드에서 제외됨.
  outputFileTracingIncludes: {
    "/api/**": ["./data/lease.db"],
  },
};

export default nextConfig;
