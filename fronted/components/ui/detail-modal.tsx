"use client";

import { X } from "lucide-react";
import { cn } from "@/lib/utils";

interface DetailModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  className?: string;
}

export function DetailModal({ open, onClose, title, children, className }: DetailModalProps) {
  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-50 bg-black/20 transition-opacity"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="fixed inset-4 z-50 flex items-center justify-center pointer-events-none">
        <div
          className={cn(
            "pointer-events-auto w-full max-w-2xl max-h-full bg-white rounded-md border border-[#E7E7E7] shadow-sm flex flex-col",
            className
          )}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-[#E7E7E7] shrink-0">
            <h3 className="text-sm font-medium text-[#1a1a1a]">{title}</h3>
            <button
              onClick={onClose}
              className="flex items-center justify-center h-6 w-6 rounded-sm hover:bg-[#F0F0F0] transition-colors"
            >
              <X className="h-3.5 w-3.5 text-[#8c8c8c]" />
            </button>
          </div>

          {/* Body */}
          <div className="flex-1 overflow-y-auto p-4">
            {children}
          </div>
        </div>
      </div>
    </>
  );
}
