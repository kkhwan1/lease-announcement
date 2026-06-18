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

export function FloorTable({ floors }: FloorTableProps) {
  const [unit, setUnit] = useState<AreaUnit>("pyeong");

  if (floors.length === 0) {
    return (
      <div className="flex items-center justify-center py-12 text-body-sm text-stone rounded-xl border border-hairline-soft bg-canvas">
        공실 정보가 없습니다.
      </div>
    );
  }

  const formatArea = (pyeong: string | null, sqm: string | null): string => {
    return unit === "pyeong" ? formatPyeong(pyeong) : formatSqm(sqm);
  };

  return (
    <div className="overflow-x-auto rounded-xl border border-hairline-soft bg-canvas">
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
          {floors.map((row, idx) => (
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
