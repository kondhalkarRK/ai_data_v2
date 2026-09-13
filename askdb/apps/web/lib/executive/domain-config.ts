/** Client mirror of domain configuration — KPI display order & copy only.
 * Live availability still comes from the Executive Intelligence API.
 */

import type { Industry } from "@nql/shared-types";

export interface DomainConfig {
  title: string;
  tagline: string;
}

const CONFIG: Record<string, DomainConfig> = {
  automotive: {
    title: "Automotive Intelligence",
    tagline: "Your business, explained by AI",
  },
  insurance: {
    title: "Insurance Intelligence",
    tagline: "Your business, explained by AI",
  },
};

export function getDomainConfig(industry: Industry | string): DomainConfig {
  return (
    CONFIG[industry] ?? {
      title: "Executive Intelligence",
      tagline: "Your business, explained by AI",
    }
  );
}
