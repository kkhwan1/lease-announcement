// 발달상권 + 거주인구 섹션 — BDS Planet 스타일 원형 차트(도넛) + 막대 시각화.
// 데이터 없으면 렌더링 안 함. 이모지 금지, 디자인 토큰만 사용. Recharts(client).
"use client";

import { useState } from "react";
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Label,
  LabelList,
} from "recharts";
import type { CommercialArea, IndustryCount } from "@/lib/types";
import { Card } from "@/components/ui/Card";
import { PillTab } from "@/components/ui/PillTab";
import { SectionHeading } from "@/components/ui/SectionHeading";

interface CommercialAreaSectionProps {
  data: CommercialArea | null;
}

// Recharts는 SVG 내부에서 CSS 변수를 못 읽으므로 색 리터럴(globals.css와 동기화).
const COBALT = "#0064E0"; // primary
const STEEL = "#7A8C99"; // steel
const INK = "#344854"; // ink
const COBALT_DEEP = "#0143B5"; // primary-deep
const STONE = "#A8B4BD"; // stone
const SURFACE = "#F1F4F8"; // surface-soft

// 도넛 차트용 범례 한 줄
function LegendRow({
  color,
  label,
  count,
  pct,
  unit = "개",
}: {
  color: string;
  label: string;
  count: number;
  pct: number;
  unit?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5">
      <div className="flex items-center gap-2">
        <span
          className="inline-block h-3 w-3 shrink-0 rounded-sm"
          style={{ backgroundColor: color }}
        />
        <span className="text-body-sm font-bold text-ink">{label}</span>
      </div>
      <span className="text-body-sm text-steel">
        {count.toLocaleString()}{unit} · {pct}%
      </span>
    </div>
  );
}

interface DonutTooltipPayload {
  payload: { name: string; value: number; pct: number };
}
function DonutTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: DonutTooltipPayload[];
}) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded-lg border border-hairline-soft bg-canvas px-3 py-2 text-body-sm shadow-elev2">
      <p className="font-bold text-ink-deep">{p.name}</p>
      <p className="text-steel">
        {p.value.toLocaleString()}개 · {p.pct}%
      </p>
    </div>
  );
}

