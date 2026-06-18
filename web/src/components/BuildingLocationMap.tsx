// 건물 상세 전용 단일 위치 지도. 카카오맵에 해당 건물 1개만 마커로 표시.
// SDK 동적 로드 패턴은 KakaoMap.tsx에서 차용(스크립트 주입·window.kakao 체크·
// autoload=false·onerror placeholder). 리스트용 클러스터러/클릭핸들러는 불필요해 제외.
"use client";

import { useEffect, useRef, useState } from "react";

declare global {
  interface Window {
    kakao: any;
  }
}

interface BuildingLocationMapProps {
  latitude: number | null;
  longitude: number | null;
  name: string;
}

// 단일 건물 표시용 확대 레벨 (동네 수준). KakaoMap 리스트는 8(서울 전체).
const DETAIL_LEVEL = 3;

export function BuildingLocationMap({
  latitude,
  longitude,
  name,
}: BuildingLocationMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const isInitializedRef = useRef(false);
  const [loadFailed, setLoadFailed] = useState(false);

  const apiKey = process.env.NEXT_PUBLIC_KAKAO_JS_KEY;
  const hasCoords = latitude != null && longitude != null;

  useEffect(() => {
    if (isInitializedRef.current) return;
    if (!containerRef.current || !hasCoords) return;

    const scriptId = "kakao-map-sdk"; // KakaoMap과 동일 ID 공유 (중복 주입 방지)

    function initMap() {
      const kakao = window.kakao;
      kakao.maps.load(() => {
        const center = new kakao.maps.LatLng(latitude, longitude);
        const map = new kakao.maps.Map(containerRef.current!, {
          center,
          level: DETAIL_LEVEL,
        });
        new kakao.maps.Marker({ position: center, map, title: name });
        isInitializedRef.current = true;
      });
    }

    // 이미 로드됨 — 바로 초기화
    if (window.kakao && window.kakao.maps) {
      initMap();
      return;
    }

    // 스크립트 태그는 있지만 로드 중 — load 이벤트 대기
    const existing = document.getElementById(scriptId) as HTMLScriptElement | null;
    if (existing) {
      existing.addEventListener("load", initMap);
      return () => existing.removeEventListener("load", initMap);
    }

    // 키 없으면 주입 안 함 (placeholder)
    if (!apiKey) return;

    const script = document.createElement("script");
    script.id = scriptId;
    script.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${apiKey}&autoload=false`;
    script.async = true;
    script.onload = initMap;
    script.onerror = () => setLoadFailed(true);
    document.head.appendChild(script);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 좌표 없음 — 안내 placeholder (앱은 정상 동작)
  if (!hasCoords) {
    return (
      <div className="flex h-64 w-full items-center justify-center rounded-xxxl bg-surface-soft p-6 text-center">
        <p className="text-body-sm text-steel">위치 정보가 준비되지 않았습니다.</p>
      </div>
    );
  }

  // 키 없음 또는 로드 실패 — placeholder
  if (!apiKey || loadFailed) {
    return (
      <div className="flex h-64 w-full items-center justify-center rounded-xxxl bg-surface-soft p-6 text-center">
        <p className="text-body-sm text-steel">
          {!apiKey
            ? "카카오맵 키를 설정하면 지도가 표시됩니다."
            : "지도를 불러오지 못했습니다."}
        </p>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="h-64 w-full overflow-hidden rounded-xxxl border border-hairline-soft"
    />
  );
}
