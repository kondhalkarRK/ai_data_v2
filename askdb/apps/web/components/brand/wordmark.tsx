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
 * Soci keeps the complementary blue and teal brand treatment in a single word.
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
  const lead = APP_NAME.slice(0, 2);
  const tail = APP_NAME.slice(2);

  return (
    <span
      className={cn(
        "inline-flex items-baseline font-semibold",
        SIZE[size],
        className,
      )}
      aria-label={APP_NAME}
      role="img"
    >
      <span aria-hidden="true" className="brand-ask">{lead}</span>
      {tail ? <span aria-hidden="true" className="brand-me">{tail}</span> : null}
      {withPeriod ? <span className="text-foreground/80">.</span> : null}
    </span>
  );
}
