import { APP_NAME } from "@/lib/brand";
import { cn } from "@/lib/utils";

type WordmarkSize = "sm" | "md" | "lg" | "hero";

const SIZE: Record<WordmarkSize, string> = {
  sm: "text-sm tracking-tight",
  md: "text-lg tracking-tight",
  lg: "text-2xl tracking-tight",
  hero: "text-4xl tracking-[-0.04em] sm:text-5xl lg:text-[3.35rem]",
};

/**
 * Product wordmark: ASK (cyan/blue) + DB (teal) — complementary brand treatment.
 */
export function BrandWordmark({
  size = "md",
  withPeriod = false,
  className,
}: {
  size?: WordmarkSize;
  withPeriod?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-baseline font-semibold",
        SIZE[size],
        className,
      )}
      aria-label={APP_NAME}
    >
      <span className="brand-ask">Ask</span>
      <span className="brand-db ml-[0.18em]">DB</span>
      {withPeriod ? <span className="text-foreground/80">.</span> : null}
    </span>
  );
}
