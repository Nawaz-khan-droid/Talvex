"use client";

import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { LogIn, UserPlus, Loader2 } from "lucide-react";

interface AuthDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAuthSuccess?: () => void;
}

interface AuthState {
  user: {
    user_id: string;
    email: string;
    role: string;
    display_name: string | null;
  } | null;
}

// Global auth state (shared across components without a full provider)
let _listeners: Array<() => void> = [];
let _authState: AuthState = { user: null };

function _emitChange() {
  _listeners.forEach((l) => l());
}

export function getAuthState(): AuthState {
  return _authState;
}

export function subscribeAuth(callback: () => void): () => void {
  _listeners.push(callback);
  return () => {
    _listeners = _listeners.filter((l) => l !== callback);
  };
}

export function logoutAuth() {
  fetch("/api/auth/logout", { method: "POST" }).catch(() => {});
  _authState = { user: null };
  _emitChange();
}

export function AuthDialog({ open, onOpenChange, onAuthSuccess }: AuthDialogProps) {
  const [activeTab, setActiveTab] = useState<"login" | "register">("login");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Login form state
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");

  // Register form state
  const [regEmail, setRegEmail] = useState("");
  const [regPassword, setRegPassword] = useState("");
  const [regDisplayName, setRegDisplayName] = useState("");

  // Reset form when dialog opens/closes or tab changes
  useEffect(() => {
    if (open) {
      setError(null);
      setLoading(false);
      setLoginEmail("");
      setLoginPassword("");
      setRegEmail("");
      setRegPassword("");
      setRegDisplayName("");
    }
  }, [open]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: loginEmail, password: loginPassword }),
      });

      const data = await res.json();

      if (!res.ok) {
        setError(data.detail || "Login failed");
        return;
      }

      _authState = { user: data };
      _emitChange();
      onOpenChange(false);
      onAuthSuccess?.();
    } catch {
      setError("Network error. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const res = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: regEmail,
          password: regPassword,
          display_name: regDisplayName || undefined,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        setError(data.detail || "Registration failed");
        return;
      }

      _authState = { user: data };
      _emitChange();
      onOpenChange(false);
      onAuthSuccess?.();
    } catch {
      setError("Network error. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="sm:max-w-md p-0 gap-0 overflow-hidden"
        showCloseButton={true}
      >
        <DialogTitle className="sr-only">
          {activeTab === "login" ? "Log in to TALVEX" : "Create an account"}
        </DialogTitle>
        <DialogDescription className="sr-only">
          {activeTab === "login"
            ? "Enter your credentials to access your account"
            : "Create a new TALVEX account"}
        </DialogDescription>

        <div className="px-6 pt-6 pb-4">
          <h2 className="text-[1.5rem] font-medium leading-8 text-on-surface">
            {activeTab === "login" ? "Welcome back" : "Create account"}
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            {activeTab === "login"
              ? "Sign in to access your job pipeline"
              : "Start tracking your applications with TALVEX"}
          </p>
        </div>

        <Tabs
          value={activeTab}
          onValueChange={(v) => {
            setActiveTab(v as "login" | "register");
            setError(null);
          }}
          className="px-6"
        >
          <TabsList className="grid w-full grid-cols-2 mb-4">
            <TabsTrigger value="login" className="gap-1.5">
              <LogIn className="size-3.5" />
              Login
            </TabsTrigger>
            <TabsTrigger value="register" className="gap-1.5">
              <UserPlus className="size-3.5" />
              Register
            </TabsTrigger>
          </TabsList>

          {error && (
            <div className="mb-4 p-3 rounded-xl bg-destructive/10 text-destructive text-sm border border-destructive/20">
              {error}
            </div>
          )}

          <TabsContent value="login" className="mt-0">
            <form onSubmit={handleLogin} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="auth-login-email">Email</Label>
                <Input
                  id="auth-login-email"
                  type="email"
                  placeholder="you@example.com"
                  required
                  value={loginEmail}
                  onChange={(e) => setLoginEmail(e.target.value)}
                  disabled={loading}
                  className="rounded-xl"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="auth-login-password">Password</Label>
                <Input
                  id="auth-login-password"
                  type="password"
                  placeholder="Enter your password"
                  required
                  minLength={8}
                  value={loginPassword}
                  onChange={(e) => setLoginPassword(e.target.value)}
                  disabled={loading}
                  className="rounded-xl"
                />
              </div>
              <Button
                type="submit"
                className="w-full rounded-xl"
                disabled={loading}
              >
                {loading ? (
                  <>
                    <Loader2 className="size-4 animate-spin" />
                    Signing in...
                  </>
                ) : (
                  <>
                    <LogIn className="size-4" />
                    Sign In
                  </>
                )}
              </Button>
            </form>
          </TabsContent>

          <TabsContent value="register" className="mt-0">
            <form onSubmit={handleRegister} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="auth-reg-email">Email</Label>
                <Input
                  id="auth-reg-email"
                  type="email"
                  placeholder="you@example.com"
                  required
                  value={regEmail}
                  onChange={(e) => setRegEmail(e.target.value)}
                  disabled={loading}
                  className="rounded-xl"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="auth-reg-display-name">Display Name (optional)</Label>
                <Input
                  id="auth-reg-display-name"
                  type="text"
                  placeholder="Alex Johnson"
                  value={regDisplayName}
                  onChange={(e) => setRegDisplayName(e.target.value)}
                  disabled={loading}
                  className="rounded-xl"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="auth-reg-password">Password</Label>
                <Input
                  id="auth-reg-password"
                  type="password"
                  placeholder="Min. 8 characters"
                  required
                  minLength={8}
                  value={regPassword}
                  onChange={(e) => setRegPassword(e.target.value)}
                  disabled={loading}
                  className="rounded-xl"
                />
              </div>
              <Button
                type="submit"
                className="w-full rounded-xl"
                disabled={loading}
              >
                {loading ? (
                  <>
                    <Loader2 className="size-4 animate-spin" />
                    Creating account...
                  </>
                ) : (
                  <>
                    <UserPlus className="size-4" />
                    Create Account
                  </>
                )}
              </Button>
            </form>
          </TabsContent>
        </Tabs>

        <div className="px-6 pb-6 pt-2">
          <p className="text-xs text-center text-muted-foreground">
            {activeTab === "login" ? (
              <>
                Don&apos;t have an account?{" "}
                <button
                  type="button"
                  className="text-primary hover:underline font-medium"
                  onClick={() => setActiveTab("register")}
                >
                  Sign up
                </button>
              </>
            ) : (
              <>
                Already have an account?{" "}
                <button
                  type="button"
                  className="text-primary hover:underline font-medium"
                  onClick={() => setActiveTab("login")}
                >
                  Sign in
                </button>
              </>
            )}
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default AuthDialog;
