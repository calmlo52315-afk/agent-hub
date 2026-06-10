"use client";

import type { BundleContent, ArtifactCard } from "@/types";
import {
  Package,
  Download,
  Monitor,
  FileCode,
  ShieldCheck,
  FileText,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useArtifactStore } from "@/stores/artifactStore";
import JSZip from "jszip";

const typeIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  preview: Monitor,
  diff: FileCode,
  review: ShieldCheck,
  file: FileText,
};

async function downloadBundle(taskId: string, artifacts: ArtifactCard[]) {
  const filesToDownload: { path: string; content: string }[] = [];

  for (const artifact of artifacts) {
    if (artifact.task_id === taskId && artifact.card_type === "diff") {
      const diffContent = artifact.content as any;
      if (diffContent?.files) {
        for (const file of diffContent.files) {
          if (file.content) {
            filesToDownload.push({ path: file.path, content: file.content });
          }
        }
      }
    }
    if (artifact.task_id === taskId && artifact.card_type === "file") {
      const fileContent = artifact.content as any;
      if (fileContent?.content) {
        filesToDownload.push({ path: fileContent.path, content: fileContent.content });
      }
    }
  }

  if (filesToDownload.length === 0) {
    alert("No files to download!");
    return;
  }

  try {
    const zip = new JSZip();

    // 将所有文件添加到 zip 中
    for (const file of filesToDownload) {
      zip.file(file.path, file.content);
    }

    // 生成 zip 文件并下载
    const content = await zip.generateAsync({ type: "blob" });
    const url = URL.createObjectURL(content);
    const link = document.createElement("a");
    link.href = url;
    link.download = `agenthub-task-${taskId.slice(0, 8)}.zip`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  } catch (error) {
    console.error("Failed to generate zip:", error);
    alert("Failed to generate zip file. Please try again.");
  }
}

interface BundleCardProps {
  content: BundleContent;
  title: string;
  summary?: string;
  taskId?: string;
}

export function BundleCard({ content, title, summary, taskId }: BundleCardProps) {
  const artifacts = useArtifactStore((s) => s.artifacts);

  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-2" style={{ padding: 16 }}>
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Package className="h-4 w-4 text-[#6B7280]" />
            {title}
          </CardTitle>
        </div>
        {summary && (
          <p className="text-xs text-[#9CA3AF] mt-0.5">{summary}</p>
        )}
      </CardHeader>
      <CardContent style={{ padding: "0 16px 16px" }}>
        <div className="space-y-2">
          <div className="rounded-[8px] border border-[#E5E7EB] bg-[#F3F4F6] divide-y divide-[#E5E7EB]">
            {content.items.map((item, idx) => {
              const Icon = typeIcons[item.type] || Package;
              return (
                <div key={idx} className="flex items-center gap-2.5 px-3 py-2">
                  <Icon className="h-3.5 w-3.5 text-[#9CA3AF]" />
                  <span className="text-xs font-mono text-[#9CA3AF] flex-1">
                    {item.artifact_id}
                  </span>
                  <Badge variant="secondary" className="text-[10px] px-1.5 h-4">
                    {item.type}
                  </Badge>
                </div>
              );
            })}
          </div>

          <Button
            variant="outline"
            size="sm"
            className="w-full text-xs h-8"
            onClick={() => taskId && downloadBundle(taskId, artifacts)}
          >
            <div className="flex items-center gap-1.5">
              <Download className="h-3.5 w-3.5" />
              下载打包文件
            </div>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
