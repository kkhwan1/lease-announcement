// @TASK T2 - BuildingList 컴포넌트
// @SPEC web/src/lib/types.ts (BuildingSummary)

import { BuildingSummary } from "@/lib/types";
import { BuildingCard } from "./BuildingCard";

interface BuildingListProps {
  buildings: BuildingSummary[];
  selectedId?: string | null;
  onHover?: (id: string | null) => void;
}

export function BuildingList({ buildings, selectedId, onHover }: BuildingListProps) {
  if (buildings.length === 0) {
    return (
      <div className="flex h-full items-center justify-center py-16 text-body-sm text-steel">
        조건에 맞는 매물이 없습니다
      </div>
    );
  }

  return (
    <ul className="flex flex-col gap-3 overflow-y-auto">
      {buildings.map((building) => (
        <li key={building.building_id}>
          <BuildingCard
            building={building}
            selected={selectedId === building.building_id}
            onHover={onHover}
          />
        </li>
      ))}
    </ul>
  );
}
