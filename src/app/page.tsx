"use client";

import { useState, useEffect, useCallback, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { Header } from "@/components/layout/header";
import {
  StatsCards,
  RecentApplications,
  FunnelChart,
  QuickActions,
} from "@/components/dashboard/dashboard-components";
import { KanbanBoard } from "@/components/pipeline/pipeline-components";
import { PersonaList } from "@/components/personas/persona-components";
import { JobAnalyzer } from "@/components/ingest/ingest-components";
import { ResumeBuilder } from "@/components/resume/resume-components";
import { PrivacySection } from "@/components/privacy/privacy-components";
import { AnalyticsDashboard } from "@/components/analytics/analytics-components";
import { OnboardingWizard } from "@/components/onboarding/onboarding-wizard";
import { SettingsPanel } from "@/components/settings/settings-panel";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { useIsMobile } from "@/hooks/use-mobile";
import { AlertCircle, X, LogIn } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  AuthDialog,
  getAuthState,
  subscribeAuth,
} from "@/components/auth/auth-dialog";
import { Loader2 } from "lucide-react";
import type {
  Application,
  JobPersona,
  AnalyticsData,
} from "@/lib/types";

type TabId =
  | "dashboard"
  | "pipeline"
  | "personas"
  | "ingest"
  | "resume"
  | "privacy"
  | "analytics"
  | "settings";

const TAB_TITLES: Record<TabId, string> = {
  dashboard: "Dashboard",
  pipeline: "Pipeline",
  personas: "Personas",
  ingest: "Ingest & Analyze",
  resume: "Resume Builder",
  privacy: "Privacy Monitor",
  analytics: "Analytics",
  settings: "Settings",
};

