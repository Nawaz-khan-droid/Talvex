"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { ArrowRight, ArrowLeft, ChevronRight, Trash2, Clock, Shield } from "lucide-react";
import type { Application } from "@/lib/types";
import { STATUS_COLORS, STATUS_ORDER, PRIVACY_COLORS } from "@/lib/types";
import { getNextTransitions, getStatusLabel } from "@/lib/fsm";
import { toast } from "sonner";

interface KanbanBoardProps {
  applications: Application[];
  loading: boolean;
  onRefresh: () => void;
  onSelectApplication: (app: Application) => void;
  onNavigate: (tab: string) => void;
}

export function KanbanBoard({ applications, loading, onSelectApplication, onNavigate }: KanbanBoardProps) {
  const [filterStatus, setFilterStatus] = useState<string>("ALL");
  const [filterPersona, setFilterPersona] = useState<string>("ALL");
  const [detailApp, setDetailApp] = useState<Application | null>(null);

  const personaOptions = Array.from(
    new Set(applications.map((a) => a.persona?.name).filter(Boolean) as string[])
  );

  const filtered = applications.filter((app) => {
    if (filterStatus !== "ALL" && app.status !== filterStatus) return false;
    if (filterPersona !== "ALL" && app.persona?.name !== filterPersona) return false;
    return true;
  });

  const grouped = STATUS_ORDER.map((status) => ({
    status,
    label: getStatusLabel(status),
    apps: filtered.filter((a) => a.status === status),
  }));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <Select value={filterStatus} onValueChange={setFilterStatus}>
          <SelectTrigger className="w-40 h-9 text-sm">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL">All Statuses</SelectItem>
            {STATUS_ORDER.map((s) => (
              <SelectItem key={s} value={s}>
                {getStatusLabel(s)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {personaOptions.length > 0 && (
          <Select value={filterPersona} onValueChange={setFilterPersona}>
            <SelectTrigger className="w-40 h-9 text-sm">
              <SelectValue placeholder="Persona" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL">All Personas</SelectItem>
              {personaOptions.map((p) => (
                <SelectItem key={p} value={p}>
                  {p}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7 gap-3">
          {[...Array(7)].map((_, i) => (
            <Skeleton key={i} className="h-64" />
          ))}
        </div>
      ) : (
        <div className="flex gap-3 overflow-x-auto pb-4 snap-x">
          {grouped.map(({ status, label, apps }) => (
            <div
              key={status}
              className="min-w-[260px] w-[260px] flex-shrink-0 snap-start"
            >
              <div className="flex items-center gap-2 mb-3 px-1">
                <Badge className={`${STATUS_COLORS[status]} text-xs font-semibold`}>
                  {label}
                </Badge>
                <span className="text-xs text-muted-foreground font-medium">{apps.length}</span>
              </div>

              <ScrollArea className="max-h-[calc(100vh-220px)]">
                <div className="space-y-2 pr-2">
                  {apps.length === 0 && (
                    <div className="text-xs text-muted-foreground text-center py-8 border border-dashed rounded-lg">
                      No applications
                    </div>
                  )}
                  {apps.map((app) => (
                    <ApplicationCard
                      key={app.id}
                      application={app}
                      onClick={() => setDetailApp(app)}
                    />
                  ))}
                </div>
              </ScrollArea>
            </div>
          ))}
        </div>
      )}

      {detailApp && (
        <ApplicationDetail
          application={detailApp}
          onClose={() => setDetailApp(null)}
          onRefresh={() => setDetailApp(null)}
          onNavigate={onNavigate}
        />
      )}
    </div>
  );
}

function ApplicationCard({
  application,
  onClick,
}: {
  application: Application;
  onClick: () => void;
}) {
  return (
    <Card
      className="cursor-pointer hover:shadow-md transition-all hover:border-primary/30"
      onClick={onClick}
    >
      <CardContent className="p-3 space-y-2">
        <div className="flex items-start justify-between">
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold truncate">{application.company}</p>
            <p className="text-xs text-muted-foreground truncate">{application.roleTitle}</p>
          </div>
          {application.matchScore > 0 && (
            <Badge
              variant="secondary"
              className="text-xs shrink-0 ml-2"
            >
              {Math.round(application.matchScore)}%
            </Badge>
          )}
        </div>

        <div className="flex items-center gap-1.5 flex-wrap">
          {application.persona && (
            <Badge variant="outline" className="text-[10px] px-1.5 py-0">
              {application.persona.name}
            </Badge>
          )}
          <Badge className={`text-[10px] px-1.5 py-0 ${PRIVACY_COLORS[application.privacyStatus as keyof typeof PRIVACY_COLORS] || ""}`}>
            <Shield className="h-2.5 w-2.5 mr-0.5" />
            {application.privacyStatus}
          </Badge>
        </div>

        {application.appliedDate && (
          <div className="flex items-center gap-1 text-[10px] text-muted-foreground">
            <Clock className="h-3 w-3" />
            {new Date(application.appliedDate).toLocaleDateString()}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ApplicationDetail({
  application,
  onClose,
  onRefresh,
  onNavigate,
}: {
  application: Application;
  onClose: () => void;
  onRefresh: () => void;
  onNavigate: (tab: string) => void;
}) {
  const [advancing, setAdvancing] = useState<string | null>(null);

  const transitions = getNextTransitions(application.status);
  const statusHistory = [application.status];

  const handleAdvance = async (toStatus: string) => {
    setAdvancing(toStatus);
    try {
      const res = await fetch(`/api/applications/${application.id}/advance`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ to: toStatus }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || "Failed to advance");
      }
      toast.success(`Moved to ${toStatus}`);
      onRefresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to advance");
    } finally {
      setAdvancing(null);
    }
  };

  const handleDelete = async () => {
    if (!confirm("Delete this application? This cannot be undone.")) return;
    try {
      const res = await fetch(`/api/applications/${application.id}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error("Failed to delete");
      toast.success("Application deleted");
      onRefresh();
    } catch {
      toast.error("Failed to delete application");
    }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {application.company} — {application.roleTitle}
          </DialogTitle>
          <DialogDescription>
            Application details and status management
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <Badge className={STATUS_COLORS[application.status]}>
              {application.status}
            </Badge>
            {application.matchScore > 0 && (
              <Badge variant="secondary">
                Match: {Math.round(application.matchScore)}%
              </Badge>
            )}
            {application.atsScore > 0 && (
              <Badge variant="secondary">
                ATS: {Math.round(application.atsScore)}%
              </Badge>
            )}
            <Badge className={PRIVACY_COLORS[application.privacyStatus as keyof typeof PRIVACY_COLORS] || ""}>
              <Shield className="h-3 w-3 mr-1" />
              {application.privacyStatus}
            </Badge>
          </div>

          {application.persona && (
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Persona
              </p>
              <p className="text-sm mt-0.5">{application.persona.name}</p>
            </div>
          )}

          {application.appliedDate && (
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Applied Date
              </p>
              <p className="text-sm mt-0.5">
                {new Date(application.appliedDate).toLocaleDateString()}
              </p>
            </div>
          )}

          {application.jobDescription && (
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Job Description
              </p>
              <div className="mt-1 p-3 bg-muted rounded-md text-xs max-h-40 overflow-y-auto whitespace-pre-wrap">
                {application.jobDescription}
              </div>
            </div>
          )}

          <Separator />

          <div>
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
              Transition
            </p>
            <div className="flex flex-wrap gap-2">
              {transitions.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  This application is in a terminal state.
                </p>
              ) : (
                transitions.map((t) => (
                  <Button
                    key={t.to}
                    size="sm"
                    variant="outline"
                    className="text-xs"
                    disabled={advancing === t.to}
                    onClick={() => handleAdvance(t.to)}
                  >
                    {advancing === t.to ? "..." : `${t.label} `}
                    <ChevronRight className="h-3 w-3 ml-1" />
                  </Button>
                ))
              )}
            </div>
          </div>

          <Separator />

          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              className="text-xs"
              onClick={() => onNavigate("resume")}
            >
              View Resume
            </Button>
            <Button
              variant="destructive"
              size="sm"
              className="text-xs ml-auto"
              onClick={handleDelete}
            >
              <Trash2 className="h-3 w-3 mr-1" />
              Delete
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
