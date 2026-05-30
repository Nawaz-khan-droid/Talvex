"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  Shield,
  ShieldAlert,
  ShieldCheck,
  Mail,
  AlertTriangle,
  Eye,
  Globe,
} from "lucide-react";

interface CanaryRecord {
  id: string;
  appId: string;
  canaryEmail: string;
  trackingSlug: string | null;
  leakFlagged: boolean;
  leakDetails: string | null;
  createdAt: string;
  application: {
    id: string;
    company: string;
    roleTitle: string;
    persona: { id: string; name: string } | null;
  };
}

interface PrivacySectionProps {
  canaries: CanaryRecord[];
  loading: boolean;
}

export function PrivacySection({ canaries, loading }: PrivacySectionProps) {
  const leakedCount = canaries.filter((c) => c.leakFlagged).length;
  const monitoredCount = canaries.filter((c) => !c.leakFlagged).length;
  const companies = Array.from(
    new Map(
      canaries.map((c) => [
        c.application.company,
        {
          company: c.application.company,
          leaked: canaries
            .filter((cc) => cc.application.company === c.application.company)
            .some((cc) => cc.leakFlagged),
        },
      ])
    ).values()
  );

  const safeCompanies = companies.filter((c) => !c.leaked).length;
  const leakedCompanies = companies.filter((c) => c.leaked).length;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="p-2 rounded-lg bg-emerald-100 dark:bg-emerald-900/30">
              <ShieldCheck className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
            </div>
            <div>
              <p className="text-2xl font-bold">{monitoredCount}</p>
              <p className="text-xs text-muted-foreground">Monitored</p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="p-2 rounded-lg bg-destructive/10">
              <ShieldAlert className="h-5 w-5 text-destructive" />
            </div>
            <div>
              <p className="text-2xl font-bold text-destructive">{leakedCount}</p>
              <p className="text-xs text-muted-foreground">Leaks Detected</p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/10">
              <Globe className="h-5 w-5 text-primary" />
            </div>
            <div>
              <p className="text-2xl font-bold">{companies.length}</p>
              <p className="text-xs text-muted-foreground">Companies Tracked</p>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold">Company Trust Scores</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Skeleton className="h-32 w-full" />
          ) : companies.length === 0 ? (
            <div className="text-center py-8">
              <Shield className="h-8 w-8 mx-auto text-muted-foreground/30 mb-2" />
              <p className="text-sm text-muted-foreground">
                No canary emails deployed yet. Create applications to start monitoring.
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {companies
                .sort((a, b) => (a.leaked === b.leaked ? 0 : a.leaked ? 1 : -1))
                .map(({ company, leaked }) => (
                  <div
                    key={company}
                    className="flex items-center justify-between py-2 px-3 rounded-md hover:bg-muted/50"
                  >
                    <div className="flex items-center gap-2">
                      {leaked ? (
                        <ShieldAlert className="h-4 w-4 text-destructive" />
                      ) : (
                        <ShieldCheck className="h-4 w-4 text-emerald-500" />
                      )}
                      <span className="text-sm font-medium">{company}</span>
                    </div>
                    <Badge
                      className={
                        leaked
                          ? "bg-destructive/10 text-destructive"
                          : "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300"
                      }
                    >
                      {leaked ? "LEAKED" : "CLEAN"}
                    </Badge>
                  </div>
                ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base font-semibold flex items-center gap-2">
              <Mail className="h-4 w-4 text-primary" />
              Canary Emails
            </CardTitle>
            <Badge variant="secondary" className="text-xs">{canaries.length}</Badge>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-3">
              {[...Array(3)].map((_, i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          ) : canaries.length === 0 ? (
            <div className="text-center py-8">
              <Mail className="h-8 w-8 mx-auto text-muted-foreground/30 mb-2" />
              <p className="text-sm text-muted-foreground">
                No canary emails deployed yet.
              </p>
            </div>
          ) : (
            <div className="divide-y">
              {canaries.map((canary) => (
                <div
                  key={canary.id}
                  className="flex items-center justify-between py-3"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <Mail className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                      <p className="text-sm font-mono truncate">{canary.canaryEmail}</p>
                    </div>
                    <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                      <span>{canary.application.company}</span>
                      <span>·</span>
                      <span>{new Date(canary.createdAt).toLocaleDateString()}</span>
                    </div>
                  </div>
                  <Badge
                    className={
                      canary.leakFlagged
                        ? "bg-destructive/10 text-destructive shrink-0 ml-2"
                        : "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300 shrink-0 ml-2"
                    }
                  >
                    {canary.leakFlagged ? "LEAKED" : "CLEAN"}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {leakedCount > 0 && (
        <Card className="border-destructive/30">
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-semibold flex items-center gap-2 text-destructive">
              <AlertTriangle className="h-4 w-4" />
              Leak Alerts
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {canaries
              .filter((c) => c.leakFlagged)
              .map((canary) => (
                <div
                  key={canary.id}
                  className="p-3 bg-destructive/5 rounded-lg border border-destructive/20"
                >
                  <div className="flex items-center gap-2 mb-1">
                    <ShieldAlert className="h-4 w-4 text-destructive" />
                    <span className="text-sm font-semibold">{canary.application.company}</span>
                    <Badge variant="secondary" className="text-xs">
                      {canary.application.roleTitle}
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Canary <span className="font-mono">{canary.canaryEmail}</span> received
                    unexpected communication.
                  </p>
                  {canary.leakDetails && (
                    <p className="text-xs mt-1 text-destructive/80">
                      {canary.leakDetails}
                    </p>
                  )}
                </div>
              ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
