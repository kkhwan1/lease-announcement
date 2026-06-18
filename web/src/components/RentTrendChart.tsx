// @TASK T-chart - 월별 평당임대료 추이 차트
// @SPEC docs/planning — 건물 상세 페이지 임대료 추이 섹션
"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { RentTrendPoint } from "@/lib/types";
import { toNum, formatRentManwon } from "@/lib/format";

interface RentTrendChartProps {
  data: RentTrendPoint[];
}

// YYYY-MM-DD → YYYY.MM 포맷
function toYearMonth(dateStr: string): string {
  return dateStr.slice(0, 7).replace("-", ".");
}

// 월별 평균 집계: 같은 snapshot_month의 rent_per_pyeong 평균
interface ChartPoint {
  month: string; // YYYY.MM
  rent: number;  // 평균 평당임대료(원)
}

function aggregateByMonth(data: RentTrendPoint[]): ChartPoint[] {
  const map = new Map<string, number[]>();

  for (const point of data) {
    const n = toNum(point.rent_per_pyeong);
    if (n === null || n <= 0) continue;
    const month = toYearMonth(point.snapshot_month);
    const arr = map.get(month) ?? [];
    arr.push(n);
    map.set(month, arr);
  }

  return Array.from(map.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([month, values]) => ({
      month,
      rent: Math.round(values.reduce((s, v) => s + v, 0) / values.length),
    }));
}

// y축 tick: 원 → 만원 단위 표시
function formatYTick(value: number): string {
  return `${Math.round(value / 10000)}만`;
}

// Recharts는 SVG 내부에서 CSS 변수를 읽지 못하므로 직접 상수로 정의.
const COBALT = "#0064E0";
const GRID_STROKE = "#E9EDF1";
const AXIS_TICK_FILL = "#7A8C99";

// Tooltip 커스텀 포맷
function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { value: number }[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-hairline-soft shadow-elev2 bg-canvas px-3 py-2 text-body-sm">
      <p className="text-steel mb-1">{label}</p>
      <p className="text-ink-deep font-bold">
        평당 {formatRentManwon(payload[0].value)}
      </p>
    </div>
  );
}

export function RentTrendChart({ data }: RentTrendChartProps) {
  // 빈 배열
  if (data.length === 0) {
    return (
      <div className="rounded-xl border border-hairline-soft bg-canvas px-4 py-6 text-center text-body-sm text-stone">
        임대료 데이터가 없습니다.
      </div>
    );
  }

  // 월별 집계를 먼저 수행 — 안내/차트 분기를 "유효 임대료가 있는 월 수" 기준으로 통일.
  const chartData = aggregateByMonth(data);

  // 유효 집계 월이 1개 이하 — 안내 카드 (원시 데이터 월 수가 아닌 집계 결과 기준)
  if (chartData.length <= 1) {
    const monthLabel = chartData.length === 1 ? chartData[0].month : null;
    const avgRent = chartData.length === 1 ? chartData[0].rent : null;

    return (
      <div className="rounded-xl border border-hairline-soft bg-canvas px-4 py-6">
        <p className="text-body-sm text-charcoal">
          현재{" "}
          {monthLabel ? (
            <span className="font-bold">1개월({monthLabel})</span>
          ) : (
            "1개월"
          )}{" "}
          데이터만 있습니다. 다음 달 데이터가 쌓이면 임대료 추이가 표시됩니다.
        </p>
        {avgRent !== null && (
          <p className="mt-3 text-body-sm text-steel">
            현재 평균 평당임대료:{" "}
            <span className="font-bold text-ink-deep">{formatRentManwon(avgRent)}</span>
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="w-full bg-canvas">
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
          <XAxis
            dataKey="month"
            tick={{ fontSize: 12, fill: AXIS_TICK_FILL }}
            tickLine={false}
            axisLine={{ stroke: GRID_STROKE }}
          />
          <YAxis
            tickFormatter={formatYTick}
            tick={{ fontSize: 12, fill: AXIS_TICK_FILL }}
            tickLine={false}
            axisLine={false}
            width={52}
          />
          <Tooltip content={<CustomTooltip />} />
          <Line
            type="monotone"
            dataKey="rent"
            stroke={COBALT}
            strokeWidth={2}
            dot={{ r: 4, fill: COBALT, strokeWidth: 0 }}
            activeDot={{ r: 5, fill: COBALT, strokeWidth: 0 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
