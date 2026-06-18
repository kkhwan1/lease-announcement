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
    <div className="rounded border border-gray-200 bg-white px-3 py-2 shadow-sm text-sm">
      <p className="text-gray-500 mb-1">{label}</p>
      <p className="font-semibold text-gray-900">
        평당 {formatRentManwon(payload[0].value)}
      </p>
    </div>
  );
}

export function RentTrendChart({ data }: RentTrendChartProps) {
  // 빈 배열
  if (data.length === 0) {
    return (
      <div className="rounded border border-gray-200 bg-white px-4 py-6 text-center text-sm text-gray-500">
        임대료 데이터가 없습니다.
      </div>
    );
  }

  // 고유 snapshot_month 집합
  const uniqueMonths = new Set(data.map((d) => toYearMonth(d.snapshot_month)));

  // 고유 월 1개 이하 — 안내 카드
  if (uniqueMonths.size <= 1) {
    const monthLabel = uniqueMonths.size === 1 ? Array.from(uniqueMonths)[0] : null;

    // 현재 평균 평당임대료 계산
    const rents = data.map((d) => toNum(d.rent_per_pyeong)).filter((n): n is number => n !== null && n > 0);
    const avgRent = rents.length > 0 ? rents.reduce((s, v) => s + v, 0) / rents.length : null;

    return (
      <div className="rounded border border-gray-200 bg-white px-4 py-6">
        <p className="text-sm text-gray-700">
          현재{" "}
          {monthLabel ? (
            <span className="font-semibold">1개월({monthLabel})</span>
          ) : (
            "1개월"
          )}{" "}
          데이터만 있습니다. 다음 달 데이터가 쌓이면 임대료 추이가 표시됩니다.
        </p>
        {avgRent !== null && (
          <p className="mt-3 text-sm text-gray-500">
            현재 평균 평당임대료:{" "}
            <span className="font-semibold text-gray-900">{formatRentManwon(avgRent)}</span>
          </p>
        )}
      </div>
    );
  }

  // 월별 집계
  const chartData = aggregateByMonth(data);

  return (
    <div className="w-full bg-white">
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis
            dataKey="month"
            tick={{ fontSize: 12, fill: "#6b7280" }}
            tickLine={false}
            axisLine={{ stroke: "#e5e7eb" }}
          />
          <YAxis
            tickFormatter={formatYTick}
            tick={{ fontSize: 12, fill: "#6b7280" }}
            tickLine={false}
            axisLine={false}
            width={52}
          />
          <Tooltip content={<CustomTooltip />} />
          <Line
            type="monotone"
            dataKey="rent"
            stroke="#2563eb"
            strokeWidth={2}
            dot={{ r: 4, fill: "#2563eb", strokeWidth: 0 }}
            activeDot={{ r: 5, fill: "#2563eb", strokeWidth: 0 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
