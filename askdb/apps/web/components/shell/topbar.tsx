"use client";

import { Menu, Presentation, Search } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { IndustrySwitcher } from "@/components/shell/industry-switcher";
import { ThemeToggle } from "@/components/shell/theme-toggle";
import { Button } from "@/components/ui/button";
import { useRegionAccess } from "@/hooks/use-session";
import { MAIN_TABS } from "@/lib/navigation";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui-store";

export function Topbar() {
  const pathname = usePathname();
  const setMobileNavOpen = useUiStore((state) => state.setMobileNavOpen);
  const presenterMode = useUiStore((state) => state.presenterMode);
  const togglePresenterMode = useUiStore((state) => state.togglePresenterMode);
  const setCommandPaletteOpen = useUiStore((state) => state.setCommandPaletteOpen);
  const regionAccess = useRegionAccess();

  return (
    <header className="app-topbar sticky top-0 z-20 flex h-[var(--topbar-height)] shrink-0 items-center gap-3 border-b border-border px-4">
      {(
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => setMobileNavOpen(true)}
          aria-label="Open navigation"
          className="lg:hidden"
        >
          <Menu />
        </Button>
      )}

      {/* Main workspace tabs. Real links, so they are bookmarkable and the back button
          behaves — the legacy Streamlit tabs were neither. */}
      <nav aria-label="Workspace" className="min-w-0 flex-1">
        <ul className="flex items-center gap-0.5 overflow-x-auto">
          {MAIN_TABS.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || pathname.startsWith(`${href}/`);
            return (
              <li key={href}>
                <Link
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex items-center gap-2 whitespace-nowrap rounded-[var(--radius-control)] px-3 py-1.5 text-sm outline-none transition-[color,background-color] duration-150",
                    "focus-visible:ring-2 focus-visible:ring-ring/60",
                    active
                      ? "nav-item-active font-medium"
                      : "text-muted-foreground hover:bg-muted/55 hover:text-foreground",
                  )}
                >
                  <Icon className="size-4" aria-hidden="true" />
                  <span className="hidden sm:inline">{label}</span>
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
        {!regionAccess.unrestricted ? (
          <span className="hidden rounded-full border border-primary/30 bg-primary/10 px-2.5 py-0.5 text-[11px] font-medium text-primary sm:inline">
            {regionAccess.zones.length
              ? regionAccess.zones.map((zone) => `${zone} User`).join(" · ")
              : "Restricted User"}
          </span>
        ) : null}
        <ThemeToggle className="hidden md:inline-flex" />
      </div>
    </header>
  );
}
