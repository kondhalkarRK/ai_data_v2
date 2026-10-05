import type { Role } from "@nql/shared-types";
import {
  BarChart3,
  BookOpen,
  Boxes,
  Gauge,
  History,
  Home,
  LineChart,
  type LucideIcon,
  MessageSquare,
  Network,
  Share2,
  ShieldCheck,
  ShieldHalf,
  Star,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Minimum role required. Admin-only items are hidden from users entirely. */
  minRole: Role;
  description: string;
}

export interface NavSection {
  id: string;
  label: string | null;
  items: NavItem[];
}

/** Left sidebar. ADMIN sees everything; USER sees everything except the Admin section. */
export const NAV_SECTIONS: NavSection[] = [
  {
    id: "workspace",
    label: null,
    items: [
      {
        href: "/dashboard",
        label: "Executive Intelligence",
        icon: BarChart3,
        minRole: "user",
        description: "Domain-aware KPIs, grounded AI insights, and performance analytics.",
      },
      {
        href: "/chat",
        label: "AI Chat",
        icon: MessageSquare,
        minRole: "user",
        description: "Ask questions in natural language over governed data.",
      },
      {
        href: "/data-quality",
        label: "Data Trust",
        icon: ShieldCheck,
        minRole: "user",
        description: "Data reliability: trust score, DQ rules, alerts, freshness and drift.",
      },
      {
        href: "/semantic",
        label: "Semantic Atlas",
        icon: Network,
        minRole: "user",
        description: "Semantic model and knowledge graph.",
      },
      {
        href: "/semantic?tab=graph",
        label: "Knowledge Graph",
        icon: Share2,
        minRole: "user",
        description: "Explore the enterprise knowledge graph.",
      },
    ],
  },
  {
    id: "more",
    label: "More",
    items: [
      {
        href: "/home",
        label: "Home",
        icon: Home,
        minRole: "user",
        description: "Ask DB hero, live demo, and connected data sources.",
      },
      {
        href: "/analytics-builder",
        label: "Analytics Builder",
        icon: LineChart,
        minRole: "user",
        description: "No-code business analytics over the semantic layer.",
      },
      {
        href: "/data-preview",
        label: "Data Preview",
        icon: Boxes,
        minRole: "user",
        description: "Browse governed tables from the active industry pack.",
      },
      {
        href: "/knowledge",
        label: "Knowledge Hub (Beta)",
        icon: BookOpen,
        minRole: "user",
        description: "Retrieve cited business context for AI Chat. Still evolving.",
      },
      {
        href: "/saved-questions",
        label: "Saved Questions",
        icon: Star,
        minRole: "user",
        description: "Personal and shared question collections.",
      },
      {
        href: "/query-history",
        label: "Query History",
        icon: History,
        minRole: "user",
        description: "Every executed question with SQL and status.",
      },
      {
        href: "/profile",
        label: "My AI Usage",
        icon: Gauge,
        minRole: "user",
        description: "Your weekly AI token and call usage.",
      },
    ],
  },
  {
    id: "admin",
    label: "Admin",
    items: [
      {
        href: "/admin",
        label: "Admin Center",
        icon: ShieldHalf,
        minRole: "admin",
        description: "LLM settings, usage monitoring, data trust, semantic and entity catalog administration, audit.",
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

const ROLE_RANK: Record<Role, number> = { user: 0, admin: 1 };

export function visibleSections(role: Role): NavSection[] {
  return NAV_SECTIONS.map((section) => ({
    ...section,
    items: section.items.filter((item) => ROLE_RANK[role] >= ROLE_RANK[item.minRole]),
  })).filter((section) => section.items.length > 0);
}
