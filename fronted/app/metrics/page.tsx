"use client";

import { BarChart3, TrendingUp, CheckCircle2, Clock, Activity } from "lucide-react";

export default function MetricsPage() {
  const cards = [
    { icon: CheckCircle2, label: "任务成功率", value: "--", color: "text-[#6B7280]" },
    { icon: TrendingUp, label: "评审通过率", value: "--", color: "text-[#6B7280]" },
    { icon: Clock, label: "平均耗时", value: "--", color: "text-[#6B7280]" },
    { icon: Activity, label: "Token 消耗", value: "--", color: "text-[#6B7280]" },
  ];

  return (
    <div className="flex h-full flex-col p-6 overflow-y-auto">
      <div className="max-w-[840px] mx-auto w-full">
        <div className="flex items-center gap-3 mb-6">
          <BarChart3 className="h-6 w-6 text-[#6B7280]" />
          <h1 className="text-xl font-bold">数据看板</h1>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          {cards.map((card) => {
            const Icon = card.icon;
            return (
              <div key={card.label} className="rounded-xl border border-border bg-card p-4">
                <Icon className={`h-5 w-5 ${card.color} mb-2`} />
                <p className="text-2xl font-bold">{card.value}</p>
                <p className="text-xs text-muted-foreground mt-1">{card.label}</p>
              </div>
            );
          })}
        </div>

        {/* Chart Placeholder */}
        <div className="rounded-xl border border-border bg-card p-6">
          <h3 className="text-sm font-semibold mb-4">任务执行趋势</h3>
          <div className="flex items-center justify-center h-48 text-sm text-muted-foreground">
            图表区域 — 接入 Stage6 指标数据后展示折线图
          </div>
        </div>
      </div>
    </div>
  );
}
