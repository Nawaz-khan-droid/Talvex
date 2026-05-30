"use client";

import { useState, useCallback, useRef, type DragEvent } from "react";
import Image from "next/image";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  useOnboarding,
  type UserProfile,
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
  ArrowRight,
  ArrowLeft,
  Upload,
  X,
  FileText,
  ExternalLink,
  Sparkles,
  Target,
  Search,
  Rocket,
  CheckCircle2,
  Briefcase,
  MapPin,
  DollarSign,
  Monitor,
  Clock,
  User,
  GraduationCap,
  Building2,
} from "lucide-react";

const STEP_ICONS = [Sparkles, User, Search, Rocket];
const STEP_TITLES = ["Welcome", "Your Profile", "Job Preferences", "All Set!"];

// ─── Progress Header ────────────────────────────────────────────
function StepProgress({ currentStep, totalSteps }: { currentStep: number; totalSteps: number }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>Step {currentStep + 1} of {totalSteps}</span>
        <span>{Math.round(((currentStep + 1) / totalSteps) * 100)}% complete</span>
      </div>
      <Progress value={((currentStep + 1) / totalSteps) * 100} className="h-1.5" />
      <div className="flex gap-1">
        {Array.from({ length: totalSteps }).map((_, i) => (
          <div
            key={i}
            className={`h-1 flex-1 rounded-full transition-colors duration-300 ${
              i <= currentStep ? "bg-primary" : "bg-primary/20"
            }`}
          />
        ))}
      </div>
    </div>
  );
}

// ─── Step 0: Welcome ───────────────────────────────────────────
function WelcomeStep({ onNext }: { onNext: () => void }) {
  return (
    <div className="flex flex-col items-center text-center space-y-6 py-4">
      <div className="relative">
        <div className="absolute inset-0 bg-primary/20 rounded-full blur-2xl scale-110" />
        <Image
          src="/talvex-logo.png"
          alt="TALVEX"
          width={80}
          height={80}
          className="relative rounded-2xl"
          priority
        />
      </div>
      <div className="space-y-2">
        <h2 className="text-2xl font-bold tracking-tight">Welcome to TALVEX</h2>
        <p className="text-lg text-muted-foreground font-medium">
          Your Personal Career Command Center
        </p>
      </div>
      <p className="text-sm text-muted-foreground max-w-sm leading-relaxed">
        Track applications, tailor resumes, detect data leaks, and manage your
        entire job search pipeline with precision — all in one place.
      </p>
      <div className="grid grid-cols-2 gap-3 w-full max-w-sm">
        {[
          { icon: Target, label: "Track & Pipeline", desc: "Monitor every application" },
          { icon: FileText, label: "Smart Resumes", desc: "ATS-optimized & tailored" },
          { icon: Monitor, label: "Privacy Monitor", desc: "Detect data leaks early" },
          { icon: Search, label: "AI-Powered Search", desc: "Find your dream role" },
        ].map(({ icon: Icon, label, desc }) => (
          <div key={label} className="flex items-start gap-2.5 p-3 rounded-xl border bg-card text-left">
            <Icon className="size-4 mt-0.5 text-primary shrink-0" />
            <div>
              <p className="text-xs font-medium">{label}</p>
              <p className="text-[11px] text-muted-foreground">{desc}</p>
            </div>
          </div>
        ))}
      </div>
      <Button onClick={onNext} size="lg" className="w-full max-w-sm gap-2">
        <Sparkles className="size-4" />
        Get Started
      </Button>
    </div>
  );
}

