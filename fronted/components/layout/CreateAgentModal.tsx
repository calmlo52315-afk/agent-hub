"use client";

import { useState } from "react";
import { X, Plus, Link2, Trash2 } from "lucide-react";
import type { AgentDefinition } from "@/types";
import type { AgentCreateRequest } from "@/lib/api";
import * as api from "@/lib/api";

interface CreateAgentModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: (agent: AgentDefinition) => void;
}

const AVAILABLE_SKILLS = [
  { id: "coding", label: "代码生成" },
  { id: "review", label: "代码审查" },
  { id: "read_file", label: "读取文件" },
  { id: "write_file", label: "写入文件" },
  { id: "search_code", label: "搜索代码" },
  { id: "run_command", label: "运行命令" },
  { id: "git_diff", label: "Git Diff" },
];

const PROVIDERS = [
  { id: "claude_code", label: "Claude Code" },
  { id: "codex", label: "Codex" },
];

export function CreateAgentModal({
  open,
  onClose,
  onCreated,
}: CreateAgentModalProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [selectedSkills, setSelectedSkills] = useState<string[]>(["coding"]);
  const [preferredProvider, setPreferredProvider] = useState("claude_code");
  const [visibility, setVisibility] = useState("private");
  const [importUrl, setImportUrl] = useState("");
  const [importing, setImporting] = useState(false);
  const [importedSkills, setImportedSkills] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const toggleSkill = (skillId: string) => {
    setSelectedSkills((prev) =>
      prev.includes(skillId)
        ? prev.filter((s) => s !== skillId)
        : [...prev, skillId]
    );
  };

  const handleImport = async () => {
    if (!importUrl.trim()) return;
    setImporting(true);
    setError("");
    try {
      const resp = await fetch(importUrl.trim());
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      let skills: string[] = [];
      if (Array.isArray(data)) {
        skills = data.map((s) => (typeof s === "string" ? s : s.name || s.id || ""));
      } else if (typeof data === "object" && data !== null) {
        skills = (data.skills || data.tools || []).map(
          (s: { name?: string; id?: string } | string) =>
            typeof s === "string" ? s : s.name || s.id || ""
        );
      }
      skills = skills.filter(Boolean).slice(0, 20);
      setImportedSkills(skills);
      // 自动合并到已选 skills
      setSelectedSkills((prev) => {
        const merged = new Set([...prev, ...skills]);
        return Array.from(merged);
      });
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Failed to import from URL"
      );
    } finally {
      setImporting(false);
    }
  };

  const handleSubmit = async () => {
    if (!name.trim()) {
      setError("请输入 Agent 名称");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const payload: AgentCreateRequest = {
        name: name.trim(),
        description: description.trim(),
        system_prompt: systemPrompt.trim(),
        allowed_skills: selectedSkills,
        preferred_provider: preferredProvider,
        visibility,
        import_url: importUrl.trim() || undefined,
      };
      const agent = await api.createAgent(payload);
      onCreated(agent);
      // Reset form
      setName("");
      setDescription("");
      setSystemPrompt("");
      setSelectedSkills(["coding"]);
      setPreferredProvider("claude_code");
      setVisibility("private");
      setImportUrl("");
      setImportedSkills([]);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "创建失败");
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative z-10 w-full max-w-lg max-h-[90vh] bg-white rounded-xl shadow-2xl border border-[#E5E7EB] flex flex-col mx-4 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-[#E5E7EB] shrink-0">
          <div>
            <p className="text-[15px] font-semibold text-[#111827]">
              创建 Agent
            </p>
            <p className="text-[11px] text-[#9CA3AF]">
              自定义 Agent 会显示在对话侧边栏中
            </p>
          </div>
          <button
            onClick={onClose}
            className="flex items-center justify-center h-7 w-7 rounded-lg hover:bg-[#F3F4F6] transition-colors shrink-0"
          >
            <X className="h-4 w-4 text-[#6B7280]" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          {/* Name */}
          <div>
            <label className="text-[12px] font-medium text-[#111827] mb-1 block">
              名称 <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Python Data Analyst"
              maxLength={64}
              className="w-full rounded-[8px] border border-[#E5E7EB] px-3 py-2 text-[13px] text-[#111827] placeholder-[#9CA3AF] outline-none focus:border-[#6366F1] focus:ring-1 focus:ring-[#6366F1] transition-colors"
            />
          </div>

          {/* Description */}
          <div>
            <label className="text-[12px] font-medium text-[#111827] mb-1 block">
              描述
            </label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="一句话描述 Agent 的用途"
              maxLength={128}
              className="w-full rounded-[8px] border border-[#E5E7EB] px-3 py-2 text-[13px] text-[#111827] placeholder-[#9CA3AF] outline-none focus:border-[#6366F1] focus:ring-1 focus:ring-[#6366F1] transition-colors"
            />
          </div>

          {/* System Prompt */}
          <div>
            <label className="text-[12px] font-medium text-[#111827] mb-1 block">
              System Prompt
            </label>
            <textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              placeholder="编写 System Prompt 来定义 Agent 的行为..."
              rows={5}
              maxLength={4096}
              className="w-full rounded-[8px] border border-[#E5E7EB] px-3 py-2 text-[13px] text-[#111827] placeholder-[#9CA3AF] outline-none focus:border-[#6366F1] focus:ring-1 focus:ring-[#6366F1] transition-colors resize-none"
            />
            <p className="text-[10px] text-[#9CA3AF] mt-0.5">
              {systemPrompt.length}/4096
            </p>
          </div>

          {/* Skills */}
          <div>
            <label className="text-[12px] font-medium text-[#111827] mb-1 block">
              Skills / Tools
            </label>
            <div className="flex flex-wrap gap-1.5">
              {AVAILABLE_SKILLS.map((skill) => {
                const active = selectedSkills.includes(skill.id);
                return (
                  <button
                    key={skill.id}
                    onClick={() => toggleSkill(skill.id)}
                    className={`text-[11px] px-2.5 py-1 rounded-full font-medium transition-colors ${
                      active
                        ? "bg-[#EEF2FF] text-[#4F46E5] border border-[#C7D2FE]"
                        : "bg-[#F3F4F6] text-[#6B7280] border border-[#E5E7EB] hover:border-[#D1D5DB]"
                    }`}
                  >
                    {skill.label}
                  </button>
                );
              })}
              {/* Imported skills */}
              {importedSkills
                .filter((s) => !AVAILABLE_SKILLS.some((a) => a.id === s))
                .map((s) => (
                  <span
                    key={s}
                    className="text-[11px] px-2.5 py-1 rounded-full font-medium bg-[#FEF3C7] text-[#92400E] border border-[#FDE68A]"
                  >
                    {s}
                  </span>
                ))}
            </div>
          </div>

          {/* Import URL */}
          <div>
            <label className="text-[12px] font-medium text-[#111827] mb-1 block flex items-center gap-1">
              <Link2 className="h-3 w-3" />
              从 URL 导入 Skills / Tools
            </label>
            <div className="flex gap-2">
              <input
                type="url"
                value={importUrl}
                onChange={(e) => setImportUrl(e.target.value)}
                placeholder="https://example.com/skills.json"
                className="flex-1 rounded-[8px] border border-[#E5E7EB] px-3 py-2 text-[13px] text-[#111827] placeholder-[#9CA3AF] outline-none focus:border-[#6366F1] focus:ring-1 focus:ring-[#6366F1] transition-colors"
              />
              <button
                onClick={handleImport}
                disabled={importing || !importUrl.trim()}
                className="shrink-0 inline-flex items-center gap-1 px-3 py-2 rounded-[8px] bg-[#F3F4F6] text-[#111827] text-[12px] font-medium hover:bg-[#E5E7EB] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {importing ? "导入中..." : "导入"}
              </button>
            </div>
            {importedSkills.length > 0 && (
              <p className="text-[10px] text-[#059669] mt-1">
                已导入 {importedSkills.length} 个 skills
              </p>
            )}
          </div>

          {/* Provider */}
          <div>
            <label className="text-[12px] font-medium text-[#111827] mb-1 block">
              首选 Provider
            </label>
            <div className="flex gap-2">
              {PROVIDERS.map((p) => (
                <button
                  key={p.id}
                  onClick={() => setPreferredProvider(p.id)}
                  className={`text-[12px] px-3 py-1.5 rounded-[8px] font-medium transition-colors ${
                    preferredProvider === p.id
                      ? "bg-[#EEF2FF] text-[#4F46E5] border border-[#C7D2FE]"
                      : "bg-[#F3F4F6] text-[#6B7280] border border-[#E5E7EB]"
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          {/* Visibility */}
          <div>
            <label className="text-[12px] font-medium text-[#111827] mb-1 block">
              可见性
            </label>
            <select
              value={visibility}
              onChange={(e) => setVisibility(e.target.value)}
              className="w-full rounded-[8px] border border-[#E5E7EB] px-3 py-2 text-[13px] text-[#111827] outline-none focus:border-[#6366F1] focus:ring-1 focus:ring-[#6366F1] transition-colors bg-white"
            >
              <option value="private">私有 — 仅自己可见</option>
              <option value="unlisted">不公开 — 有链接的人可见</option>
              <option value="public">公开 — 所有人可见</option>
            </select>
          </div>

          {/* Error */}
          {error && (
            <div className="rounded-[8px] bg-[#FEF2F2] border border-[#FECACA] px-3 py-2">
              <p className="text-[12px] text-[#DC2626]">{error}</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-[#E5E7EB] shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-[8px] text-[13px] font-medium text-[#6B7280] hover:bg-[#F3F4F6] transition-colors"
          >
            取消
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting || !name.trim()}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-[8px] bg-[#4F46E5] text-white text-[13px] font-medium hover:bg-[#4338CA] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Plus className="h-3.5 w-3.5" />
            {submitting ? "创建中..." : "创建 Agent"}
          </button>
        </div>
      </div>
    </div>
  );
}
