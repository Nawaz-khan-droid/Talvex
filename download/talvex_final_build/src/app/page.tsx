"use client";

import { useState, useEffect, useCallback, Suspense } from "react";
import { useSearchParams } from "next/navigation";
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
    setLoading(false);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      setLoading(true);
      const [appRes, personaRes, analyticsRes, canaryRes] = await Promise.all([
        fetch("/api/applications", { signal: controller.signal }),
        fetch("/api/personas", { signal: controller.signal }),
        fetch("/api/analytics", { signal: controller.signal }),
        fetch("/api/canary", { signal: controller.signal }),
      ]);
      if (controller.signal.aborted) return;
      if (appRes.ok) setApplications(await appRes.json());
      if (personaRes.ok) setPersonas(await personaRes.json());
      if (analyticsRes.ok) setAnalytics(await analyticsRes.json());
      if (canaryRes.ok) setCanaries(await canaryRes.json());
      setLoading(false);
    };
    load();
    return () => controller.abort();
  }, []);

  const handleNavigate = useCallback((tab: string) => {
    setActiveTab(tab as TabId);
  }, []);

  const handleSelectApplication = useCallback((app: Application) => {
    setActiveTab("pipeline");
  }, []);

  return (
    <div className="flex h-screen overflow-hidden bg-background">
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
        />

        <main className="flex-1 overflow-y-auto p-4 md:p-6">
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
