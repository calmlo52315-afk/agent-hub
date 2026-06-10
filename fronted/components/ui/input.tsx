import * as React from "react";
import { cn } from "@/lib/utils";

const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-8 w-full rounded-sm border border-[#E7E7E7] bg-white px-2.5 py-1 text-xs transition-colors",
          "placeholder:text-[#b0b0b0]",
          "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#64748B] focus-visible:border-[#64748B]",
          "disabled:cursor-not-allowed disabled:opacity-50",
          className
        )}
        ref={ref}
        {...props}
      />
    );
  }
);
Input.displayName = "Input";

export { Input };
