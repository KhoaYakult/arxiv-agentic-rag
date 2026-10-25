"use client";

import { PanelLeftOpen } from "lucide-react";
import { createContext, useContext, useState } from "react";
import { OfflineBanner } from "@/components/offline-banner";
import { PapersProvider } from "@/components/papers-context";
import { Sidebar } from "@/components/sidebar";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";

interface ShellValue {
  openSidebar: () => void;
  sidebarCollapsed: boolean;
  expandSidebar: () => void;
}
const ShellContext = createContext<ShellValue>({ openSidebar: () => {}, sidebarCollapsed: false, expandSidebar: () => {} });
export const useShell = () => useContext(ShellContext);

export function AppShell({ children }: { children: React.ReactNode }) {
  const [drawer, setDrawer] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  return (
    <PapersProvider>
      <ShellContext.Provider
        value={{ openSidebar: () => setDrawer(true), sidebarCollapsed: collapsed, expandSidebar: () => setCollapsed(false) }}
      >
        <div className="flex h-dvh overflow-hidden">
          {!collapsed && (
            <div className="hidden md:block">
              <Sidebar onCollapse={() => setCollapsed(true)} />
            </div>
          )}
          <Sheet open={drawer} onOpenChange={setDrawer}>
            <SheetContent side="left" className="gap-0 p-0 data-[side=left]:w-[264px]">
              <SheetTitle className="sr-only">Thư viện bài báo</SheetTitle>
              <Sidebar onNavigate={() => setDrawer(false)} />
            </SheetContent>
          </Sheet>
          <div className="relative flex min-w-0 flex-1 flex-col">
            <OfflineBanner />
            {collapsed && (
              <button
                onClick={() => setCollapsed(false)}
                aria-label="Mở thanh bên"
                className="absolute left-3 top-3 z-10 hidden size-8 place-items-center rounded-[6px] text-faint hover:bg-accent md:grid"
              >
                <PanelLeftOpen className="size-4" />
              </button>
            )}
            <div className="min-h-0 flex-1">{children}</div>
          </div>
        </div>
      </ShellContext.Provider>
    </PapersProvider>
  );
}
