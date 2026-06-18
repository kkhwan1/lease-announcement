import type { Metadata } from "next";
import "./globals.css";
import { SiteHeader } from "@/components/SiteHeader";
import { SiteFooter } from "@/components/SiteFooter";

export const metadata: Metadata = {
  title: {
    default: "오피스 임대매물 검색",
    template: "%s | 오피스 임대매물 검색",
  },
  description:
    "서울 주요 권역 오피스 임대매물을 지도와 목록으로 한눈에. 층별 공실, 임대료, 건물 정보를 제공합니다.",
  keywords: ["오피스 임대", "사무실 임대", "공실", "강남 오피스", "여의도 오피스", "임대료"],
  openGraph: {
    title: "오피스 임대매물 검색",
    description:
      "서울 주요 권역 오피스 임대매물을 지도와 목록으로 한눈에.",
    type: "website",
    locale: "ko_KR",
  },
  robots: { index: true, follow: true },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko" className="h-full">
      <head>
        <link
          rel="stylesheet"
          href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css"
        />
      </head>
      <body className="min-h-full flex flex-col bg-background text-foreground">
        <SiteHeader />
        <main className="flex-1">{children}</main>
        <SiteFooter />
      </body>
    </html>
  );
}
