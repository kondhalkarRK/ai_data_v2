import * as React from "react";

import { cn } from "@/lib/utils";

export const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  ({ className, type = "text", ...props }, ref) => (
    <input
      ref={ref}
      type={type}
      className={cn(
        "flex h-9 w-full rounded-[var(--radius-control)] border border-input bg-surface-raised px-3 py-1 text-sm text-foreground shadow-xs outline-none transition-[color,border-color,box-shadow] duration-150",
        "placeholder:text-muted-foreground",
        "hover:border-muted-foreground/35 focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/35",
        "disabled:cursor-not-allowed disabled:opacity-50",
        // aria-invalid drives the error styling, so the visual state and the state
        // announced to assistive technology can never disagree.
        "aria-invalid:border-danger aria-invalid:focus-visible:ring-danger/40",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";
