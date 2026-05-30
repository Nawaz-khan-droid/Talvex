"use client";

import { useState, useEffect, useCallback } from "react";
import { Menu, Bell, Sun, Moon, LogIn, LogOut } from "lucide-react";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  AuthDialog,
  getAuthState,
  subscribeAuth,
  logoutAuth,
} from "@/components/auth/auth-dialog";

interface HeaderProps {
  title: string;
  onToggleSidebar: () => void;
  leakAlerts?: number;
  onAuthChange?: () => void;
}

export function Header({
  title,
  onToggleSidebar,
  leakAlerts = 0,
  onAuthChange,
}: HeaderProps) {
  const { theme, setTheme } = useTheme();
  const [authDialogOpen, setAuthDialogOpen] = useState(false);
  const [userEmail, setUserEmail] = useState<string | null>(null);

  useEffect(() => {
    // Check initial auth state
    const state = getAuthState();
    if (state.user) {
      setUserEmail(state.user.email);
    }

    // Subscribe to auth changes
    return subscribeAuth(() => {
      const s = getAuthState();
      setUserEmail(s.user ? s.user.email : null);
      onAuthChange?.();
    });
  }, [onAuthChange]);

  const handleAuthSuccess = useCallback(() => {
    onAuthChange?.();
  }, [onAuthChange]);

  const handleLogout = useCallback(() => {
    logoutAuth();
    onAuthChange?.();
  }, [onAuthChange]);

  return (
    <>
      <AuthDialog
        open={authDialogOpen}
        onOpenChange={setAuthDialogOpen}
        onAuthSuccess={handleAuthSuccess}
      />
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
        {/* Auth button: Login or User email + Logout */}
        {userEmail ? (
          <div className="flex items-center gap-2">
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="hidden sm:inline-flex items-center text-sm text-muted-foreground px-2 max-w-[180px] truncate">
                  {userEmail}
                </span>
              </TooltipTrigger>
              <TooltipContent>
                {userEmail}
              </TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-10 w-10 rounded-xl"
                  onClick={handleLogout}
                >
                  <LogOut className="h-5 w-5" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                Log out
              </TooltipContent>
            </Tooltip>
          </div>
        ) : (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="h-10 rounded-xl gap-1.5"
                onClick={() => setAuthDialogOpen(true)}
              >
                <LogIn className="h-4 w-4" />
                <span className="hidden sm:inline">Login</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              Log in to your account
            </TooltipContent>
          </Tooltip>
        )}

        {/* Theme Toggle */}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-10 w-10 rounded-xl"
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            >
              <Sun className="h-5 w-5 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
              <Moon className="absolute h-5 w-5 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
              <span className="sr-only">Toggle theme</span>
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            {theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          </TooltipContent>
        </Tooltip>

        {/* Notifications */}
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
