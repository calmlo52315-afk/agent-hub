"use client";

import { Settings, Save, Cpu, Clock, RotateCcw, Folder } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function ConfigPage() {
  const sections = [
    {
      icon: Cpu,
      title: "模型路由配置",
      desc: "DeepSeek / Claude 权重分配与模型选择策略",
    },
    {
      icon: Clock,
      title: "Skill 超时配置",
      desc: "各 Skill 执行超时时间与重试策略",
    },
    {
      icon: RotateCcw,
      title: "重试规则配置",
      desc: "任务失败重试次数、退避策略与熔断阈值",
    },
    {
      icon: Folder,
      title: "目录权限配置",
      desc: "工作区与产物目录的读写权限管理",
    },
  ];

  return (
    <div className="flex h-full flex-col p-6 overflow-y-auto">
      <div className="max-w-[840px] mx-auto w-full">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Settings className="h-6 w-6 text-[#6B7280]" />
            <h1 className="text-xl font-bold">系统配置</h1>
          </div>
          <Button size="sm" className="gap-1.5">
            <Save className="h-3.5 w-3.5" />
            保存配置
          </Button>
        </div>

        <div className="space-y-3">
          {sections.map((section) => {
            const Icon = section.icon;
            return (
              <div
                key={section.title}
                className="rounded-xl border border-border bg-card p-4 hover:bg-muted/30 transition-colors cursor-pointer"
              >
                <div className="flex items-center gap-3">
                  <Icon className="h-5 w-5 text-muted-foreground shrink-0" />
                  <div>
                    <h3 className="text-sm font-semibold">{section.title}</h3>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {section.desc}
                    </p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
