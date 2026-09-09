"use client";

import { PanelLeftOpen, Presentation, Search } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { IndustrySwitcher } from "@/components/shell/industry-switcher";
import { ThemeToggle } from "@/components/shell/theme-toggle";
import { Button } from "@/components/ui/button";
import { MAIN_TABS } from "@/lib/navigation";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui-store";

export function Topbar() {
  const pathname = usePathname();
  const collapsed = useUiStore((state) => state.sidebarCollapsed);
  const toggleSidebar = useUiStore((state) => state.toggleSidebar);
  const presenterMode = useUiStore((state) => state.presenterMode);
  const togglePresenterMode = useUiStore((state) => state.togglePresenterMode);
  const setCommandPaletteOpen = useUiStore((state) => state.setCommandPaletteOpen);

  return (
    <header className="sticky top-0 z-20 flex h-[var(--topbar-height)] shrink-0 items-center gap-3 border-b border-border bg-background/85 px-4 backdrop-blur">
      {collapsed ? (
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={toggleSidebar}
          aria-label="Expand sidebar"
          className="lg:hidden"
        >
          <PanelLeftOpen />
        </Button>
      ) : null}

      {/* Main workspace tabs. Real links, so they are bookmarkable and the back button
          behaves — the legacy Streamlit tabs were neither. */}
      <nav aria-label="Workspace" className="min-w-0 flex-1">
        <ul className="flex items-center gap-1 overflow-x-auto">
          {MAIN_TABS.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || pathname.startsWith(`${href}/`);
            return (
              <li key={href}>
                <Link
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex items-center gap-2 whitespace-nowrap rounded-[var(--radius-control)] px-3 py-1.5 text-sm transition-colors",
                    active
                      ? "bg-muted font-medium text-foreground"
                      : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
                  )}
                >
                  <Icon className="size-4" aria-hidden="true" />
                  {label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="flex shrink-0 items-center gap-1.5">
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => setCommandPaletteOpen(true)}
          aria-label="Search (Ctrl+K)"
          title="Search  Ctrl+K"
        >
          <Search />
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={togglePresenterMode}
          aria-pressed={presenterMode}
          aria-label="Presenter mode"
          title="Presenter mode"
          className={cn(presenterMode && "bg-primary/10 text-primary")}
        >
          <Presentation />
        </Button>
        <IndustrySwitcher />
        <ThemeToggle className="hidden md:inline-flex" />
      </div>
    </header>
  );
}