// ─── Step 1: Profile (Career + Resume merged) ──────────────────
function ProfileStep({ profile, updateProfile }: { profile: UserProfile; updateProfile: (p: Partial<UserProfile>) => void }) {
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const canProceed = profile.name.trim().length > 0 && profile.targetRole.trim().length > 0;

  const handleDragOver = useCallback((e: DragEvent) => { e.preventDefault(); setDragOver(true); }, []);
  const handleDragLeave = useCallback((e: DragEvent) => { e.preventDefault(); setDragOver(false); }, []);
  const handleDrop = useCallback((e: DragEvent) => {
    e.preventDefault(); setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file && /\.(pdf|docx|txt)$/i.test(file.name)) {
      updateProfile({ resumeUploaded: true, resumeFileName: file.name });
    }
  }, [updateProfile]);
  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) updateProfile({ resumeUploaded: true, resumeFileName: file.name });
  }, [updateProfile]);
  const removeFile = useCallback(() => {
    updateProfile({ resumeUploaded: false, resumeFileName: "" });
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, [updateProfile]);

  return (
    <div className="space-y-5">
      <div className="space-y-1.5">
        <h3 className="text-lg font-semibold">Tell us about yourself</h3>
        <p className="text-sm text-muted-foreground">
          Name and target role are required. Everything else can be updated later in Settings.
        </p>
      </div>

      {/* Name + Role row */}
      <div className="grid gap-4">
        <div className="space-y-2">
          <Label htmlFor="onb-name" className="flex items-center gap-1.5">
            <User className="size-3.5" />
            Full Name <span className="text-destructive">*</span>
          </Label>
          <Input id="onb-name" placeholder="e.g. Alex Johnson" value={profile.name}
            onChange={(e) => updateProfile({ name: e.target.value })} />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="onb-current-role" className="flex items-center gap-1.5">
              <Briefcase className="size-3.5" /> Current Role
            </Label>
            <Input id="onb-current-role" placeholder="e.g. Software Engineer" value={profile.currentRole}
              onChange={(e) => updateProfile({ currentRole: e.target.value })} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="onb-target-role" className="flex items-center gap-1.5">
              <Target className="size-3.5" /> Target Role <span className="text-destructive">*</span>
            </Label>
            <Input id="onb-target-role" placeholder="e.g. Senior Frontend Dev" value={profile.targetRole}
              onChange={(e) => updateProfile({ targetRole: e.target.value })} />
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="space-y-2">
            <Label className="flex items-center gap-1.5"><GraduationCap className="size-3.5" /> Experience</Label>
            <Select value={profile.experienceLevel} onValueChange={(v) => updateProfile({ experienceLevel: v })}>
              <SelectTrigger className="w-full"><SelectValue placeholder="Select" /></SelectTrigger>
              <SelectContent>
                {(Object.entries(EXPERIENCE_LABELS) as [ExperienceLevel, string][]).map(([k, l]) => (
                  <SelectItem key={k} value={k}>{l}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label className="flex items-center gap-1.5"><Building2 className="size-3.5" /> Industry</Label>
            <Select value={profile.industry} onValueChange={(v) => updateProfile({ industry: v })}>
              <SelectTrigger className="w-full"><SelectValue placeholder="Select" /></SelectTrigger>
              <SelectContent>
                {(Object.entries(INDUSTRY_LABELS) as [Industry, string][]).map(([k, l]) => (
                  <SelectItem key={k} value={k}>{l}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label className="flex items-center gap-1.5"><MapPin className="size-3.5" /> Location</Label>
            <Input id="onb-location" placeholder="City, State" value={profile.location}
              onChange={(e) => updateProfile({ location: e.target.value })} />
          </div>
        </div>
      </div>

      <Separator />

      {/* Resume upload + template in one row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Upload */}
        <div className="space-y-2">
          <Label>Resume</Label>
          {profile.resumeUploaded ? (
            <div className="flex items-center gap-3 p-3 rounded-xl border bg-card">
              <div className="flex items-center justify-center size-9 rounded-lg bg-primary/10">
                <FileText className="size-4 text-primary" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{profile.resumeFileName}</p>
              </div>
              <Button variant="ghost" size="icon" className="size-7" onClick={removeFile}><X className="size-3.5" /></Button>
            </div>
          ) : (
            <div
              onDragOver={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`flex flex-col items-center justify-center gap-1.5 p-4 rounded-xl border-2 border-dashed cursor-pointer transition-colors ${
                dragOver ? "border-primary bg-primary/5" : "border-muted-foreground/25 hover:border-primary/50 hover:bg-muted/50"
              }`}
            >
              <Upload className="size-4 text-muted-foreground" />
              <p className="text-xs text-muted-foreground">Drop or click (PDF/DOCX/TXT)</p>
            </div>
          )}
          <input ref={fileInputRef} type="file" accept=".pdf,.docx,.txt" className="hidden" onChange={handleFileSelect} />
        </div>

        {/* Template */}
        <div className="space-y-2">
          <Label>Template</Label>
          <RadioGroup value={profile.preferredTemplate}
            onValueChange={(v) => updateProfile({ preferredTemplate: v })} className="grid gap-1.5">
            {(Object.entries(TEMPLATE_INFO) as [ResumeTemplate, { label: string; description: string }][]).map(
              ([key, { label }]) => (
                <label key={key} className={`flex items-center gap-2 px-3 py-2 rounded-lg border cursor-pointer transition-colors text-xs ${
                  profile.preferredTemplate === key ? "border-primary bg-primary/5 font-medium" : "hover:bg-muted/50"
                }`}>
                  <RadioGroupItem value={key} className="sr-only" />
                  <span>{label}</span>
                </label>
              )
            )}
          </RadioGroup>
        </div>
      </div>

      <input type="hidden" data-can-proceed={canProceed ? "true" : "false"} />
    </div>
  );
}

// ─── Step 2: Job Preferences + API Keys merged ──────────────────
function PreferencesStep({ profile, updateProfile }: { profile: UserProfile; updateProfile: (p: Partial<UserProfile>) => void }) {
  return (
    <div className="space-y-5">
      <div className="space-y-1.5">
        <h3 className="text-lg font-semibold">What are you looking for?</h3>
        <p className="text-sm text-muted-foreground">
          Help us find relevant opportunities. Skip anything you&apos;re not sure about.
        </p>
      </div>

      {/* Search keywords + locations */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="onb-keywords" className="flex items-center gap-1.5">
            <Search className="size-3.5" /> Keywords
          </Label>
          <Input id="onb-keywords" placeholder="React, TypeScript, Fullstack" value={profile.searchKeywords}
            onChange={(e) => updateProfile({ searchKeywords: e.target.value })} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="onb-locations" className="flex items-center gap-1.5">
            <MapPin className="size-3.5" /> Locations
          </Label>
          <Input id="onb-locations" placeholder="San Francisco, Remote" value={profile.preferredLocations}
            onChange={(e) => updateProfile({ preferredLocations: e.target.value })} />
        </div>
      </div>

      {/* Work mode + Employment type + Salary */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="space-y-2">
          <Label className="flex items-center gap-1.5"><Monitor className="size-3.5" /> Work Mode</Label>
          <Select value={profile.workMode} onValueChange={(v) => updateProfile({ workMode: v })}>
            <SelectTrigger className="w-full"><SelectValue placeholder="Any" /></SelectTrigger>
            <SelectContent>
              {(Object.entries(WORK_MODE_LABELS) as [WorkMode, string][]).map(([k, l]) => (
                <SelectItem key={k} value={k}>{l}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label className="flex items-center gap-1.5"><Clock className="size-3.5" /> Job Type</Label>
          <Select value={profile.employmentType} onValueChange={(v) => updateProfile({ employmentType: v })}>
            <SelectTrigger className="w-full"><SelectValue placeholder="Any" /></SelectTrigger>
            <SelectContent>
              {(Object.entries(EMPLOYMENT_LABELS) as [EmploymentType, string][]).map(([k, l]) => (
                <SelectItem key={k} value={k}>{l}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label className="flex items-center gap-1.5"><DollarSign className="size-3.5" /> Salary (USD/yr)</Label>
          <div className="flex items-center gap-1">
            <Input placeholder="Min" type="number" value={profile.salaryMin}
              onChange={(e) => updateProfile({ salaryMin: e.target.value })} className="flex-1" />
            <span className="text-muted-foreground text-xs">–</span>
            <Input placeholder="Max" type="number" value={profile.salaryMax}
              onChange={(e) => updateProfile({ salaryMax: e.target.value })} className="flex-1" />
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Step 3: Summary ────────────────────────────────────────────
function SummaryStep({ profile }: { profile: UserProfile }) {
  const items: { label: string; value: string; icon: React.ElementType }[] = [
    { label: "Name", value: profile.name || "Not set", icon: User },
    { label: "Current Role", value: profile.currentRole || "Not set", icon: Briefcase },
    { label: "Target Role", value: profile.targetRole || "Not set", icon: Target },
    { label: "Experience", value: profile.experienceLevel ? EXPERIENCE_LABELS[profile.experienceLevel as ExperienceLevel] : "Not set", icon: GraduationCap },
    { label: "Industry", value: profile.industry ? INDUSTRY_LABELS[profile.industry as Industry] : "Not set", icon: Building2 },
    { label: "Location", value: profile.location || "Not set", icon: MapPin },
    { label: "Template", value: TEMPLATE_INFO[profile.preferredTemplate as ResumeTemplate]?.label || "Chronological", icon: FileText },
    { label: "Work Mode", value: profile.workMode ? WORK_MODE_LABELS[profile.workMode as WorkMode] : "Any", icon: Monitor },
  ];

  return (
    <div className="space-y-5">
      <div className="flex flex-col items-center text-center space-y-2 py-2">
        <div className="flex items-center justify-center size-12 rounded-full bg-primary/10">
          <CheckCircle2 className="size-6 text-primary" />
        </div>
        <div className="space-y-1">
          <h3 className="text-lg font-semibold">You&apos;re all set!</h3>
          <p className="text-sm text-muted-foreground">
            Here&apos;s your profile. Update anytime in Settings.
          </p>
        </div>
      </div>

      <div className="grid gap-1.5 max-h-60 overflow-y-auto pr-1">
        {items.map(({ label, value, icon: Icon }) => (
          <div key={label} className="flex items-center justify-between p-2.5 rounded-lg border bg-card">
            <div className="flex items-center gap-2">
              <Icon className="size-3.5 text-muted-foreground" />
              <span className="text-xs text-muted-foreground">{label}</span>
            </div>
            <span className="text-sm font-medium text-right max-w-[60%] truncate">{value}</span>
          </div>
        ))}
      </div>

      <div className="p-3 rounded-xl bg-muted/50 border text-center">
        <p className="text-xs text-muted-foreground">
          Start by adding a job posting in <span className="font-medium text-foreground">Ingest</span>, create a
          <span className="font-medium text-foreground"> Persona</span>, or browse your <span className="font-medium text-foreground">Dashboard</span>.
        </p>
      </div>
    </div>
  );
}

// ─── Main Wizard Component ──────────────────────────────────────
export function OnboardingWizard() {
  const {
    isOpen, currentStep, totalSteps, profile, updateProfile,
    nextStep, prevStep, onComplete, onClose,
  } = useOnboarding();

  const StepIcon = STEP_ICONS[currentStep];
  const canProceed = currentStep === 1
    ? profile.name.trim().length > 0 && profile.targetRole.trim().length > 0
    : true;

  const handleNext = () => {
    if (currentStep === totalSteps - 1) onComplete();
    else nextStep();
  };

  const renderStepContent = () => {
    switch (currentStep) {
      case 0: return <WelcomeStep onNext={nextStep} />;
      case 1: return <ProfileStep profile={profile} updateProfile={updateProfile} />;
      case 2: return <PreferencesStep profile={profile} updateProfile={updateProfile} />;
      case 3: return <SummaryStep profile={profile} />;
      default: return null;
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent
        showCloseButton={currentStep > 0}
        className="sm:max-w-xl max-h-[90vh] flex flex-col overflow-hidden p-0 gap-0"
      >
        <DialogTitle className="sr-only">TALVEX — {STEP_TITLES[currentStep]}</DialogTitle>
        <DialogDescription className="sr-only">
          {currentStep === 0 ? "Welcome to TALVEX" : `Step ${currentStep + 1} of ${totalSteps}: ${STEP_TITLES[currentStep]}`}
        </DialogDescription>

        {/* Progress */}
        {currentStep > 0 && currentStep < totalSteps - 1 && (
          <div className="px-6 pt-5 pb-1">
            <StepProgress currentStep={currentStep} totalSteps={totalSteps} />
          </div>
        )}

        {/* Step header */}
        {currentStep > 0 && currentStep < totalSteps - 1 && (
          <div className="px-6 pt-3 pb-1 flex items-center gap-2">
            <div className="flex items-center justify-center size-8 rounded-lg bg-primary/10">
              <StepIcon className="size-4 text-primary" />
            </div>
            <h2 className="text-base font-semibold">{STEP_TITLES[currentStep]}</h2>
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          <div key={currentStep} className="animate-in fade-in-0 duration-300">
            {renderStepContent()}
          </div>
        </div>

        {/* Nav footer */}
        {currentStep > 0 && currentStep < totalSteps - 1 && (
          <div className="px-6 pb-5 border-t pt-4 flex items-center justify-between">
            <Button variant="ghost" size="sm" onClick={prevStep}>
              <ArrowLeft className="size-4" /> Back
            </Button>
            <Button onClick={handleNext} disabled={!canProceed} size="sm" className="gap-1">
              Continue <ArrowRight className="size-4" />
            </Button>
          </div>
        )}

        {currentStep === totalSteps - 1 && (
          <div className="px-6 pb-5 border-t pt-4 flex justify-center">
            <Button onClick={handleNext} size="lg" className="gap-2 min-w-[200px]">
              <Rocket className="size-4" /> Go to Dashboard
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default OnboardingWizard;
