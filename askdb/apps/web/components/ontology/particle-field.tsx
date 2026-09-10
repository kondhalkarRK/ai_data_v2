"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

const PARTICLES = Array.from({ length: 28 }, (_, index) => ({
  id: index,
  left: `${(index * 37) % 100}%`,
  top: `${(index * 53) % 100}%`,
  size: 2 + (index % 4),
  dx: `${((index % 5) - 2) * 10}px`,
  dy: `${((index % 7) - 3) * -8}px`,
  duration: `${10 + (index % 8)}s`,
  delay: `${(index % 6) * 0.4}s`,
}));

export function ParticleField({ className }: { className?: string }) {
  return (
    <div className={cn("galaxy-particles", className)} aria-hidden="true">
      {PARTICLES.map((particle) => (
        <span
          key={particle.id}
          className="galaxy-particle"
          style={
            {
              left: particle.left,
              top: particle.top,
              width: particle.size,
              height: particle.size,
              animationDelay: particle.delay,
              "--dx": particle.dx,
              "--dy": particle.dy,
              "--duration": particle.duration,
            } as React.CSSProperties
          }
        />
      ))}
    </div>
  );
}
