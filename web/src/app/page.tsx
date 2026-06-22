"use client";

// 홈 = 지도+리스트 분할 (메인 탐색). 좌: 필터+카드 리스트 / 우: 카카오 지도.
import { useEffect, useMemo, useState } from "react";
import { Plus, Minus } from "lucide-react";
import FilterBar from "@/components/FilterBar";
import { BuildingList } from "@/components/BuildingList";
import KakaoMap from "@/components/KakaoMap";
import {
  fetchBuildingSummaries,
  fetchMapPins,
  type BuildingFilter,
} from "@/lib/queries";
import type { BuildingSummary, BuildingMapPin } from "@/lib/types";

export default function HomePage() {
  const [filter, setFilter] = useState<BuildingFilter>({});
  const [buildings, setBuildings] = useState<BuildingSummary[]>([]);
  const [allPins, setAllPins] = useState<BuildingMapPin[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 지도 핀: 최초 1회 전체 로드
  useEffect(() => {
    fetchMapPins()
      .then(setAllPins)
      .catch((e) => console.error("지도 핀 로드 실패:", e));
  }, []);

  // 카드 리스트: 필터 변경 시 재조회 (디바운스)
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const t = setTimeout(() => {
      fetchBuildingSummaries(filter)
        .then((rows) => {
          if (cancelled) return;
          setBuildings(rows);
          setError(null);
        })
        .catch((e) => {
          if (cancelled) return;
          console.error(e);
          setError("매물을 불러오지 못했습니다.");
        })
        .finally(() => !cancelled && setLoading(false));
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [filter]);

  // 현재 필터 결과에 해당하는 핀만 지도에 표시 (리스트와 동기화)
  const visiblePins = useMemo(() => {
    const ids = new Set(buildings.map((b) => b.building_id));
    return allPins.filter((p) => ids.has(p.building_id));
  }, [allPins, buildings]);

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      <div className="border-b border-hairline-soft bg-canvas px-4 py-3">
        <FilterBar value={filter} onChange={setFilter} />
      </div>
      <div className="flex flex-1 overflow-hidden">
        {/* 좌: 리스트 */}
        <div className="flex w-full flex-col border-r border-hairline-soft md:w-[440px] lg:w-[520px]">
          <div className="border-b border-hairline-soft px-4 py-2 text-body-sm text-steel">
            {loading
              ? "불러오는 중..."
              : error
                ? error
                : `매물 ${buildings.length.toLocaleString()}건`}
          </div>
          <div className="flex-1 overflow-y-auto">
            <BuildingList
              buildings={buildings}
              selectedId={selectedId}
              onHover={setSelectedId}
            />
          </div>
        </div>
        {/* 우: 지도 (모바일에서는 숨김) */}
        <div className="relative hidden flex-1 md:block">
          <KakaoMap
            pins={visiblePins}
            selectedId={selectedId}
            onSelectPin={setSelectedId}
          />
          {/* 지도 위 매물 수 chip */}
          <div className="absolute left-4 top-4 z-10 rounded-full bg-canvas/95 px-4 py-2 text-body-sm font-bold text-ink-deep shadow-elev2">
            매물 {buildings.length}건
          </div>
          {/* 지도 줌 컨트롤 (시각 chrome — TODO: wire zoom via KakaoMap ref) */}
          <div className="absolute bottom-6 right-6 z-10 flex flex-col gap-2">
            <button
              aria-label="지도 확대"
              onClick={() => {
                // TODO: wire zoom via KakaoMap ref
              }}
              className="flex h-10 w-10 items-center justify-center rounded-full bg-canvas text-ink shadow-elev2"
            >
              <Plus size={18} strokeWidth={2} aria-hidden />
            </button>
            <button
              aria-label="지도 축소"
              onClick={() => {
                // TODO: wire zoom via KakaoMap ref
              }}
              className="flex h-10 w-10 items-center justify-center rounded-full bg-canvas text-ink shadow-elev2"
            >
              <Minus size={18} strokeWidth={2} aria-hidden />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
