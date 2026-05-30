"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  GitBranch,
  UserCog,
  Download,
  FileText,
  Shield,
  BarChart3,
  Settings,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

const navItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/?tab=pipeline", label: "Pipeline", icon: GitBranch },
  { href: "/?tab=personas", label: "Personas", icon: UserCog },
  { href: "/?tab=ingest", label: "Ingest", icon: Download },
  { href: "/?tab=resume", label: "Resume", icon: FileText },
  { href: "/?tab=privacy", label: "Privacy", icon: Shield },
  { href: "/?tab=analytics", label: "Analytics", icon: BarChart3 },
  { href: "/?tab=settings", label: "Settings", icon: Settings },
];

interface AppSidebarProps {
  activeTab: string;
  onNavigate: (tab: string) => void;
  onClose?: () => void;
  className?: string;
}

export function AppSidebar({ activeTab, onNavigate, onClose, className }: AppSidebarProps) {
  const pathname = usePathname();

  return (
    <div
      className={cn(
        "flex flex-col h-full bg-sidebar text-sidebar-foreground",
        className
      )}
    >
      {/* M3 Navigation Drawer: Logo area */}
      <div className="flex items-center justify-between px-4 h-16">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl bg-primary-container flex items-center justify-center">
            <span className="text-on-primary-container font-bold text-sm">T</span>
          </div>
          <span className="font-medium text-base tracking-tight text-on-surface">TALVEX</span>
        </div>
        {onClose && (
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden h-10 w-10 rounded-xl"
            onClick={onClose}
          >
            <X className="h-5 w-5" />
          </Button>
        )}
      </div>

      <ScrollArea className="flex-1 px-3 py-2">
        {/* M3 Navigation Drawer: Nav items */}
        <nav className="flex flex-col gap-1">
          {navItems.map((item) => {
            const isActive =
              (item.href === "/" && activeTab === "dashboard") ||
              item.href === `/?tab=${activeTab}`;

            return (
              <button
                key={item.label}
                onClick={() => {
                  onNavigate(item.label.toLowerCase());
                  onClose?.();
                }}
                className={cn(
                  "relative flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-colors",
                  "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-sidebar-ring",
                  /* M3: Active nav item — filled Primary Container, On Primary Container text */
                  isActive
                    ? "bg-primary-container text-on-primary-container font-medium"
                    : "text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface"
                )}
              >
                {/* M3: 80px active indicator strip on the left in Primary color */}
                {isActive && (
                  <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-8 rounded-r-full bg-primary" />
                )}
                <item.icon className="h-5 w-5 shrink-0" />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        <Separator className="my-4 bg-outline-variant" />

        {/* M3: Status section */}
        <div className="px-3 py-2">
          <p className="text-xs text-on-surface-variant/60 font-medium uppercase tracking-wider">
            Status
          </p>
          <div className="mt-2 flex items-center gap-2 text-xs text-on-surface-variant">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            System Online
          </div>
        </div>
      </ScrollArea>
    </div>
  );
}
