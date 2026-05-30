"use client";

import { useSyncExternalStore, useState, useCallback, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  type UserProfile,
  DEFAULT_PROFILE,
  STORAGE_KEYS,
} from "@/hooks/use-onboarding";
import {
  EXPERIENCE_LABELS,
  INDUSTRY_LABELS,
  TEMPLATE_INFO,
  WORK_MODE_LABELS,
  EMPLOYMENT_LABELS,
  type ExperienceLevel,
  type Industry,
  type ResumeTemplate,
  type WorkMode,
  type EmploymentType,
} from "@/lib/constants";
import {
  User,
  Briefcase,
  Target,
  GraduationCap,
  Building2,
  MapPin,
  FileText,
  Monitor,
  Clock,
  DollarSign,
  Key,
  ExternalLink,
  Save,
  RotateCcw,
  CheckCircle2,
  Search,
  Shield,
  Eye,
  EyeOff,
} from "lucide-react";
import { toast } from "sonner";

// ── Storage helpers ─────────────────────────────────────────────

function subscribeToStorage(callback: () => void) {
  window.addEventListener("storage", callback);
  return () => window.removeEventListener("storage", callback);
}

function readProfileJson(): string {
  return (
    localStorage.getItem(STORAGE_KEYS.profile) ??
    JSON.stringify(DEFAULT_PROFILE)
  );
}

function getServerProfile(): string {
  return JSON.stringify(DEFAULT_PROFILE);
}

function persistProfile(profile: UserProfile): void {
  try {
    localStorage.setItem(STORAGE_KEYS.profile, JSON.stringify(profile));
  } catch {
    // storage unavailable
  }
}

function dispatchProfileChange(): void {
  window.dispatchEvent(
    new StorageEvent("storage", { key: STORAGE_KEYS.profile })
  );
}

// ── Component ───────────────────────────────────────────────────