function HomePageContent() {
  const searchParams = useSearchParams();
  const initialTab = searchParams.get("tab") as TabId | null;
  const [activeTab, setActiveTab] = useState<TabId>(initialTab || "dashboard");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const isMobile = useIsMobile();

  const [applications, setApplications] = useState<Application[]>([]);
  const [personas, setPersonas] = useState<JobPersona[]>([]);
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [canaries, setCanaries] = useState<unknown[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [authDialogOpen, setAuthDialogOpen] = useState(false);

  const fetchPersonas = useCallback(async () => {
    try {
      const res = await fetch("/api/personas");
      if (res.ok) setPersonas(await res.json());
    } catch {
      // silently handle
    }
  }, []);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setFetchError(null);
    const [appRes, personaRes, analyticsRes, canaryRes] = await Promise.all([
      fetch("/api/applications"),
      fetch("/api/personas"),
      fetch("/api/analytics"),
      fetch("/api/canary"),
    ]);
    if (appRes.ok) setApplications(await appRes.json());
    if (personaRes.ok) setPersonas(await personaRes.json());
    if (analyticsRes.ok) setAnalytics(await analyticsRes.json());
    if (canaryRes.ok) setCanaries(await canaryRes.json());

    // Check for errors from non-ok responses
    const failedRes = [appRes, personaRes, analyticsRes, canaryRes].find((r) => !r.ok);
    if (failedRes) {
      if (failedRes.status === 401) {
        setFetchError("401");
      } else {
        setFetchError(`API error: ${failedRes.status}`);
      }
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      setLoading(true);
      setFetchError(null);
      let hasError = false;
      let errorStatus = 0;
      try {
        const [appRes, personaRes, analyticsRes, canaryRes] = await Promise.all([
          fetch("/api/applications", { signal: controller.signal }),
          fetch("/api/personas", { signal: controller.signal }),
          fetch("/api/analytics", { signal: controller.signal }),
          fetch("/api/canary", { signal: controller.signal }),
        ]);
        if (controller.signal.aborted) return;

        const results = [appRes, personaRes, analyticsRes, canaryRes];
        if (appRes.ok) setApplications(await appRes.json());
        if (personaRes.ok) setPersonas(await personaRes.json());
        if (analyticsRes.ok) setAnalytics(await analyticsRes.json());
        if (canaryRes.ok) setCanaries(await canaryRes.json());

        // Check for any non-ok responses
        const failed = results.find((r) => !r.ok);
        if (failed) {
          hasError = true;
          errorStatus = failed.status;
        }
      } catch {
        hasError = true;
        errorStatus = 0;
      }

      if (hasError) {
        if (errorStatus === 401) {
          setFetchError("401");
        } else if (errorStatus > 0) {
          setFetchError(`API error: ${errorStatus}`);
        } else {
          setFetchError("Network error. Could not reach the server.");
        }
      }
      setLoading(false);
    };
    load();
    return () => controller.abort();
  }, []);

  const router = useRouter();

  const handleNavigate = useCallback((tab: string) => {
    setActiveTab(tab as TabId);
    router.push(`?tab=${tab}`, { scroll: false });
  }, [router]);

  const handleSelectApplication = useCallback((app: Application) => {
    setActiveTab("pipeline");
    router.push("?tab=pipeline", { scroll: false });
  }, [router]);

  const handleAuthChange = useCallback(() => {
    // Re-fetch data after login/logout
    fetchAll();
  }, [fetchAll]);

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <AuthDialog
        open={authDialogOpen}
        onOpenChange={setAuthDialogOpen}
        onAuthSuccess={handleAuthChange}
      />
      {isMobile ? (
        <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
          <SheetContent side="left" className="p-0 w-64">
            <SheetTitle className="sr-only">Navigation</SheetTitle>
            <AppSidebar
              activeTab={activeTab}
              onNavigate={handleNavigate}
              onClose={() => setSidebarOpen(false)}
            />
          </SheetContent>
        </Sheet>
      ) : (
        <div className="hidden lg:flex w-64 flex-shrink-0">
          <AppSidebar activeTab={activeTab} onNavigate={handleNavigate} />
        </div>
      )}

      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <Header
          title={TAB_TITLES[activeTab]}
          onToggleSidebar={() => setSidebarOpen(true)}
          leakAlerts={analytics?.leakAlerts ?? 0}
          onAuthChange={handleAuthChange}
        />

        <main className="flex-1 overflow-y-auto p-4 md:p-6">
          {/* Error banner */}
          {fetchError && (
            <div className="mb-4 flex items-start gap-3 p-4 rounded-xl bg-destructive/10 border border-destructive/20">
              <AlertCircle className="size-5 text-destructive shrink-0 mt-0.5" />
              <div className="flex-1 min-w-0">
                {fetchError === "401" ? (
                  <>
                    <p className="text-sm font-medium text-destructive">
                      Please log in to see your data
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Sign in to access your applications, personas, and analytics.
                    </p>
                  </>
                ) : (
                  <p className="text-sm font-medium text-destructive">
                    {fetchError}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                {fetchError === "401" && (
                  <Button
                    size="sm"
                    variant="outline"
                    className="gap-1.5 rounded-xl"
                    onClick={() => setAuthDialogOpen(true)}
                  >
                    <LogIn className="size-3.5" />
                    Log in
                  </Button>
                )}
                <Button
                  size="icon"
                  variant="ghost"
                  className="size-7 rounded-lg"
                  onClick={() => setFetchError(null)}
                >
                  <X className="size-3.5" />
                </Button>
              </div>
            </div>
          )}

          {activeTab === "dashboard" && (
            <div className="space-y-4 md:space-y-6">
              <StatsCards
                analytics={analytics}
                loading={loading}
                onNewApplication={() => handleNavigate("ingest")}
                onCreatePersona={() => handleNavigate("personas")}
              />
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-6">
                <div className="lg:col-span-2 space-y-4">
                  <RecentApplications
                    applications={applications}
                    loading={loading}
                    onSelect={handleSelectApplication}
                  />
                </div>
                <div className="space-y-4">
                  <FunnelChart analytics={analytics} loading={loading} />
                  <QuickActions
                    onNewApplication={() => handleNavigate("ingest")}
                    onCreatePersona={() => handleNavigate("personas")}
                  />
                </div>
              </div>
            </div>
          )}

          {activeTab === "pipeline" && (
            <KanbanBoard
              applications={applications}
              loading={loading}
              onRefresh={fetchAll}
              onSelectApplication={handleSelectApplication}
              onNavigate={handleNavigate}
            />
          )}

          {activeTab === "personas" && (
            <PersonaList personas={personas} loading={loading} onRefresh={fetchPersonas} />
          )}

          {activeTab === "ingest" && (
            <JobAnalyzer
              personas={personas}
              loading={loading}
              onRefresh={fetchAll}
              onNavigate={handleNavigate}
            />
          )}

          {activeTab === "resume" && (
            <ResumeBuilder
              applications={applications}
              personas={personas.map((p) => ({ id: p.id, name: p.name }))}
              loading={loading}
              onRefresh={fetchAll}
            />
          )}

          {activeTab === "privacy" && (
            <PrivacySection canaries={canaries} loading={loading} />
          )}

          {activeTab === "analytics" && (
            <AnalyticsDashboard analytics={analytics} loading={loading} />
          )}

          {activeTab === "settings" && <SettingsPanel />}
        </main>
      </div>
    </div>
  );
}

export default function HomePage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-screen items-center justify-center bg-background">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      }
    >
      <OnboardingWizard />
      <HomePageContent />
    </Suspense>
  );
}
