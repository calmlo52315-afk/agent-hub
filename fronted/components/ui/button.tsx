import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[8px] text-xs font-medium transition-colors focus-visible:outline-none disabled:pointer-events-none disabled:opacity-40",
  {
    variants: {
      variant: {
        default: "bg-[#111827] text-white hover:bg-[#374151]",
        destructive: "bg-[#DC2626] text-white hover:bg-[#B91C1C]",
        outline: "border border-[#E5E7EB] bg-white hover:bg-[#F3F4F6] text-[#111827]",
        secondary: "bg-[#F3F4F6] text-[#111827] hover:bg-[#E5E7EB]",
        ghost: "hover:bg-[#F3F4F6] text-[#111827]",
      },
      size: {
        default: "h-8 px-3.5",
        sm: "h-7 px-2.5 text-[11px]",
        icon: "h-8 w-8",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />;
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