export function SettingsPanel() {
  const storedJson = useSyncExternalStore(
    subscribeToStorage,
    readProfileJson,
    getServerProfile
  );
  const storedProfile: UserProfile = storedJson
    ? JSON.parse(storedJson)
    : DEFAULT_PROFILE;

  // Track unsaved edits as a partial overlay
  const [edits, setEdits] = useState<Partial<UserProfile>>({});
  const [showOpenRouter, setShowOpenRouter] = useState(false);
  const [showTavily, setShowTavily] = useState(false);
  const [apiKeyEdits, setApiKeyEdits] = useState<{ openRouterKey: string; tavilyKey: string }>({
    openRouterKey: "",
    tavilyKey: "",
  });
  const [hasOpenRouterKey, setHasOpenRouterKey] = useState(false);
  const [hasTavilyKey, setHasTavilyKey] = useState(false);

  // Fetch API key status from backend on mount
  useEffect(() => {
    fetch("/api/settings")
      .then((r) => {
        if (r.status === 401) return null; // not logged in yet
        return r.json();
      })
      .then((data) => {
        if (data) {
          setHasOpenRouterKey(!!data.hasOpenRouterKey);
          setHasTavilyKey(!!data.hasTavilyKey);
        }
      })
      .catch(() => {});
  }, []);

  const handleSaveApiKeys = useCallback(async () => {
    const body: Record<string, string> = {};
    if (apiKeyEdits.openRouterKey) body.openRouterKey = apiKeyEdits.openRouterKey;
    if (apiKeyEdits.tavilyKey) body.tavilyKey = apiKeyEdits.tavilyKey;
    if (Object.keys(body).length === 0) return;
    try {
      const res = await fetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        const data = await res.json();
        setHasOpenRouterKey(!!data.hasOpenRouterKey);
        setHasTavilyKey(!!data.hasTavilyKey);
        setApiKeyEdits({ openRouterKey: "", tavilyKey: "" });
        toast.success("API keys saved", {
          description: "Keys are encrypted and stored server-side.",
        });
      }
    } catch {
      toast.error("Failed to save API keys");
    }
  }, [apiKeyEdits]);

  const handleClearApiKeys = useCallback(async () => {
    if (!window.confirm("This will delete all your API keys. Are you sure?")) return;
    try {
      await fetch("/api/settings", { method: "DELETE" });
      setHasOpenRouterKey(false);
      setHasTavilyKey(false);
      setApiKeyEdits({ openRouterKey: "", tavilyKey: "" });
      toast.warning("API keys cleared");
    } catch {
      toast.error("Failed to clear API keys");
    }
  }, []);

  const hasEdits = Object.keys(edits).length > 0;

  // The "working" profile merges stored + unsaved edits
  const profile: UserProfile = { ...storedProfile, ...edits };

  const updateProfile = useCallback((partial: Partial<UserProfile>) => {
    setEdits((prev) => ({ ...prev, ...partial }));
  }, []);

  const handleSave = useCallback(() => {
    // Merge edits into storage
    const raw = localStorage.getItem(STORAGE_KEYS.profile);
    const base: UserProfile = raw ? JSON.parse(raw) : DEFAULT_PROFILE;
    const merged: UserProfile = { ...base, ...edits };
    persistProfile(merged);
    setEdits({});
    dispatchProfileChange();
    toast.success("Settings saved", {
      description: "Your profile has been updated successfully.",
    });
  }, [edits]);

  const handleReset = useCallback(() => {
    setEdits({});
    toast.info("Settings reset", {
      description: "Reverted to last saved configuration.",
    });
  }, []);

  const handleClearAll = useCallback(() => {
    if (
      !window.confirm("This will delete all your profile data. Are you sure?")
    ) {
      return;
    }
    persistProfile(DEFAULT_PROFILE);
    setEdits({});
    dispatchProfileChange();
    toast.warning("Profile cleared", {
      description: "All profile data has been removed.",
    });
  }, []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold flex items-center gap-2">
            <Shield className="size-5" />
            Settings
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            Manage your profile, preferences, and API keys
          </p>
        </div>
        <div className="flex items-center gap-2">
          {hasEdits && (
            <Badge
              variant="outline"
              className="text-amber-600 border-amber-300 dark:border-amber-700 dark:text-amber-400"
            >
              Unsaved changes
            </Badge>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={handleReset}
            disabled={!hasEdits}
          >
            <RotateCcw className="size-3.5" />
            Discard
          </Button>
          <Button size="sm" onClick={handleSave} disabled={!hasEdits}>
            <Save className="size-3.5" />
            Save Changes
          </Button>
        </div>
      </div>

      <Tabs defaultValue="profile" className="space-y-4">
        <TabsList className="w-full sm:w-auto">
          <TabsTrigger value="profile" className="gap-1.5">
            <User className="size-3.5" />
            Profile
          </TabsTrigger>
          <TabsTrigger value="resume" className="gap-1.5">
            <FileText className="size-3.5" />
            Resume
          </TabsTrigger>
          <TabsTrigger value="jobs" className="gap-1.5">
            <Search className="size-3.5" />
            Job Preferences
          </TabsTrigger>
          <TabsTrigger value="api" className="gap-1.5">
            <Key className="size-3.5" />
            API Keys
          </TabsTrigger>
        </TabsList>

        {/* ─── Profile Tab ──────────────────────────────────────── */}
        <TabsContent value="profile">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Career Profile</CardTitle>
              <CardDescription>
                Your basic information for personalized recommendations
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-2 sm:col-span-2">
                  <Label
                    htmlFor="set-name"
                    className="flex items-center gap-1.5"
                  >
                    <User className="size-3.5" />
                    Full Name
                  </Label>
                  <Input
                    id="set-name"
                    placeholder="Your name"
                    value={profile.name}
                    onChange={(e) => updateProfile({ name: e.target.value })}
                  />
                </div>

                <div className="space-y-2">
                  <Label
                    htmlFor="set-current"
                    className="flex items-center gap-1.5"
                  >
                    <Briefcase className="size-3.5" />
                    Current Role
                  </Label>
                  <Input
                    id="set-current"
                    placeholder="Current title"
                    value={profile.currentRole}
                    onChange={(e) =>
                      updateProfile({ currentRole: e.target.value })
                    }
                  />
                </div>

                <div className="space-y-2">
                  <Label
                    htmlFor="set-target"
                    className="flex items-center gap-1.5"
                  >
                    <Target className="size-3.5" />
                    Target Role
                  </Label>
                  <Input
                    id="set-target"
                    placeholder="Desired role"
                    value={profile.targetRole}
                    onChange={(e) =>
                      updateProfile({ targetRole: e.target.value })
                    }
                  />
                </div>

                <div className="space-y-2">
                  <Label className="flex items-center gap-1.5">
                    <GraduationCap className="size-3.5" />
                    Experience Level
                  </Label>
                  <Select
                    value={profile.experienceLevel}
                    onValueChange={(v) =>
                      updateProfile({
                        experienceLevel: v as ExperienceLevel,
                      })
                    }
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="Select level" />
                    </SelectTrigger>
                    <SelectContent>
                      {(
                        Object.entries(EXPERIENCE_LABELS) as [
                          ExperienceLevel,
                          string,
                        ][]
                      ).map(([key, label]) => (
                        <SelectItem key={key} value={key}>
                          {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label className="flex items-center gap-1.5">
                    <Building2 className="size-3.5" />
                    Industry
                  </Label>
                  <Select
                    value={profile.industry}
                    onValueChange={(v) =>
                      updateProfile({ industry: v as Industry })
                    }
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="Select industry" />
                    </SelectTrigger>
                    <SelectContent>
                      {(
                        Object.entries(INDUSTRY_LABELS) as [Industry, string][]
                      ).map(([key, label]) => (
                        <SelectItem key={key} value={key}>
                          {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2 sm:col-span-2">
                  <Label
                    htmlFor="set-location"
                    className="flex items-center gap-1.5"
                  >
                    <MapPin className="size-3.5" />
                    Location
                  </Label>
                  <Input
                    id="set-location"
                    placeholder="City, State or Country"
                    value={profile.location}
                    onChange={(e) =>
                      updateProfile({ location: e.target.value })
                    }
                  />
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ─── Resume Tab ───────────────────────────────────────── */}
        <TabsContent value="resume">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Resume Preferences</CardTitle>
              <CardDescription>
                Configure your default resume template and formatting options
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="space-y-3">
                <Label>Preferred Template</Label>
                <RadioGroup
                  value={profile.preferredTemplate}
                  onValueChange={(v) =>
                    updateProfile({
                      preferredTemplate: v as ResumeTemplate,
                    })
                  }
                  className="grid gap-2"
                >
                  {(
                    Object.entries(TEMPLATE_INFO) as [
                      ResumeTemplate,
                      { label: string; description: string },
                    ][]
                  ).map(([key, { label, description }]) => (
                    <label
                      key={key}
                      className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                        profile.preferredTemplate === key
                          ? "border-primary bg-primary/5"
                          : "hover:bg-muted/50"
                      }`}
                    >
                      <RadioGroupItem value={key} className="mt-0.5" />
                      <div className="space-y-0.5">
                        <p className="text-sm font-medium">{label}</p>
                        <p className="text-xs text-muted-foreground">
                          {description}
                        </p>
                      </div>
                    </label>
                  ))}
                </RadioGroup>
              </div>

              <Separator />

              <div className="flex items-center justify-between p-3 rounded-lg border">
                <div className="space-y-0.5">
                  <Label className="text-sm">Include Photo</Label>
                  <p className="text-xs text-muted-foreground">
                    Most ATS systems don&apos;t require photos
                  </p>
                </div>
                <Switch
                  checked={profile.includePhoto}
                  onCheckedChange={(checked) =>
                    updateProfile({ includePhoto: checked })
                  }
                />
              </div>

              <div className="space-y-2">
                <Label>Page Preference</Label>
                <RadioGroup
                  value={String(profile.pagePreference)}
                  onValueChange={(v) =>
                    updateProfile({
                      pagePreference: Number(v) as 1 | 2,
                    })
                  }
                  className="flex gap-2"
                >
                  {([1, 2] as const).map((pages) => (
                    <label
                      key={pages}
                      className={`flex items-center gap-2 px-4 py-2 rounded-lg border cursor-pointer transition-colors ${
                        profile.pagePreference === pages
                          ? "border-primary bg-primary/5"
                          : "hover:bg-muted/50"
                      }`}
                    >
                      <RadioGroupItem value={String(pages)} />
                      <span className="text-sm font-medium">
                        {pages} page{pages > 1 ? "s" : ""}
                      </span>
                    </label>
                  ))}
                </RadioGroup>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ─── Job Preferences Tab ──────────────────────────────── */}
        <TabsContent value="jobs">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Job Search Preferences
              </CardTitle>
              <CardDescription>
                Fine-tune how TALVEX finds and recommends opportunities
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label
                  htmlFor="set-keywords"
                  className="flex items-center gap-1.5"
                >
                  <Search className="size-3.5" />
                  Search Keywords
                </Label>
                <Input
                  id="set-keywords"
                  placeholder="e.g. React, TypeScript, Fullstack"
                  value={profile.searchKeywords}
                  onChange={(e) =>
                    updateProfile({ searchKeywords: e.target.value })
                  }
                />
              </div>

              <div className="space-y-2">
                <Label
                  htmlFor="set-locations"
                  className="flex items-center gap-1.5"
                >
                  <MapPin className="size-3.5" />
                  Preferred Locations
                </Label>
                <Input
                  id="set-locations"
                  placeholder="e.g. San Francisco, New York, Remote"
                  value={profile.preferredLocations}
                  onChange={(e) =>
                    updateProfile({ preferredLocations: e.target.value })
                  }
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="flex items-center gap-1.5">
                    <Monitor className="size-3.5" />
                    Work Mode
                  </Label>
                  <Select
                    value={profile.workMode}
                    onValueChange={(v) =>
                      updateProfile({ workMode: v as WorkMode })
                    }
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="Select preference" />
                    </SelectTrigger>
                    <SelectContent>
                      {(
                        Object.entries(WORK_MODE_LABELS) as [WorkMode, string][]
                      ).map(([key, label]) => (
                        <SelectItem key={key} value={key}>
                          {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label className="flex items-center gap-1.5">
                    <Clock className="size-3.5" />
                    Employment Type
                  </Label>
                  <Select
                    value={profile.employmentType}
                    onValueChange={(v) =>
                      updateProfile({ employmentType: v as EmploymentType })
                    }
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="Select type" />
                    </SelectTrigger>
                    <SelectContent>
                      {(
                        Object.entries(EMPLOYMENT_LABELS) as [
                          EmploymentType,
                          string,
                        ][]
                      ).map(([key, label]) => (
                        <SelectItem key={key} value={key}>
                          {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-2">
                <Label className="flex items-center gap-1.5">
                  <DollarSign className="size-3.5" />
                  Target Salary Range
                </Label>
                <div className="flex items-center gap-2">
                  <Input
                    placeholder="Min"
                    type="number"
                    value={profile.salaryMin}
                    onChange={(e) =>
                      updateProfile({ salaryMin: e.target.value })
                    }
                    className="flex-1"
                  />
                  <span className="text-muted-foreground text-sm">—</span>
                  <Input
                    placeholder="Max"
                    type="number"
                    value={profile.salaryMax}
                    onChange={(e) =>
                      updateProfile({ salaryMax: e.target.value })
                    }
                    className="flex-1"
                  />
                  <span className="text-xs text-muted-foreground whitespace-nowrap">
                    USD / yr
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ─── API Keys Tab ─────────────────────────────────────── */}
        <TabsContent value="api">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">API Keys</CardTitle>
              <CardDescription>
                Connect external AI services. Keys are encrypted and stored
                server-side — never in your browser.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* OpenRouter */}
              <div className="space-y-2">
                <Label
                  htmlFor="set-openrouter"
                  className="flex items-center justify-between"
                >
                  <span className="flex items-center gap-1.5">
                    <Key className="size-3.5" />
                    OpenRouter API Key
                  </span>
                  <div className="flex items-center gap-2">
                    {showOpenRouter && hasOpenRouterKey && (
                      <Badge
                        variant="secondary"
                        className="text-emerald-600 gap-1"
                      >
                        <CheckCircle2 className="size-3" />
                        Connected
                      </Badge>
                    )}
                    <a
                      href="https://openrouter.ai/keys"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-primary hover:underline flex items-center gap-1"
                    >
                      Get key
                      <ExternalLink className="size-3" />
                    </a>
                  </div>
                </Label>
                <div className="relative">
                  <Input
                    id="set-openrouter"
                    type={showOpenRouter ? "text" : "password"}
                    placeholder="sk-or-..."
                    value={apiKeyEdits.openRouterKey}
                    onChange={(e) =>
                      setApiKeyEdits((prev) => ({
                        ...prev,
                        openRouterKey: e.target.value,
                      }))
                    }
                    className="pr-10"
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="absolute right-1 top-1/2 -translate-y-1/2 size-7"
                    onClick={() => setShowOpenRouter(!showOpenRouter)}
                  >
                    {showOpenRouter ? (
                      <EyeOff className="size-3.5" />
                    ) : (
                      <Eye className="size-3.5" />
                    )}
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  Powers advanced resume customization and JD analysis
                </p>
              </div>

              <Separator />

              {/* Tavily */}
              <div className="space-y-2">
                <Label
                  htmlFor="set-tavily"
                  className="flex items-center justify-between"
                >
                  <span className="flex items-center gap-1.5">
                    <Key className="size-3.5" />
                    Tavily API Key
                  </span>
                  <div className="flex items-center gap-2">
                    {showTavily && hasTavilyKey && (
                      <Badge
                        variant="secondary"
                        className="text-emerald-600 gap-1"
                      >
                        <CheckCircle2 className="size-3" />
                        Connected
                      </Badge>
                    )}
                    <a
                      href="https://tavily.com/"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-primary hover:underline flex items-center gap-1"
                    >
                      Get key
                      <ExternalLink className="size-3" />
                    </a>
                  </div>
                </Label>
                <div className="relative">
                  <Input
                    id="set-tavily"
                    type={showTavily ? "text" : "password"}
                    placeholder="tvly-..."
                    value={apiKeyEdits.tavilyKey}
                    onChange={(e) =>
                      setApiKeyEdits((prev) => ({
                        ...prev,
                        tavilyKey: e.target.value,
                      }))
                    }
                    className="pr-10"
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="absolute right-1 top-1/2 -translate-y-1/2 size-7"
                    onClick={() => setShowTavily(!showTavily)}
                  >
                    {showTavily ? (
                      <EyeOff className="size-3.5" />
                    ) : (
                      <Eye className="size-3.5" />
                    )}
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  Enables real-time job search and web research features
                </p>
              </div>

              <Separator />

              <div className="flex gap-2">
                <Button
                  size="sm"
                  onClick={handleSaveApiKeys}
                  disabled={!apiKeyEdits.openRouterKey && !apiKeyEdits.tavilyKey}
                >
                  <Save className="size-3.5" />
                  Save Keys
                </Button>
                {hasOpenRouterKey || hasTavilyKey ? (
                  <Button size="sm" variant="destructive" onClick={handleClearApiKeys}>
                    Clear All Keys
                  </Button>
                ) : null}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Danger Zone */}
      <Card className="border-destructive/30">
        <CardHeader>
          <CardTitle className="text-base text-destructive">
            Danger Zone
          </CardTitle>
          <CardDescription>
            Irreversible actions that affect your stored data
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button variant="destructive" size="sm" onClick={handleClearAll}>
            Clear All Profile Data
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

export default SettingsPanel;
