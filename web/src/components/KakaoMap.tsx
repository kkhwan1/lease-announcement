// @TASK T-map - 카카오맵 컴포넌트
// @SPEC docs/planning — 지도 핀 표시, 마커 클러스터, selectedId 강조
"use client";

import { useEffect, useRef, useState } from "react";
import { BuildingMapPin } from "@/lib/types";
import { formatRentManwon } from "@/lib/format";

// 카카오 SDK 타입: SDK 공식 타입 패키지 없음, any로 최소 선언
declare global {
  interface Window {
    kakao: any;
  }
}

interface KakaoMapProps {
  pins: BuildingMapPin[];
  selectedId?: string | null;
  onSelectPin?: (buildingId: string) => void;
}

// 서울 중심 좌표
const SEOUL_LAT = 37.5665;
const SEOUL_LNG = 126.9780;
const INITIAL_LEVEL = 8;

// 기본 마커 이미지 크기
const MARKER_SIZE = { width: 24, height: 35 };
// 선택된 마커 이미지 크기 (강조)
const SELECTED_MARKER_SIZE = { width: 32, height: 46 };

export default function KakaoMap({ pins, selectedId, onSelectPin }: KakaoMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  // pin 데이터를 marker와 함께 보관하여 selectedId 이펙트에서 rent/vacancy 조회 가능
  const markersRef = useRef<{ id: string; marker: any; pin: BuildingMapPin }[]>([]);
  const clustererRef = useRef<any>(null);
  const overlaysRef = useRef<any[]>([]);
  const isInitializedRef = useRef(false);
  const [loadFailed, setLoadFailed] = useState(false);

  const apiKey = process.env.NEXT_PUBLIC_KAKAO_JS_KEY;

  // 선택된 핀의 CustomOverlay pill 제거
  function clearSelectedOverlay() {
    overlaysRef.current.forEach((overlay) => overlay.setMap(null));
    overlaysRef.current = [];
  }

  // 선택된 핀 위에 표시할 pill DOM 엘리먼트 생성
  function buildPillElement(pin: BuildingMapPin, selected: boolean): HTMLElement {
    const el = document.createElement("div");
    el.className = selected ? "map-pill map-pill--selected" : "map-pill";

    if (pin.min_rent_per_pyeong != null) {
      el.textContent = formatRentManwon(pin.min_rent_per_pyeong) + "/평";
    } else {
      el.textContent = `공실 ${pin.vacancy_count}`;
    }

    el.addEventListener("click", () => {
      onSelectPin?.(pin.building_id);
    });

    return el;
  }

  // 마커 이미지 생성 헬퍼
  function createMarkerImage(kakao: any, selected: boolean) {
    const size = selected ? SELECTED_MARKER_SIZE : MARKER_SIZE;
    return new kakao.maps.MarkerImage(
      selected
        ? "https://t1.daumcdn.net/localimg/localimages/07/mapapidoc/markerStar.png"
        : "https://t1.daumcdn.net/localimg/localimages/07/mapapidoc/marker_red.png",
      new kakao.maps.Size(size.width, size.height)
    );
  }

  // 마커 및 클러스터 전체 정리 (overlay도 함께 정리)
  function clearMarkers() {
    clearSelectedOverlay();
    if (clustererRef.current) {
      clustererRef.current.clear();
    }
    markersRef.current.forEach(({ marker }) => marker.setMap(null));
    markersRef.current = [];
  }

  // 핀 배열로 마커 생성
  function buildMarkers(kakao: any, map: any, pinList: BuildingMapPin[], currentSelectedId?: string | null) {
    clearMarkers();

    const newMarkers = pinList.map((pin) => {
      const isSelected = pin.building_id === currentSelectedId;
      const markerImage = createMarkerImage(kakao, isSelected);

      const marker = new kakao.maps.Marker({
        position: new kakao.maps.LatLng(pin.latitude, pin.longitude),
        image: markerImage,
        title: pin.name,
      });

      kakao.maps.event.addListener(marker, "click", () => {
        onSelectPin?.(pin.building_id);
      });

      // pin을 함께 저장하여 selectedId 이펙트에서 rent/vacancy 조회 가능
      return { id: pin.building_id, marker, pin };
    });

    markersRef.current = newMarkers;

    // 클러스터러에 마커 추가
    if (clustererRef.current) {
      clustererRef.current.addMarkers(newMarkers.map((m) => m.marker));
    } else {
      newMarkers.forEach(({ marker }) => marker.setMap(map));
    }
  }

  // 카카오맵 SDK 동적 로드 및 초기화
  useEffect(() => {
    if (isInitializedRef.current) return;
    if (!containerRef.current) return;

    const scriptId = "kakao-map-sdk";

    function initMap() {
      const kakao = window.kakao;
      kakao.maps.load(() => {
        const map = new kakao.maps.Map(containerRef.current!, {
          center: new kakao.maps.LatLng(SEOUL_LAT, SEOUL_LNG),
          level: INITIAL_LEVEL,
        });
        mapRef.current = map;

        // 클러스터러 초기화
        clustererRef.current = new kakao.maps.MarkerClusterer({
          map,
          averageCenter: true,
          minLevel: 5,
          disableClickZoom: false,
        });

        buildMarkers(kakao, map, pins, selectedId);
        isInitializedRef.current = true;
      });
    }

    // 이미 스크립트가 로드됐으면 바로 초기화
    if (window.kakao && window.kakao.maps) {
      initMap();
      return;
    }

    if (document.getElementById(scriptId)) {
      // 스크립트 태그는 있지만 아직 로드 중 — load 이벤트 대기
      const existing = document.getElementById(scriptId) as HTMLScriptElement;
      existing.addEventListener("load", initMap);
      return () => existing.removeEventListener("load", initMap);
    }

    // 키가 없으면 주입하지 않음 (placeholder 렌더)
    if (!apiKey) return;

    // 스크립트 태그 동적 주입
    const script = document.createElement("script");
    script.id = scriptId;
    script.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${apiKey}&autoload=false&libraries=clusterer`;
    script.async = true;
    script.onload = initMap;
    // 로드 실패(도메인 미등록/네트워크) 시 placeholder로 폴백
    script.onerror = () => setLoadFailed(true);
    document.head.appendChild(script);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // pins 변경 시 마커 재생성
  useEffect(() => {
    if (!isInitializedRef.current || !mapRef.current || !window.kakao) return;
    buildMarkers(window.kakao, mapRef.current, pins, selectedId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pins]);

  // selectedId 변경 시 강조 + panTo + pill overlay
  useEffect(() => {
    if (!isInitializedRef.current || !mapRef.current || !window.kakao) return;

    const kakao = window.kakao;

    // 모든 마커 이미지 초기화
    markersRef.current.forEach(({ id, marker }) => {
      marker.setImage(createMarkerImage(kakao, id === selectedId));
    });

    // 기존 overlay 제거
    clearSelectedOverlay();

    // panTo + 선택된 핀 위에 pill overlay 추가
    if (selectedId) {
      const target = markersRef.current.find((m) => m.id === selectedId);
      if (target) {
        mapRef.current.panTo(target.marker.getPosition());

        const overlay = new kakao.maps.CustomOverlay({
          position: target.marker.getPosition(),
          content: buildPillElement(target.pin, true),
          yAnchor: 1.0,
          clickable: true,
          zIndex: 10,
        });
        overlay.setMap(mapRef.current);
        overlaysRef.current.push(overlay);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  // 키 없음 또는 로드 실패 시 placeholder (앱은 정상 동작, 리스트는 그대로)
  if (!apiKey || loadFailed) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-surface-soft rounded-xxxl p-6 text-center">
        <p className="text-body-sm text-steel">
          {!apiKey
            ? "카카오맵 키를 설정하면 지도가 표시됩니다."
            : "지도를 불러오지 못했습니다. 카카오 개발자 콘솔에서 사이트 도메인(http://localhost:3000) 등록을 확인해 주세요."}
        </p>
      </div>
    );
  }

  return <div ref={containerRef} className="h-full w-full" />;
}
