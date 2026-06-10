"use client";

import { useArtifactStore } from "@/stores/artifactStore";
import { DiffViewerCard } from "./DiffViewerCard";
import { ReviewCard } from "./ReviewCard";
import { PreviewCard } from "./PreviewCard";
import { FileCard } from "./FileCard";
import { BundleCard } from "./BundleCard";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import type {
  ArtifactCard,
  DiffContent,
  ReviewContent,
  PreviewContent,
  FileContent,
  BundleContent,
} from "@/types";
import { Package, Info, ChevronDown, ChevronUp } from "lucide-react";
import { useState, useEffect } from "react";

function UnknownCardType({ artifact }: { artifact: ArtifactCard }) {
  return (
    <div className="rounded-[8px] border border-dashed border-[#E5E7EB] bg-white p-4">
      <div className="flex items-center gap-2 mb-1">
        <Info className="h-4 w-4 text-[#9CA3AF]" />
        <h3 className="text-sm font-medium text-[#111827]">{artifact.title}</h3>
      </div>
      <p className="text-xs text-[#9CA3AF]">
        {artifact.summary || `Unknown card type: ${artifact.card_type}`}
      </p>
      <div className="flex items-center gap-2 mt-2">
        <Badge variant="secondary" className="text-[10px]">
          {artifact.card_type}
        </Badge>
        <p className="text-[10px] text-[#9CA3AF] font-mono truncate">
          {artifact.artifact_id.slice(0, 12)}...
        </p>
      </div>
    </div>
  );
}

function ArtifactCardRenderer({ artifact }: { artifact: ArtifactCard }) {
  switch (artifact.card_type) {
    case "diff":
      return (
        <DiffViewerCard
          content={artifact.content as unknown as DiffContent}
          title={artifact.title}
          summary={artifact.summary}
        />
      );
    case "review":
      return (
        <ReviewCard
          content={artifact.content as unknown as ReviewContent}
          title={artifact.title}
          summary={artifact.summary}
        />
      );
    case "preview":
      return (
        <PreviewCard
          content={artifact.content as unknown as PreviewContent}
          title={artifact.title}
          summary={artifact.summary}
        />
      );
    case "file":
      return (
        <FileCard
          content={artifact.content as unknown as FileContent}
          title={artifact.title}
          summary={artifact.summary}
        />
      );
    case "bundle":
      return (
        <BundleCard
          content={artifact.content as unknown as BundleContent}
          title={artifact.title}
          summary={artifact.summary}
          taskId={artifact.task_id}
        />
      );
    default:
      return <UnknownCardType artifact={artifact} />;
  }
}

function TaskGroup({
  taskId,
  artifacts,
  isExpanded,
  onToggle,
}: {
  taskId: string;
  artifacts: ArtifactCard[];
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const sortedArtifacts = [...artifacts].sort((a, b) => {
    const typeOrder: Record<string, number> = { bundle: 0, review: 1, diff: 2, file: 3, preview: 4 };
    return (typeOrder[a.card_type] ?? 99) - (typeOrder[b.card_type] ?? 99);
  });

  return (
    <div>
      <button
        onClick={onToggle}
        className="w-full text-left px-3 py-2.5 rounded-[8px] bg-[#F3F4F6] hover:bg-[#E5E7EB] transition-colors flex items-center justify-between"
      >
        <div className="flex items-center gap-2">
          <Package className="h-4 w-4 text-[#6B7280]" />
          <span className="text-sm font-medium text-[#111827]">
            Task: {taskId.slice(0, 8)}...
          </span>
          <Badge variant="outline" className="text-[10px]">
            {artifacts.length} items
          </Badge>
        </div>
        {isExpanded ? (
          <ChevronUp className="h-4 w-4 text-[#9CA3AF]" />
        ) : (
          <ChevronDown className="h-4 w-4 text-[#9CA3AF]" />
        )}
      </button>

      {isExpanded && (
        <div className="mt-2 pl-2 space-y-3">
          {sortedArtifacts.map((artifact) => (
            <ArtifactCardRenderer
              key={artifact.artifact_id}
              artifact={artifact}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function ArtifactCardList() {
  const artifacts = useArtifactStore((s) => s.artifacts);
  const loading = useArtifactStore((s) => s.loading);

  const [expandedTasks, setExpandedTasks] = useState<Set<string>>(new Set());

  const toggleTask = (taskId: string) => {
    setExpandedTasks((prev) => {
      const next = new Set(prev);
      if (next.has(taskId)) next.delete(taskId);
      else next.add(taskId);
      return next;
    });
  };

  const grouped = artifacts.reduce(
    (acc, artifact) => {
      const taskId = artifact.task_id;
      if (!acc[taskId]) acc[taskId] = [];
      acc[taskId].push(artifact);
      return acc;
    },
    {} as Record<string, ArtifactCard[]>
  );

  const taskIds = Object.keys(grouped).sort((a, b) => {
    const latestA = Math.max(...grouped[a].map((x) => new Date(x.updated_at).getTime()));
    const latestB = Math.max(...grouped[b].map((x) => new Date(x.updated_at).getTime()));
    return latestB - latestA;
  });

  useEffect(() => {
    if (taskIds.length > 0) {
      setExpandedTasks((prev) => {
        if (prev.size === 0) {
          return new Set([taskIds[0]]);
        }
        return prev;
      });
    }
  }, [taskIds.length]);

  if (loading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-32 w-full rounded-[8px]" />
        ))}
      </div>
    );
  }

  if (artifacts.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
        <div className="rounded-full bg-[#F3F4F6] p-3 mb-3">
          <Package className="h-5 w-5 text-[#9CA3AF]" />
        </div>
        <p className="text-sm text-[#9CA3AF] mb-1">
          No artifacts yet
        </p>
        <p className="text-xs text-[#9CA3AF]">
          Agent outputs will appear here
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {taskIds.map((taskId) => (
        <TaskGroup
          key={taskId}
          taskId={taskId}
          artifacts={grouped[taskId]}
          isExpanded={expandedTasks.has(taskId)}
          onToggle={() => toggleTask(taskId)}
        />
      ))}
    </div>
  );
}
