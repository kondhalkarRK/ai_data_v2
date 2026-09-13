"use client";

import type { UserProfile } from "@nql/shared-types";
import { LogOut, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Logo } from "@/components/brand/logo";
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

export function Sidebar({ user }: { user: UserProfile }) {
  const pathname = usePathname();
  const collapsed = useUiStore((state) => state.sidebarCollapsed);
  const toggleSidebar = useUiStore((state) => state.toggleSidebar);
  const logout = useLogout();

  const sections = visibleSections(user.role);

  return (
    <aside
      aria-label="Primary"
      className={cn(
        "flex h-dvh shrink-0 flex-col border-r border-sidebar-border bg-sidebar transition-[width] duration-200",
        collapsed ? "w-[var(--sidebar-width-collapsed)]" : "w-[var(--sidebar-width)]",
      )}
    >
      <div
        className={cn(
          "flex h-[var(--topbar-height)] items-center border-b border-sidebar-border px-3",
          collapsed ? "justify-center" : "justify-between",
        )}
      >
        <Link
          href="/data-preview"
          className="rounded-[var(--radius-control)]"
          aria-label="NQL Insight home"
        >
          <Logo compact={collapsed} size="sm" />
        </Link>
        {collapsed ? null : (
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={toggleSidebar}
            aria-label="Collapse sidebar"
          >
            <PanelLeftClose />
          </Button>
        )}
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-3" aria-label="Sections">
        {sections.map((section) => (
          <div key={section.id} className="mb-4 last:mb-0">
            {section.label && !collapsed ? (
              <p className="px-2.5 pb-1.5 text-2xs font-medium text-muted-foreground">
                {section.label}
              </p>
            ) : null}
            <ul className="space-y-0.5">
              {section.items.map((item) => {
                // Exact match, or a nested route below this item.
                const active =
                  pathname === item.href || pathname.startsWith(`${item.href}/`);
                const Icon = item.icon;
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      title={collapsed ? item.label : item.description}
                      className={cn(
                        "flex items-center gap-2.5 rounded-[var(--radius-control)] px-2.5 py-2 text-sm transition-colors",
                        collapsed && "justify-center px-0",
                        active
                          ? "bg-primary/10 font-medium text-primary"
                          : "text-muted-foreground hover:bg-muted hover:text-foreground",
                      )}
                    >
                      <Icon className="size-4 shrink-0" aria-hidden="true" />
                      {collapsed ? (
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

      <div className="border-t border-sidebar-border p-2">
        {collapsed ? (
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
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-foreground">
                  {user.fullName}
                </p>
                <p className="truncate text-2xs capitalize text-muted-foreground">
                  {user.role}
                </p>
              </div>
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
