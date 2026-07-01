// GET /api/news — 부동산 뉴스 피드.
// MVP: 로컬에 뉴스 데이터 없음 → 항상 빈 배열(뉴스 준비중). UI가 빈 상태 처리.
import { NextResponse } from "next/server";
import type { NewsArticle } from "@/lib/types";

export const dynamic = "force-dynamic";

export function GET() {
  const data: NewsArticle[] = [];
  return NextResponse.json(data);
}
