"use client";

import { useEffect, useState, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Briefcase,
  UserCog,
  TrendingUp,
  ShieldAlert,
  Plus,
  ArrowRight,
} from "lucide-react";
import type { Application, AnalyticsData } from "@/lib/types";
import { STATUS_COLORS } from "@/lib/types";

interface StatsCardsProps {
  analytics: AnalyticsData | null;
  loading: boolean;
  onNewApplication: () => void;
  onCreatePersona: () => void;
}

export function StatsCards({ analytics, loading, onNewApplication, onCreatePersona }: StatsCardsProps) {
  const stats = [
    {
      label: "Total Applications",
      value: analytics?.totalApplications ?? 0,
      icon: Briefcase,
      color: "text-primary",
      bg: "bg-primary/10",
    },
    {
      label: "Active Personas",
      value: analytics?.totalPersonas ?? 0,
      icon: UserCog,
      color: "text-purple-600 dark:text-purple-400",
      bg: "bg-purple-100 dark:bg-purple-900/30",
    },
    {
      label: "Avg Match Rate",
      value: `${analytics?.overallMatchRate ?? 0}%`,
      icon: TrendingUp,
      color: "text-emerald-600 dark:text-emerald-400",
      bg: "bg-emerald-100 dark:bg-emerald-900/30",
    },
    {
      label: "Leak Alerts",
      value: analytics?.leakAlerts ?? 0,
      icon: ShieldAlert,
      color: analytics && analytics.leakAlerts > 0 ? "text-destructive" : "text-muted-foreground",
      bg: analytics && analytics.leakAlerts > 0 ? "bg-destructive/10" : "bg-muted",
    },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
      {stats.map((stat) => (
        <Card key={stat.label} className="relative overflow-hidden">
          <CardContent className="p-4">
            {loading ? (
              <Skeleton className="h-16 w-full" />
            ) : (
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs md:text-sm text-muted-foreground font-medium">
                    {stat.label}
                  </p>
                  <p className={`text-xl md:text-2xl font-bold mt-1 ${stat.color}`}>
                    {stat.value}
                  </p>
                </div>
                <div className={`p-2 rounded-lg ${stat.bg}`}>
                  <stat.icon className={`h-4 w-4 md:h-5 md:w-5 ${stat.color}`} />
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

interface RecentApplicationsProps {
  applications: Application[];
  loading: boolean;
  onSelect: (app: Application) => void;
}

export function RecentApplications({ applications, loading, onSelect }: RecentApplicationsProps) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base font-semibold">Recent Applications</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        {loading ? (
          <div className="px-4 pb-4 space-y-3">
            {[...Array(5)].map((_, i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </div>
        ) : applications.length === 0 ? (
          <div className="px-4 pb-6 text-center">
            <p className="text-sm text-muted-foreground py-8">
              No applications yet. Start by analyzing a job posting.
            </p>
          </div>
        ) : (
          <div className="divide-y">
            {applications.slice(0, 5).map((app) => (
              <button
                key={app.id}
                onClick={() => onSelect(app)}
                className="w-full flex items-center justify-between px-4 py-3 hover:bg-muted/50 transition-colors text-left"
              >
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium truncate">{app.company}</p>
                  <p className="text-xs text-muted-foreground truncate">{app.roleTitle}</p>
                </div>
                <div className="flex items-center gap-2 ml-2 shrink-0">
                  {app.matchScore > 0 && (
                    <Badge variant="secondary" className="text-xs">
                      {Math.round(app.matchScore)}%
                    </Badge>
                  )}
                  <Badge className={`text-xs ${STATUS_COLORS[app.status]}`}>
                    {app.status}
                  </Badge>
                </div>
              </button>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

interface FunnelChartProps {
  analytics: AnalyticsData | null;
  loading: boolean;
}

export function FunnelChart({ analytics, loading }: FunnelChartProps) {
  if (loading || !analytics) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold">Application Funnel</CardTitle>
        </CardHeader>
        <CardContent>
          <Skeleton className="h-48 w-full" />
        </CardContent>
      </Card>
    );
  }

  const funnelEntries = Object.entries(analytics.funnel) as [string, number][];
  const maxCount = Math.max(...funnelEntries.map(([, c]) => c), 1);

  const statusLabels: Record<string, string> = {
    SCRAPED: "Scraped",
    TAILORED: "Tailored",
    SUBMITTED: "Submitted",
    INTERVIEWING: "Interviewing",
    OFFER: "Offer",
    REJECTED: "Rejected",
    GHOSTED: "Ghosted",
  };

  const statusColors: Record<string, string> = {
    SCRAPED: "bg-gray-300 dark:bg-gray-600",
    TAILORED: "bg-purple-400 dark:bg-purple-500",
    SUBMITTED: "bg-blue-400 dark:bg-blue-500",
    INTERVIEWING: "bg-amber-400 dark:bg-amber-500",
    OFFER: "bg-emerald-400 dark:bg-emerald-500",
    REJECTED: "bg-red-400 dark:bg-red-500",
    GHOSTED: "bg-zinc-300 dark:bg-zinc-500",
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base font-semibold">Application Funnel</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {funnelEntries.map(([status, count]) => (
            <div key={status} className="flex items-center gap-3">
              <span className="text-xs font-medium w-24 text-right text-muted-foreground shrink-0">
                {statusLabels[status] || status}
              </span>
              <div className="flex-1 h-7 bg-muted rounded-md overflow-hidden">
                <div
                  className={`h-full rounded-md transition-all duration-500 ${statusColors[status] || "bg-gray-400"}`}
                  style={{
                    width: `${maxCount > 0 ? (count / maxCount) * 100 : 0}%`,
                    minWidth: count > 0 ? "2rem" : "0",
                  }}
                />
              </div>
              <span className="text-sm font-semibold w-8 text-right">{count}</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

interface QuickActionsProps {
  onNewApplication: () => void;
  onCreatePersona: () => void;
}

export function QuickActions({ onNewApplication, onCreatePersona }: QuickActionsProps) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base font-semibold">Quick Actions</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <Button
          className="w-full justify-start gap-2"
          onClick={onNewApplication}
        >
          <Plus className="h-4 w-4" />
          New Application
          <ArrowRight className="h-4 w-4 ml-auto" />
        </Button>
        <Button
          variant="outline"
          className="w-full justify-start gap-2"
          onClick={onCreatePersona}
        >
          <Plus className="h-4 w-4" />
          Create Persona
        </Button>
      </CardContent>
    </Card>
  );
}
