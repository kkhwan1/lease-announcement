// @TASK T5 - FloorTable 컴포넌트 (층별 공실 테이블)
// @SPEC web/src/lib/types.ts#FloorVacancy, web/src/lib/format.ts
"use client";

import { useState } from "react";
import type { FloorVacancy } from "@/lib/types";
import {
  formatPyeong,
  formatSqm,
  formatRentManwon,
} from "@/lib/format";
import { PillTab } from "@/components/ui/PillTab";

// availability_kind 값 → 표시 문자열
const AVAILABILITY_KIND_LABEL: Record<string, string> = {
  immediate: "즉시",
  negotiable: "협의",
  by_date: "날짜협의",
  unknown: "-",
};

function getAvailabilityLabel(row: FloorVacancy): string {
  if (row.availability_raw) return row.availability_raw;
  if (row.availability_kind && row.availability_kind in AVAILABILITY_KIND_LABEL) {
    return AVAILABILITY_KIND_LABEL[row.availability_kind];
  }
  return "-";
}

interface FloorTableProps {
  floors: FloorVacancy[];
}

type AreaUnit = "pyeong" | "sqm";

// 즉시입주 여부: availability_kind==='immediate' 또는 availability_raw에 '즉시' 포함
function isImmediate(row: FloorVacancy): boolean {
  if (row.availability_kind === "immediate") return true;
  if (row.availability_raw && row.availability_raw.includes("즉시")) return true;
  return false;
}

// 층 정렬: floor_number 내림차순, null이면 floor_label 보조(문자열 내림차순)
function sortByFloor(a: FloorVacancy, b: FloorVacancy): number {
  const aNum = a.floor_number;
  const bNum = b.floor_number;
  if (aNum !== null && bNum !== null) return bNum - aNum;
  if (aNum !== null) return -1; // 숫자 있는 쪽 우선
  if (bNum !== null) return 1;
  // 둘 다 null → floor_label 내림차순
  const aLabel = a.floor_label ?? "";
  const bLabel = b.floor_label ?? "";
  return bLabel.localeCompare(aLabel, "ko");
}

export function FloorTable({ floors }: FloorTableProps) {
  const [unit, setUnit] = useState<AreaUnit>("pyeong");

  if (floors.length === 0) {
    return (
      <div className="flex items-center justify-center py-12 text-body-sm text-stone rounded-xl border border-hairline-soft bg-canvas">
        공실 정보가 없습니다.
      </div>
    );
  }

  // 층 내림차순 정렬 (원본 배열 변경 없이 복사 후 정렬)
  const sorted = [...floors].sort(sortByFloor);

  // 요약 집계
  const totalCount = floors.length;
  const immediateCount = floors.filter(isImmediate).length;

  const formatArea = (pyeong: string | null, sqm: string | null): string => {
    return unit === "pyeong" ? formatPyeong(pyeong) : formatSqm(sqm);
  };

  return (
    <div className="overflow-x-auto rounded-xl border border-hairline-soft bg-canvas">
      {/* 요약 한 줄 */}
      <div className="px-4 py-2 border-b border-hairline-soft bg-surface-soft">
        <span className="text-body-sm text-steel">
          총 공실 {totalCount}개 · 즉시입주 {immediateCount}개
        </span>
      </div>

      {/* 평/㎡ 단위 토글 */}
      <div className="flex justify-end gap-1 px-4 py-3 border-b border-hairline-soft bg-surface-soft">
        <PillTab active={unit === "pyeong"} onClick={() => setUnit("pyeong")}>
          평
        </PillTab>
        <PillTab active={unit === "sqm"} onClick={() => setUnit("sqm")}>
          ㎡
        </PillTab>
      </div>

      {/* 테이블 */}
      <table className="w-full">
        <thead>
          <tr className="bg-surface-soft border-b border-hairline-soft">
            <th className="px-4 py-3 text-left text-body-sm font-bold text-ink whitespace-nowrap">층</th>
            <th className="px-4 py-3 text-right text-body-sm font-bold text-ink whitespace-nowrap">전용면적</th>
            <th className="px-4 py-3 text-right text-body-sm font-bold text-ink whitespace-nowrap">임대면적</th>
            <th className="px-4 py-3 text-center text-body-sm font-bold text-ink whitespace-nowrap">입주</th>
            <th className="px-4 py-3 text-right text-body-sm font-bold text-ink whitespace-nowrap">평당 임대료</th>
            <th className="px-4 py-3 text-right text-body-sm font-bold text-ink whitespace-nowrap">평당 관리비</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-hairline-soft">
          {sorted.map((row, idx) => (
            <tr key={idx} className="hover:bg-surface-soft transition-colors">
              <td className="px-4 py-3 text-body-sm text-charcoal whitespace-nowrap">
                {row.floor_label ?? "-"}
              </td>
              <td className="px-4 py-3 text-right text-body-sm text-charcoal whitespace-nowrap">
                {formatArea(row.exclusive_area_pyeong, row.exclusive_area_sqm)}
              </td>
              <td className="px-4 py-3 text-right text-body-sm text-charcoal whitespace-nowrap">
                {formatArea(row.lease_area_pyeong, row.lease_area_sqm)}
              </td>
              <td className="px-4 py-3 text-center text-body-sm text-charcoal whitespace-nowrap">
                {getAvailabilityLabel(row)}
              </td>
              <td className="px-4 py-3 text-right text-body-sm text-ink-deep font-bold whitespace-nowrap">
                {formatRentManwon(row.rent_per_pyeong)}
              </td>
              <td className="px-4 py-3 text-right text-body-sm text-charcoal whitespace-nowrap">
                {formatRentManwon(row.maintenance_per_pyeong)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