// 직장인구 업종 분포 — 사업장수/종사자수 토글 가로 막대.
function WorkplaceIndustryChart({
  byBiz,
  byEmp,
}: {
  byBiz: IndustryCount[] | null;
  byEmp: IndustryCount[] | null;
}) {
  const [mode, setMode] = useState<"biz" | "emp">("biz");
  const list = (mode === "biz" ? byBiz : byEmp) ?? [];
  if (list.length === 0) return null;
  const unit = mode === "biz" ? "개" : "명";
  const sorted = list.slice().sort((a, b) => b.count - a.count);

  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-2">
        <p className="text-body-sm font-bold text-steel">주요 업종</p>
        <div className="flex gap-1.5">
          <PillTab active={mode === "biz"} onClick={() => setMode("biz")}>
            사업장수
          </PillTab>
          <PillTab active={mode === "emp"} onClick={() => setMode("emp")}>
            종사자수
          </PillTab>
        </div>
      </div>
      <div style={{ height: sorted.length * 36 + 8 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={sorted}
            layout="vertical"
            margin={{ top: 0, right: 52, left: 0, bottom: 0 }}
            barCategoryGap={6}
          >
            <XAxis type="number" hide />
            <YAxis
              type="category"
              dataKey="name"
              width={148}
              tick={{ fontSize: 11, fill: INK }}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              cursor={{ fill: SURFACE }}
              content={({ active, payload }) =>
                active && payload?.length ? (
                  <div className="rounded-lg border border-hairline-soft bg-canvas px-3 py-2 text-body-sm shadow-elev2">
                    <span className="font-bold text-ink-deep">
                      {payload[0].payload.name}
                    </span>
                    <span className="ml-2 text-steel">
                      {Number(payload[0].value).toLocaleString()}
                      {unit}
                    </span>
                  </div>
                ) : null
              }
            />
            <Bar dataKey="count" fill={COBALT_DEEP} radius={[0, 4, 4, 0]} barSize={15}>
              <LabelList
                dataKey="count"
                position="right"
                fontSize={12}
                fill={STEEL}
                formatter={(v: React.ReactNode) =>
                  `${Number(v).toLocaleString()}${unit}`
                }
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export function CommercialAreaSection({ data }: CommercialAreaSectionProps) {
  if (!data || !data.store_count || data.store_count <= 0) return null;

  const total = data.store_count;
  const retail = data.retail_count ?? 0;
  const service = data.service_count ?? 0;
  const food = data.food_count ?? 0;
  const pct = (n: number) => (total > 0 ? Math.round((n / total) * 100) : 0);

  const industryData = [
    { name: "도소매", value: retail, pct: pct(retail), color: COBALT },
    { name: "서비스", value: service, pct: pct(service), color: STEEL },
    { name: "외식", value: food, pct: pct(food), color: INK },
  ].filter((d) => d.value > 0);

  // 세부업종 막대용 — 점포수 내림차순
  const topInd = (data.top_industries ?? []).slice().sort((a, b) => b.count - a.count);

  const wp = data.workplace ?? null;
  const hasResident = data.resident_total != null && data.resident_total > 0;
  const male = data.resident_male ?? 0;
  const female = data.resident_female ?? 0;
  const genderData = [
    { name: "남성", value: male, pct: male + female > 0 ? Math.round((male / (male + female)) * 100) : 0, color: COBALT },
    { name: "여성", value: female, pct: male + female > 0 ? Math.round((female / (male + female)) * 100) : 0, color: COBALT_DEEP },
  ].filter((d) => d.value > 0);

  return (
    <section className="mb-12">
      <SectionHeading level={3} className="mb-4">발달상권 · 지역 통계</SectionHeading>

      {/* 발달상권 카드 — 업종 도넛 + 범례 + 세부업종 막대 */}
      <Card variant="flat" as="div">
        <div className="mb-4">
          {data.area_name && (
            <p className="text-heading-sm text-ink-deep">{data.area_name}</p>
          )}
          <p className="mt-0.5 text-body-sm text-steel">
            반경 {data.radius_m ?? 300}m 내 점포 분포
          </p>
        </div>

        {/* 업종 도넛 + 범례 2단 (모바일 1단) */}
        <div className="grid grid-cols-1 items-center gap-4 sm:grid-cols-2">
          <div className="relative h-52">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={industryData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  innerRadius={58}
                  outerRadius={84}
                  paddingAngle={2}
                  stroke="none"
                >
                  {industryData.map((d) => (
                    <Cell key={d.name} fill={d.color} />
                  ))}
                  <Label
                    position="center"
                    content={({ viewBox }) => {
                      const vb = viewBox as { cx?: number; cy?: number } | undefined;
                      if (!vb?.cx || !vb?.cy) return null;
                      return (
                        <text x={vb.cx} y={vb.cy} textAnchor="middle">
                          <tspan
                            x={vb.cx}
                            dy="-0.3em"
                            fontSize="22"
                            fontWeight="700"
                            fill={INK}
                          >
                            {total.toLocaleString()}
                          </tspan>
                          <tspan x={vb.cx} dy="1.5em" fontSize="12" fill={STEEL}>
                            총 점포
                          </tspan>
                        </text>
                      );
                    }}
                  />
                </Pie>
                <Tooltip content={<DonutTooltip />} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="divide-y divide-hairline-soft">
            {industryData.map((d) => (
              <LegendRow
                key={d.name}
                color={d.color}
                label={d.name}
                count={d.value}
                pct={d.pct}
              />
            ))}
          </div>
        </div>

        {/* 세부업종 막대 차트 (Top N) */}
        {topInd.length > 0 && (
          <div className="mt-6">
            <p className="mb-2 text-body-sm font-bold text-steel">세부업종 분포 (상위 {topInd.length})</p>
            <div style={{ height: topInd.length * 38 + 8 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={topInd}
                  layout="vertical"
                  margin={{ top: 0, right: 36, left: 0, bottom: 0 }}
                  barCategoryGap={8}
                >
                  <XAxis type="number" hide />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={104}
                    tick={{ fontSize: 12, fill: INK }}
                    tickLine={false}
                    axisLine={false}
                  />
                  <Tooltip
                    cursor={{ fill: SURFACE }}
                    content={({ active, payload }) =>
                      active && payload?.length ? (
                        <div className="rounded-lg border border-hairline-soft bg-canvas px-3 py-2 text-body-sm shadow-elev2">
                          <span className="font-bold text-ink-deep">
                            {payload[0].payload.name}
                          </span>
                          <span className="ml-2 text-steel">
                            {Number(payload[0].value).toLocaleString()}개
                          </span>
                        </div>
                      ) : null
                    }
                  />
                  <Bar dataKey="count" fill={COBALT} radius={[0, 4, 4, 0]} barSize={16}>
                    <LabelList
                      dataKey="count"
                      position="right"
                      fontSize={12}
                      fill={STEEL}
                      formatter={(v: React.ReactNode) =>
                        `${Number(v).toLocaleString()}개`
                      }
                    />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        <p className="mt-4 text-caption text-stone">
          {data.base_period ? `${data.base_period} 기준 · ` : ""}
          소상공인시장진흥공단 상가(상권)정보. 참고용 추정 자료입니다.
        </p>
      </Card>

      {/* 거주인구 카드 — 남녀 도넛 + 통계 */}
      {hasResident && (
        <Card variant="flat" as="div" className="mt-4">
          <div className="mb-4">
            <p className="text-heading-sm text-ink-deep">
              거주인구{data.dong_name ? ` · ${data.dong_name}` : ""}
            </p>
            <p className="mt-0.5 text-body-sm text-steel">법정동 기준 주민등록 인구</p>
          </div>

          <div className="grid grid-cols-1 items-center gap-4 sm:grid-cols-2">
            <div className="relative h-52">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={genderData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={58}
                    outerRadius={84}
                    paddingAngle={2}
                    stroke="none"
                  >
                    {genderData.map((d) => (
                      <Cell key={d.name} fill={d.color} />
                    ))}
                    <Label
                      position="center"
                      content={({ viewBox }) => {
                        const vb = viewBox as { cx?: number; cy?: number } | undefined;
                        if (!vb?.cx || !vb?.cy) return null;
                        return (
                          <text x={vb.cx} y={vb.cy} textAnchor="middle">
                            <tspan x={vb.cx} dy="-0.3em" fontSize="20" fontWeight="700" fill={INK}>
                              {(data.resident_total ?? 0).toLocaleString()}
                            </tspan>
                            <tspan x={vb.cx} dy="1.5em" fontSize="12" fill={STEEL}>
                              총 인구
                            </tspan>
                          </text>
                        );
                      }}
                    />
                  </Pie>
                  <Tooltip content={<DonutTooltip />} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="divide-y divide-hairline-soft">
              {genderData.map((d) => (
                <LegendRow
                  key={d.name}
                  color={d.color}
                  label={d.name}
                  count={d.value}
                  pct={d.pct}
                  unit="명"
                />
              ))}
              {data.household_count != null && data.household_count > 0 && (
                <div className="flex items-center justify-between gap-3 py-1.5">
                  <span className="text-body-sm font-bold text-ink">세대수</span>
                  <span className="text-body-sm text-steel">
                    {data.household_count.toLocaleString()}세대
                  </span>
                </div>
              )}
            </div>
          </div>

          <p className="mt-4 text-caption text-stone">
            {data.resident_period ? `${data.resident_period} 기준 · ` : ""}
            행정안전부 주민등록 인구·세대현황.
          </p>
        </Card>
      )}

      {/* 직장인구 — 국민연금 가입 사업장(법정동). 거주인구와 대비되는 '주간 직장 규모' */}
      {wp && (wp.employee_total ?? 0) > 0 && (
        <Card variant="flat" as="div" className="mt-4">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
            <div>
              <p className="text-heading-sm text-ink-deep">
                직장인구{data.dong_name ? ` · ${data.dong_name}` : ""}
              </p>
              <p className="mt-0.5 text-body-sm text-steel">
                국민연금 가입 사업장 기준 종사자
              </p>
            </div>
            <div className="text-right">
              <p className="text-heading-lg font-bold text-ink-deep">
                {(wp.employee_total ?? 0).toLocaleString()}
                <span className="ml-1 text-body-md font-normal text-steel">명</span>
              </p>
              <p className="text-body-sm text-steel">
                사업장 {(wp.biz_count ?? 0).toLocaleString()}개
              </p>
            </div>
          </div>

          {/* 업종 분포 — 사업장수/종사자수 토글 막대 */}
          <WorkplaceIndustryChart
            byBiz={wp.top_industries}
            byEmp={wp.top_industries_emp}
          />

          <p className="mt-4 text-caption text-stone">
            {wp.base_period ? `${wp.base_period} 기준 · ` : ""}
            국민연금공단 가입 사업장 내역(3인 이상 법인 등). 참고용 추정 자료입니다.
          </p>
        </Card>
      )}
    </section>
  );
}
