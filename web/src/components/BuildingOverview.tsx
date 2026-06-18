// @TASK T7 - BuildingOverview + 특장점 섹션
// @SPEC web/src/lib/types.ts (BuildingDetail, DISTRICT_LABELS)
// @SPEC web/src/lib/format.ts (formatFloors, formatSqm, formatPyeong, formatPercent, toNum)

import { BuildingDetail, DISTRICT_LABELS } from "@/lib/types";
import {
  formatFloors,
  formatSqm,
  formatPyeong,
  formatPercent,
  toNum,
} from "@/lib/format";
import { Card } from "@/components/ui/Card";

interface BuildingOverviewProps {
  detail: BuildingDetail;
  // 렌더할 부분 선택. "overview"=건물 개요 카드만(상단 우측 칼럼용),
  // "registry"=건축물대장+특장점(상단 아래 전폭용). 생략 시 전체.
  section?: "overview" | "registry";
}

/** 라벨:값 한 행. value가 null/빈문자열/"-"이면 렌더하지 않음. */
function DefinitionRow({ label, value }: { label: string; value: string | null }) {
  if (value === null || value.trim() === "" || value === "-") return null;
  return (
    <div className="flex gap-2 py-1.5">
      <dt className="w-24 shrink-0 text-body-sm font-bold text-ink">{label}</dt>
      <dd className="text-body-sm text-charcoal">{value}</dd>
    </div>
  );
}

/** 섹션 카드 래퍼 */
function SectionCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Card variant="flat" as="section">
      <h2 className="mb-3 text-heading-sm text-ink-deep">{title}</h2>
      <dl className="divide-y divide-hairline-soft">{children}</dl>
    </Card>
  );
}

export function BuildingOverview({ detail, section }: BuildingOverviewProps) {
  const {
    address_road,
    district,
    completed_year,
    floors_above,
    floors_below,
    gross_area_sqm,
    gross_area_pyeong,
    efficiency_ratio,
    parking_total,
    ceiling_height_m,
    ev_count,
    main_purpose,
    building_coverage_ratio,
    floor_area_ratio,
    height_m,
    land_area_sqm,
    use_zone,
    features_raw,
  } = detail;

  // 연면적: sqm / 평 병기
  const areaDisplay = (() => {
    const sqm = formatSqm(gross_area_sqm);
    const pyeong = formatPyeong(gross_area_pyeong);
    if (sqm === "-" && pyeong === "-") return null;
    if (sqm === "-") return pyeong;
    if (pyeong === "-") return sqm;
    return `${sqm} / ${pyeong}`;
  })();

  // 건축물대장 섹션: 값이 하나라도 있을 때만 렌더 (빈 문자열은 값 없음으로 취급)
  const hasText = (v: string | null) => v !== null && v.trim() !== "";
  const hasBuildingRegistry =
    hasText(main_purpose) ||
    toNum(building_coverage_ratio) !== null ||
    toNum(floor_area_ratio) !== null ||
    toNum(height_m) !== null ||
    toNum(land_area_sqm) !== null ||
    hasText(use_zone);

  // 1. 건물 개요 카드 (상단 우측 칼럼)
  const overviewCard = (
    <SectionCard title="건물 개요">
      <DefinitionRow label="주소" value={address_road} />
      <DefinitionRow
        label="권역"
        value={district !== null ? DISTRICT_LABELS[district] : null}
      />
      <DefinitionRow
        label="준공"
        value={completed_year !== null ? `${completed_year}년` : null}
      />
      <DefinitionRow
        label="규모"
        value={formatFloors(floors_above, floors_below)}
      />
      <DefinitionRow label="연면적" value={areaDisplay} />
      <DefinitionRow label="전용률" value={formatPercent(efficiency_ratio)} />
      <DefinitionRow
        label="주차"
        value={parking_total !== null ? `${parking_total}대` : null}
      />
      <DefinitionRow
        label="천정고"
        value={ceiling_height_m !== null ? `${ceiling_height_m}m` : null}
      />
      <DefinitionRow
        label="승강기"
        value={ev_count !== null ? `${ev_count}대` : null}
      />
    </SectionCard>
  );

  // 2. 건축물대장 카드 (모두 null이면 생략)
  const registryCard = hasBuildingRegistry ? (
    <SectionCard title="건축물대장">
      <DefinitionRow label="주용도" value={main_purpose} />
      <DefinitionRow
        label="건폐율"
        value={formatPercent(building_coverage_ratio)}
      />
      <DefinitionRow label="용적률" value={formatPercent(floor_area_ratio)} />
      <DefinitionRow
        label="높이"
        value={height_m !== null ? `${height_m}m` : null}
      />
      <DefinitionRow label="대지면적" value={formatSqm(land_area_sqm)} />
      <DefinitionRow label="용도지역" value={use_zone} />
    </SectionCard>
  ) : null;

  // 3. 건물 특장점 카드 (features_raw 있을 때만)
  const featuresCard =
    features_raw !== null && features_raw.trim() !== "" ? (
      <Card variant="flat" as="section">
        <h2 className="mb-3 text-heading-sm text-ink-deep">건물 특장점</h2>
        <p className="whitespace-pre-line text-body-md text-charcoal">
          {features_raw}
        </p>
      </Card>
    ) : null;

  // section="overview" — 건물 개요만 (상단 2단 우측 칼럼)
  if (section === "overview") {
    return overviewCard;
  }

  // section="registry" — 건축물대장 + 특장점 (상단 아래 전폭, 2열)
  if (section === "registry") {
    if (!registryCard && !featuresCard) return null;
    return (
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {registryCard}
        {featuresCard}
      </div>
    );
  }

  // 기본(미지정) — 전체 (하위호환): 개요|대장 2열 + 특장점 전폭
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {overviewCard}
        {registryCard}
      </div>
      {featuresCard}
    </div>
  );
}
