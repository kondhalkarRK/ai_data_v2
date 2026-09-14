"use client";

import { cn } from "@/lib/utils";

/** Lightweight ambient motion for the Ask DB hero — CSS-only, respects reduced motion. */
export function HeroBackdrop({ className }: { className?: string }) {
  return (
    <div aria-hidden="true" className={cn("pointer-events-none absolute inset-0 overflow-hidden", className)}>
      <div className="hero-ambient absolute inset-0" />
      <div className="hero-gradient-drift absolute inset-[-20%] opacity-70 dark:opacity-90" />

      <svg className="absolute inset-0 h-full w-full opacity-[0.55] dark:opacity-70" viewBox="0 0 800 480">
        <defs>
          <radialGradient id="hero-node-glow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity="0.55" />
            <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* Soft connection lines */}
        <g className="hero-connections stroke-primary/25 dark:stroke-primary/35" fill="none" strokeWidth="1">
          <path d="M120 340 C220 280, 280 220, 380 200" className="hero-draw" />
          <path d="M380 200 C470 180, 520 140, 640 110" className="hero-draw hero-draw-delay" />
          <path d="M200 120 C300 160, 340 220, 380 200" className="hero-draw hero-draw-delay-2" />
          <path d="M380 200 C420 280, 480 320, 620 360" className="hero-draw" />
        </g>

        {/* Orbiting ring */}
        <g className="hero-orbit origin-center" style={{ transformOrigin: "520px 160px" }}>
          <circle cx="520" cy="160" r="54" fill="none" className="stroke-teal/25 dark:stroke-teal/40" strokeWidth="1" strokeDasharray="3 7" />
          <circle cx="574" cy="160" r="3.5" className="fill-teal/80" />
        </g>

        <g className="hero-orbit-slow origin-center" style={{ transformOrigin: "220px 280px" }}>
          <circle cx="220" cy="280" r="36" fill="none" className="stroke-primary/20 dark:stroke-primary/30" strokeWidth="1" strokeDasharray="2 6" />
          <circle cx="256" cy="280" r="2.5" className="fill-primary/70" />
        </g>

        {/* Floating nodes */}
        <g className="hero-float">
          <circle cx="380" cy="200" r="18" fill="url(#hero-node-glow)" />
          <circle cx="380" cy="200" r="5" className="fill-primary" />
        </g>
        <g className="hero-float-delay">
          <rect x="112" y="328" width="14" height="14" rx="3" className="fill-teal/50 rotate-12" />
        </g>
        <g className="hero-float-delay-2">
          <polygon points="640,100 652,120 628,120" className="fill-primary/45" />
        </g>
        <g className="hero-float">
          <circle cx="620" cy="360" r="4" className="fill-teal/70" />
        </g>

        {/* Soft particles */}
        {[
          [90, 80],
          [150, 200],
          [300, 90],
          [450, 320],
          [700, 240],
          [760, 80],
          [60, 400],
          [500, 60],
        ].map(([x, y], index) => (
          <circle
            key={`${x}-${y}`}
            cx={x}
            cy={y}
            r={index % 2 === 0 ? 1.6 : 1.2}
            className={cn(
              index % 3 === 0 ? "fill-primary/40" : "fill-teal/35",
              "hero-particle",
              index % 2 === 0 && "hero-particle-delay",
            )}
          />
        ))}
      </svg>
    </div>
  );
}
