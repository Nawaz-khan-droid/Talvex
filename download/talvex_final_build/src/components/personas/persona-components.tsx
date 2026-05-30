"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Label } from "@/components/ui/label";
import { Plus, Pencil, Trash2, Users, X } from "lucide-react";
import type { JobPersona } from "@/lib/types";
import { toast } from "sonner";

interface PersonaListProps {
  personas: JobPersona[];
  loading: boolean;
  onRefresh: () => void;
}

export function PersonaList({ personas, loading, onRefresh }: PersonaListProps) {
  const [showForm, setShowForm] = useState(false);
  const [editingPersona, setEditingPersona] = useState<JobPersona | null>(null);
  const [deletingPersona, setDeletingPersona] = useState<JobPersona | null>(null);

  const handleCreate = () => {
    setEditingPersona(null);
    setShowForm(true);
  };

  const handleEdit = (persona: JobPersona) => {
    setEditingPersona(persona);
    setShowForm(true);
  };

  const handleDelete = async () => {
    if (!deletingPersona) return;
    try {
      const res = await fetch(`/api/personas/${deletingPersona.id}`, { method: "DELETE" });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || "Failed to delete");
      }
      toast.success(`Persona "${deletingPersona.name}" deleted`);
      onRefresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to delete");
    } finally {
      setDeletingPersona(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Users className="h-5 w-5 text-primary" />
          <h2 className="text-lg font-semibold">Personas</h2>
          <Badge variant="secondary" className="text-xs">
            {personas.length}
          </Badge>
        </div>
        <Button size="sm" onClick={handleCreate}>
          <Plus className="h-4 w-4 mr-1" />
          New Persona
        </Button>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(3)].map((_, i) => (
            <Skeleton key={i} className="h-40" />
          ))}
        </div>
      ) : personas.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <Users className="h-10 w-10 mx-auto text-muted-foreground/40 mb-3" />
            <p className="text-sm text-muted-foreground mb-4">
              No personas yet. Create your first job persona to get started.
            </p>
            <Button size="sm" onClick={handleCreate}>
              <Plus className="h-4 w-4 mr-1" />
              Create Persona
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {personas.map((persona) => {
            let skills: string[] = [];
            try {
              skills = JSON.parse(persona.skillsJson);
            } catch {
              skills = persona.skillsJson.split(",").map((s) => s.trim()).filter(Boolean);
            }

            return (
              <Card key={persona.id} className="group">
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between">
                    <CardTitle className="text-base">{persona.name}</CardTitle>
                    <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        onClick={() => handleEdit(persona)}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-destructive hover:text-destructive"
                        onClick={() => setDeletingPersona(persona)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <span>{skills.length} skills</span>
                    <span>·</span>
                    <span>{persona._count?.applications || 0} applications</span>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {skills.slice(0, 5).map((skill) => (
                      <Badge key={skill} variant="secondary" className="text-[10px] px-1.5 py-0">
                        {skill}
                      </Badge>
                    ))}
                    {skills.length > 5 && (
                      <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                        +{skills.length - 5}
                      </Badge>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <Dialog open={showForm} onOpenChange={setShowForm}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              {editingPersona ? "Edit Persona" : "Create Persona"}
            </DialogTitle>
            <DialogDescription>
              {editingPersona
                ? "Update your job persona details."
                : "Define a job persona with relevant skills."}
            </DialogDescription>
          </DialogHeader>
          <PersonaForm
            persona={editingPersona}
            onClose={() => setShowForm(false)}
            onRefresh={onRefresh}
          />
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!deletingPersona} onOpenChange={(open) => !open && setDeletingPersona(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Persona</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete &quot;{deletingPersona?.name}&quot;?
              {deletingPersona && (deletingPersona._count?.applications || 0) > 0 && (
                <span className="block mt-2 font-medium text-destructive">
                  Warning: This persona has {deletingPersona._count?.applications} linked
                  applications and cannot be deleted.
                </span>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function PersonaForm({
  persona,
  onClose,
  onRefresh,
}: {
  persona: JobPersona | null;
  onClose: () => void;
  onRefresh: () => void;
}) {
  const [name, setName] = useState(persona?.name || "");
  const [skillsText, setSkillsText] = useState(() => {
    if (!persona) return "";
    try {
      const arr = JSON.parse(persona.skillsJson);
      return arr.join(", ");
    } catch {
      return persona.skillsJson;
    }
  });
  const [masterBullets, setMasterBullets] = useState(persona?.masterBullets || "");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !skillsText.trim()) {
      toast.error("Name and skills are required");
      return;
    }

    const skillsArr = skillsText
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);

    setSubmitting(true);
    try {
      const url = persona ? `/api/personas/${persona.id}` : "/api/personas";
      const res = await fetch(url, {
        method: persona ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          skillsJson: JSON.stringify(skillsArr),
          masterBullets: masterBullets.trim(),
        }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || "Failed to save persona");
      }

      toast.success(persona ? "Persona updated" : "Persona created");
      onRefresh();
      onClose();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to save persona");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="persona-name">Name</Label>
        <Input
          id="persona-name"
          placeholder="e.g., Frontend Engineer"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="persona-skills">Skills (comma-separated)</Label>
        <Input
          id="persona-skills"
          placeholder="React, TypeScript, Node.js, GraphQL"
          value={skillsText}
          onChange={(e) => setSkillsText(e.target.value)}
          required
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="persona-bullets">Master Bullets</Label>
        <Textarea
          id="persona-bullets"
          placeholder="Key achievements and bullet points for resumes..."
          value={masterBullets}
          onChange={(e) => setMasterBullets(e.target.value)}
          rows={4}
        />
      </div>

      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" disabled={submitting}>
          {submitting ? "Saving..." : persona ? "Update" : "Create"}
        </Button>
      </DialogFooter>
    </form>
  );
}
