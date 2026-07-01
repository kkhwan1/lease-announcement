// GET /api/buildings/[id] — 건물 상세 번들(detail+floors+rents).
// 조회 로직은 lib/buildingDetail.ts(서버 전용) 공유. 상세 페이지(RSC)는 이 API를
// 거치지 않고 그 모듈을 직접 호출한다(self-fetch 제거 — Vercel 배포URL SSO 회피).
import { NextResponse, type NextRequest } from "next/server";
import { getBuildingDetailBundle } from "@/lib/buildingDetail";

export const dynamic = "force-dynamic";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params; // Next.js 16: params는 Promise
  return NextResponse.json(getBuildingDetailBundle(id));
}
