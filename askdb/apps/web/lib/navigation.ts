import type { Role } from "@nql/shared-types";
import {
  Activity,
  BarChart3,
  BookOpen,
  Boxes,
  History,
  Home,
  LineChart,
  type LucideIcon,
  MessageSquare,
  Network,
  ScrollText,
  ShieldCheck,
  Star,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Minimum role required. Items above the caller's role are hidden. */
  minRole: Role;
  description: string;
}

export interface NavSection {
  id: string;
  label: string | null;
  items: NavItem[];
}

/** Left sidebar — flagship workspace order for business users. */
export const NAV_SECTIONS: NavSection[] = [
  {
    id: "workspace",
    label: null,
    items: [
      {
        href: "/home",
        label: "Home",
        icon: Home,
        minRole: "viewer",
        description: "Ask DB hero, live demo, and connected data sources.",
      },
      {
        href: "/dashboard",
        label: "Executive Intelligence",
        icon: BarChart3,
        minRole: "viewer",
        description: "Domain-aware KPIs, grounded AI insights, and performance analytics.",
      },
      {
        href: "/chat",
        label: "AI Chat",
        icon: MessageSquare,
        minRole: "analyst",
        description: "Ask questions in natural language over governed data.",
      },
      {
        href: "/analytics-builder",
        label: "Analytics Builder",
        icon: LineChart,
        minRole: "analyst",
        description: "No-code business analytics over the semantic layer.",
      },
      {
        href: "/data-quality",
        label: "Data Trust Center",
        icon: ShieldCheck,
        minRole: "viewer",
        description: "Observability, quality, governance, and trust scoring.",
      },
      {
        href: "/semantic?tab=graph",
        label: "Ontology Browser",
        icon: Network,
        minRole: "viewer",
        description: "Explore the enterprise knowledge graph.",
      },
    ],
  },
  {
    id: "explore",
    label: "Explore",
    items: [
      {
        href: "/data-preview",
        label: "Data Preview",
        icon: Boxes,
        minRole: "viewer",
        description: "Browse governed tables from the active industry pack.",
      },
      {
        href: "/semantic",
        label: "Semantic Atlas",
        icon: Network,
        minRole: "viewer",
        description: "Ontology browser, semantic model, and business glossary.",
      },
      {
        href: "/knowledge",
        label: "Knowledge",
        icon: BookOpen,
        minRole: "viewer",
        description: "Documents, ingestion jobs and retrieval sources.",
      },
    ],
  },
  {
    id: "activity",
    label: "Activity",
    items: [
      {
        href: "/saved-questions",
        label: "Saved Questions",
        icon: Star,
        minRole: "viewer",
        description: "Personal and shared question collections.",
      },
      {
        href: "/query-history",
        label: "Query History",
        icon: History,
        minRole: "viewer",
        description: "Every executed question with SQL, cost and status.",
      },
      {
        href: "/llm-observability",
        label: "LLM Observability",
        icon: Activity,
        minRole: "analyst",
        description: "Cost analytics and LLM sampling controls.",
      },
      {
        href: "/system-logs",
        label: "System Logs",
        icon: ScrollText,
        minRole: "admin",
        description: "Execution logs, errors and performance stages.",
      },
    ],
  },
];

/** Primary top tabs — includes Analytics Builder as a flagship surface. */
export const MAIN_TABS = [
  { href: "/home", label: "Home", icon: Home },
  { href: "/dashboard", label: "Executive Intelligence", icon: BarChart3 },
  { href: "/chat", label: "AI Chat", icon: MessageSquare },
  { href: "/analytics-builder", label: "Analytics Builder", icon: LineChart },
] as const;

const ROLE_RANK: Record<Role, number> = { viewer: 0, analyst: 1, admin: 2 };

export function visibleSections(role: Role): NavSection[] {
  return NAV_SECTIONS.map((section) => ({
    ...section,
    items: section.items.filter((item) => ROLE_RANK[role] >= ROLE_RANK[item.minRole]),
  })).filter((section) => section.items.length > 0);
}
