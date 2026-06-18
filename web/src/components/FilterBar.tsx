// @TASK T2 - FilterBar 컴포넌트
// @SPEC web/src/lib/queries.ts#BuildingFilter, web/src/lib/types.ts#District
"use client";

import { Search, X } from "lucide-react";
import type { BuildingFilter } from "@/lib/queries";
import { DISTRICT_LABELS } from "@/lib/types";
import type { District } from "@/lib/types";

const DISTRICTS: District[] = ["GBD", "CBD", "YBD", "BBD", "ETC"];

interface FilterBarProps {
  value: BuildingFilter;
  onChange: (next: BuildingFilter) => void;
}

// 만원 입력값 → 원 단위 변환 (예: 20 → 200000)
function manToWon(man: string): number | undefined {
  const n = parseFloat(man);
  if (isNaN(n)) return undefined;
  return Math.round(n * 10000);
}

// 원 단위 → 만원 표시값 변환
function wonToMan(won: number | undefined): string {
  if (won === undefined) return "";
  return String(won / 10000);
}

export default function FilterBar({ value, onChange }: FilterBarProps) {
  const handleDistrict = (district: string | undefined) => {
    onChange({ ...value, district });
  };

  const handleMinRent = (e: React.ChangeEvent<HTMLInputElement>) => {
    onChange({ ...value, minRent: manToWon(e.target.value) });
  };

  const handleMaxRent = (e: React.ChangeEvent<HTMLInputElement>) => {
    onChange({ ...value, maxRent: manToWon(e.target.value) });
  };

  const handleKeyword = (e: React.ChangeEvent<HTMLInputElement>) => {
    onChange({ ...value, keyword: e.target.value || undefined });
  };

  const handleReset = () => {
    onChange({});
  };

  return (
    <div className="flex flex-wrap items-center gap-3 bg-white border border-border rounded-xl px-4 py-3 shadow-sm">
      {/* 권역 선택 */}
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => handleDistrict(undefined)}
          className={[
            "px-3 py-1.5 rounded-md text-sm font-medium transition-colors",
            value.district === undefined
              ? "bg-accent text-white"
              : "bg-gray-100 text-gray-600 hover:bg-gray-200",
          ].join(" ")}
        >
          전체
        </button>
        {DISTRICTS.map((d) => (
          <button
            key={d}
            type="button"
            onClick={() => handleDistrict(d)}
            className={[
              "px-3 py-1.5 rounded-md text-sm font-medium transition-colors",
              value.district === d
                ? "bg-accent text-white"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200",
            ].join(" ")}
          >
            {DISTRICT_LABELS[d]}
          </button>
        ))}
      </div>

      {/* 구분선 */}
      <div className="h-6 w-px bg-border hidden sm:block" />

      {/* 평당 임대료 범위 (만원 단위 입력, 내부 원 단위 저장) */}
      <div className="flex items-center gap-1.5">
        <span className="text-xs text-gray-500 whitespace-nowrap">임대료</span>
        <input
          type="number"
          min={0}
          value={wonToMan(value.minRent)}
          onChange={handleMinRent}
          placeholder="최소"
          className="w-20 px-2 py-1.5 text-sm border border-border rounded focus:outline-none focus:ring-2 focus:ring-accent/30 placeholder:text-gray-400"
        />
        <span className="text-gray-400 text-sm">~</span>
        <input
          type="number"
          min={0}
          value={wonToMan(value.maxRent)}
          onChange={handleMaxRent}
          placeholder="최대"
          className="w-20 px-2 py-1.5 text-sm border border-border rounded focus:outline-none focus:ring-2 focus:ring-accent/30 placeholder:text-gray-400"
        />
        <span className="text-xs text-gray-500">만원</span>
      </div>

      {/* 구분선 */}
      <div className="h-6 w-px bg-border hidden sm:block" />

      {/* 키워드 검색 */}
      <div className="relative flex items-center">
        <Search
          className="absolute left-2.5 text-gray-400 pointer-events-none"
          size={15}
          strokeWidth={2}
        />
        <input
          type="text"
          value={value.keyword ?? ""}
          onChange={handleKeyword}
          placeholder="건물명 또는 주소"
          className="pl-8 pr-3 py-1.5 text-sm border border-border rounded w-44 focus:outline-none focus:ring-2 focus:ring-accent/30 placeholder:text-gray-400"
        />
      </div>

      {/* 초기화 */}
      <button
        type="button"
        onClick={handleReset}
        className="ml-auto flex items-center gap-1 px-3 py-1.5 text-sm text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-md transition-colors"
      >
        <X size={14} strokeWidth={2} />
        초기화
      </button>
    </div>
  );
}
