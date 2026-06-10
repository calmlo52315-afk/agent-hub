import * as React from "react";
import { cn } from "@/lib/utils";

const Badge = React.forwardRef<
  HTMLSpanElement,
  React.HTMLAttributes<HTMLSpanElement> & {
    variant?: "default" | "secondary" | "outline" | "success" | "warning" | "danger";
  }
>(({ className, variant = "default", ...props }, ref) => {
  const variantStyles: Record<string, string> = {
    default: "bg-[#F3F4F6] text-[#374151]",
    secondary: "bg-[#F3F4F6] text-[#6B7280]",
    outline: "text-[#6B7280] border border-[#E5E7EB]",
    success: "bg-[#F3F4F6] text-[#374151]",
    warning: "bg-[#F3F4F6] text-[#374151]",
    danger: "bg-[#FEF2F2] text-[#DC2626]",
  };

  return (
    <span
      ref={ref}
      className={cn(
        "inline-flex items-center rounded-[4px] border border-[#E5E7EB] px-1.5 py-0 text-[10px] font-medium",
        variantStyles[variant],
        className
      )}
      {...props}
    />
  );
});
Badge.displayName = "Badge";

export { Badge };
