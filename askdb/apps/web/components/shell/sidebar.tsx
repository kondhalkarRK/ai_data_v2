"use client";

import type { UserProfile } from "@nql/shared-types";
import { LogOut, PanelLeftClose, PanelLeftOpen, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

import { Logo } from "@/components/brand/logo";
import { APP_NAME } from "@/lib/brand";
import { ThemeToggle } from "@/components/shell/theme-toggle";
import { Button } from "@/components/ui/button";
import { useLogout } from "@/hooks/use-session";
import { visibleSections } from "@/lib/navigation";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui-store";

function initials(fullName: string): string {
  return fullName
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

function isActive(href: string, pathname: string, tab: string | null): boolean {
  const [path, query] = href.split("?");
  const itemTab = new URLSearchParams(query ?? "").get("tab");
  if (pathname !== path && !pathname.startsWith(`${path}/`)) return false;
  // "/semantic" and "/semantic?tab=graph" share a route; the tab decides which is active.
  return itemTab ? tab === itemTab : tab !== "graph";
}

export function Sidebar({ user }: { user: UserProfile }) {
  const pathname = usePathname();
  const tab = useSearchParams().get("tab");
  const collapsed = useUiStore((state) => state.sidebarCollapsed);
  const toggleSidebar = useUiStore((state) => state.toggleSidebar);
  const mobileNavOpen = useUiStore((state) => state.mobileNavOpen);
  const setMobileNavOpen = useUiStore((state) => state.setMobileNavOpen);
  const compact = collapsed && !mobileNavOpen;
  const logout = useLogout();

  const sections = visibleSections(user.role);

  return (
    <aside
      aria-label="Primary"
      className={cn(
        "flex h-dvh shrink-0 flex-col border-r border-sidebar-border bg-sidebar transition-[width] duration-200 ease-out",
        compact ? "w-[var(--sidebar-width-collapsed)]" : "w-[var(--sidebar-width)]",
      )}
    >
      <div
        className={cn(
          "flex h-[var(--topbar-height)] items-center px-3",
          compact ? "justify-center" : "justify-between",
        )}
      >
        <Link
          href="/home"
          onClick={() => setMobileNavOpen(false)}
          className="rounded-[var(--radius-control)]"
          aria-label={`${APP_NAME} home`}
        >
          <Logo compact={compact} size="sm" />
        </Link>
        <Button variant="ghost" size="icon-sm" onClick={() => setMobileNavOpen(false)} aria-label="Close navigation" className="lg:hidden"><X /></Button>
        {compact ? null : (
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={toggleSidebar}
            aria-label="Collapse sidebar"
            className="hidden lg:inline-flex"
          >
            <PanelLeftClose />
          </Button>
        )}
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-3" aria-label="Sections">
        {sections.map((section) => (
          <div key={section.id} className="mb-5 last:mb-0">
            {section.label && !compact ? (
              <p className="px-2.5 pb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground/80">
                {section.label}
              </p>
            ) : null}
            <ul className="space-y-0.5">
              {section.items.map((item) => {
                const active = isActive(item.href, pathname, tab);
                const Icon = item.icon;
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      onClick={() => setMobileNavOpen(false)}
                      aria-current={active ? "page" : undefined}
                      title={compact ? item.label : item.description}
                      className={cn(
                        "relative flex items-center gap-2.5 rounded-[var(--radius-control)] px-2.5 py-2 text-sm outline-none transition-[color,background-color,box-shadow] duration-150",
                        "focus-visible:ring-2 focus-visible:ring-ring/60 focus-visible:ring-offset-1 focus-visible:ring-offset-sidebar",
                      compact && "justify-center px-0",
                        active
                          ? "nav-item-active font-medium"
                          : "text-muted-foreground hover:bg-muted/55 hover:text-foreground",
                      )}
                    >
                      <Icon
                        className={cn("size-4 shrink-0", active && "text-primary")}
                        aria-hidden="true"
                      />
                      {compact ? (
                        <span className="sr-only">{item.label}</span>
                      ) : (
                        <span className="truncate">{item.label}</span>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="border-t border-sidebar-border/80 p-2">
        {compact ? (
          <div className="flex flex-col items-center gap-2">
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={toggleSidebar}
              aria-label="Expand sidebar"
            >
              <PanelLeftOpen />
            </Button>
            <span
              className="flex size-8 items-center justify-center rounded-full bg-primary/12 text-2xs font-semibold text-primary"
              title={user.fullName}
            >
              {initials(user.fullName)}
            </span>
          </div>
        ) : (
          <>
            <div className="mb-2 flex justify-center">
              <ThemeToggle />
            </div>
            <div className="flex items-center gap-2.5 rounded-[var(--radius-control)] px-1.5 py-1.5">
              <span
                aria-hidden="true"
                className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/12 text-2xs font-semibold text-primary"
              >
                {initials(user.fullName)}
              </span>
                    <Link
                href="/profile"
                className="min-w-0 flex-1 rounded-[var(--radius-control)] hover:bg-muted/60"
                title="My AI usage"
              >
                <p className="truncate text-sm font-medium text-foreground">
                  {user.fullName}
                </p>
                <p className="flex items-center gap-1.5 truncate text-2xs text-muted-foreground">
                  <span
                    className={cn(
                      "rounded px-1 py-px font-semibold tracking-wide",
                      user.role === "admin"
                        ? "bg-primary/12 text-primary"
                        : "bg-muted text-muted-foreground",
                    )}
                  >
                    {user.role.toUpperCase()}
                  </span>
                  <span className="truncate">{user.username}</span>
                </p>
              </Link>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => logout.mutate(false)}
                disabled={logout.isPending}
                aria-label="Sign out"
                title="Sign out"
              >
                <LogOut />
              </Button>
            </div>
          </>
        )}
      </div>
    </aside>
  );
}
