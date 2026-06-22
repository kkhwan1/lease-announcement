// @TASK T2 - FilterBar 컴포넌트
// @SPEC web/src/lib/queries.ts#BuildingFilter, web/src/lib/types.ts#District
"use client";

import { X } from "lucide-react";
import type { BuildingFilter } from "@/lib/queries";
import { DISTRICT_LABELS } from "@/lib/types";
import type { District } from "@/lib/types";
import { PillTab } from "@/components/ui/PillTab";
import { Input } from "@/components/ui/Input";
import { SearchPill } from "@/components/ui/SearchPill";
import { Button } from "@/components/ui/Button";

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
    <div className="flex flex-wrap items-center gap-3 bg-canvas border border-hairline-soft rounded-xl px-4 py-3 shadow-elev1">
      {/* 권역 선택 */}
      <div className="flex items-center gap-1">
        <PillTab
          active={value.district === undefined}
          onClick={() => handleDistrict(undefined)}
        >
          전체
        </PillTab>
        {DISTRICTS.map((d) => (
          <PillTab
            key={d}
            active={value.district === d}
            onClick={() => handleDistrict(d)}
          >
            {DISTRICT_LABELS[d]}
          </PillTab>
        ))}
      </div>

      {/* 구분선 */}
      <div className="h-6 w-px bg-hairline-soft hidden sm:block" />

      {/* 평당 임대료 범위 (만원 단위 입력, 내부 원 단위 저장) */}
      <div className="flex items-center gap-1.5">
        <span className="text-caption text-steel whitespace-nowrap">임대료</span>
        <Input
          type="number"
          min={0}
          value={wonToMan(value.minRent)}
          onChange={handleMinRent}
          placeholder="최소"
          className="w-20"
        />
        <span className="text-steel text-body-sm">~</span>
        <Input
          type="number"
          min={0}
          value={wonToMan(value.maxRent)}
          onChange={handleMaxRent}
          placeholder="최대"
          className="w-20"
        />
        <span className="text-caption text-steel">만원</span>
      </div>

      {/* 구분선 */}
      <div className="h-6 w-px bg-hairline-soft hidden sm:block" />

      {/* 키워드 검색 */}
      <SearchPill
        value={value.keyword ?? ""}
        onChange={handleKeyword}
        placeholder="건물명 또는 주소"
        className="w-44"
      />

      {/* 초기화 */}
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={handleReset}
        className="ml-auto flex items-center gap-1"
      >
        <X size={14} strokeWidth={2} />
        초기화
      </Button>
    </div>
  );
}
