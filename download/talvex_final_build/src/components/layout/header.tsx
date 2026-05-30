"use client";

import { Menu, Bell } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface HeaderProps {
  title: string;
  onToggleSidebar: () => void;
  leakAlerts?: number;
}

export function Header({ title, onToggleSidebar, leakAlerts = 0 }: HeaderProps) {
  return (
    <>
      {/* M3 Top App Bar: Surface background, no shadow, bottom border with Outline Variant */}
      <header className="sticky top-0 z-30 flex items-center justify-between h-16 px-4 md:px-6 bg-surface border-b border-outline-variant">
      <div className="flex items-center gap-3">
        <Button
          variant="ghost"
          size="icon"
          className="lg:hidden h-10 w-10 rounded-xl"
          onClick={onToggleSidebar}
        >
          <Menu className="h-5 w-5" />
        </Button>
        {/* M3 Headline Small: 1.5rem / 500 weight / 2rem line-height */}
        <h1 className="text-[1.5rem] font-medium leading-8 tracking-tight text-on-surface">{title}</h1>
      </div>

      <div className="flex items-center gap-2">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon" className="h-10 w-10 rounded-xl relative">
              <Bell className="h-5 w-5" />
              {leakAlerts > 0 && (
                <Badge className="absolute -top-1 -right-1 h-5 min-w-5 p-0 flex items-center justify-center text-[10px] bg-destructive text-destructive-foreground border-0 rounded-lg">
                  {leakAlerts}
                </Badge>
              )}
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            {leakAlerts > 0 ? `${leakAlerts} privacy alerts` : "No alerts"}
          </TooltipContent>
        </Tooltip>
      </div>
    </header>
    </>
  );
}
