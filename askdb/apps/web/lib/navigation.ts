import type { Role } from "@nql/shared-types";
import {
  BarChart3,
  BookOpen,
  Boxes,
  Database,
  History,
  type LucideIcon,
  MessageSquare,
  Network,
  ReceiptIndianRupee,
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

/** Left sidebar, in the order given by spec section 9. */
export const NAV_SECTIONS: NavSection[] = [
  {
    id: "workspace",
    label: null,
    items: [
      {
        href: "/data-sources",
        label: "Data Sources",
        icon: Database,
        minRole: "viewer",
        description: "Connected analytics databases and their status.",
      },
      {
        href: "/dashboard",
        label: "Executive Intelligence",
        icon: BarChart3,
        minRole: "viewer",
        description: "Domain-aware KPIs, grounded AI insights, and What-If analysis.",
      },
      {
        href: "/data-quality",
        label: "Data Quality",
        icon: ShieldCheck,
        minRole: "viewer",
        description: "Rules, scores, issues and evaluation history.",
      },
      {
        href: "/chat",
        label: "AI Chat",
        icon: MessageSquare,
        minRole: "analyst",
        description: "Ask questions in natural language over governed data.",
      },
    ],
  },
  {
    id: "semantic",
    label: "Semantics",
    items: [
      {
        href: "/semantic",
        label: "Semantic Core",
        icon: Network,
        minRole: "viewer",
        description: "Models, relationships, joins, glossary and ontology.",
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
        href: "/cost-analytics",
        label: "Cost Analytics",
        icon: ReceiptIndianRupee,
        minRole: "analyst",
        description: "Token usage and estimated spend by model and user.",
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

/** The three main tabs above the workspace (spec section 9). */
export const MAIN_TABS = [
  { href: "/data-preview", label: "Data Preview", icon: Boxes },
  { href: "/dashboard", label: "Executive Intelligence", icon: BarChart3 },
  { href: "/chat", label: "AI Chat", icon: MessageSquare },
] as const;

const ROLE_RANK: Record<Role, number> = { viewer: 0, analyst: 1, admin: 2 };

export function visibleSections(role: Role): NavSection[] {
  return NAV_SECTIONS.map((section) => ({
    ...section,
    items: section.items.filter((item) => ROLE_RANK[role] >= ROLE_RANK[item.minRole]),
  })).filter((section) => section.items.length > 0);
}
