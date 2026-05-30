"use client";

import { useSyncExternalStore, useCallback } from "react";

// ── Re-export types from constants (single source of truth) ─────
export type {
  ExperienceLevel,
  Industry,
  ResumeTemplate,
  WorkMode,
  EmploymentType,
} from "@/lib/constants";

export interface UserProfile {
  name: string;
  currentRole: string;
  targetRole: string;
  experienceLevel: string;  // ExperienceLevel | ""
  industry: string;         // Industry | ""
  location: string;
  resumeUploaded: boolean;
  resumeFileName: string;
  preferredTemplate: string; // ResumeTemplate
  includePhoto: boolean;
  pagePreference: 1 | 2;
  searchKeywords: string;
  preferredLocations: string;
  workMode: string;         // WorkMode | ""
  employmentType: string;   // EmploymentType | ""
  salaryMin: string;
  salaryMax: string;
}

export const DEFAULT_PROFILE: UserProfile = {
  name: "",
  currentRole: "",
  targetRole: "",
  experienceLevel: "",
  industry: "",
  location: "",
  resumeUploaded: false,
  resumeFileName: "",
  preferredTemplate: "chronological",
  includePhoto: false,
  pagePreference: 1,
  searchKeywords: "",
  preferredLocations: "",
  workMode: "",
  employmentType: "",
  salaryMin: "",
  salaryMax: "",
};

const ONBOARDING_COMPLETE_KEY = "talvex_onboarding_complete";
const ONBOARDING_PROGRESS_KEY = "talvex_onboarding_progress";
const USER_PROFILE_KEY = "talvex_user_profile";

export const STORAGE_KEYS = {
  complete: ONBOARDING_COMPLETE_KEY,
  progress: ONBOARDING_PROGRESS_KEY,
  profile: USER_PROFILE_KEY,
} as const;

// ── Helpers ─────────────────────────────────────────────────────

function writeJson(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // storage unavailable
  }
}

function removeKey(key: string): void {
  localStorage.removeItem(key);
}

function emitChange(): void {
  window.dispatchEvent(new StorageEvent("storage"));
}

function subscribe(callback: () => void): () => void {
  window.addEventListener("storage", callback);
  return () => window.removeEventListener("storage", callback);
}

// Server snapshots (SSR-safe)
const serverDefaultProfile = JSON.stringify(DEFAULT_PROFILE);

// ── Hook ────────────────────────────────────────────────────────

export interface UseOnboardingReturn {
  isOpen: boolean;
  currentStep: number;
  totalSteps: number;
  profile: UserProfile;
  isComplete: boolean;
  updateProfile: (partial: Partial<UserProfile>) => void;
  nextStep: () => void;
  prevStep: () => void;
  goToStep: (step: number) => void;
  onComplete: () => void;
  onClose: () => void;
  resetOnboarding: () => void;
}

export function useOnboarding(): UseOnboardingReturn {
  const completeJson = useSyncExternalStore(
    subscribe,
    () => localStorage.getItem(ONBOARDING_COMPLETE_KEY) ?? "false",
    () => "false"
  );
  const profileJson = useSyncExternalStore(
    subscribe,
    () => localStorage.getItem(USER_PROFILE_KEY) ?? serverDefaultProfile,
    () => serverDefaultProfile
  );
  const progressJson = useSyncExternalStore(
    subscribe,
    () => localStorage.getItem(ONBOARDING_PROGRESS_KEY) ?? "0",
    () => "0"
  );

  const isComplete = completeJson === "true";
  const profile: UserProfile = JSON.parse(profileJson);
  const currentStep: number = progressJson !== "null" ? JSON.parse(progressJson) : 0;

  const isOpen = !isComplete;

  const updateProfile = useCallback((partial: Partial<UserProfile>) => {
    const raw = localStorage.getItem(USER_PROFILE_KEY);
    const current: UserProfile = raw ? JSON.parse(raw) : DEFAULT_PROFILE;
    const updated = { ...current, ...partial };
    writeJson(USER_PROFILE_KEY, updated);
    emitChange();
  }, []);

  const nextStep = useCallback(() => {
    const raw = localStorage.getItem(ONBOARDING_PROGRESS_KEY);
    const step: number = raw ? JSON.parse(raw) : 0;
    writeJson(ONBOARDING_PROGRESS_KEY, Math.min(step + 1, 3)); // max step = 3
    emitChange();
  }, []);

  const prevStep = useCallback(() => {
    const raw = localStorage.getItem(ONBOARDING_PROGRESS_KEY);
    const step: number = raw ? JSON.parse(raw) : 0;
    writeJson(ONBOARDING_PROGRESS_KEY, Math.max(step - 1, 0));
    emitChange();
  }, []);

  const goToStep = useCallback((step: number) => {
    writeJson(ONBOARDING_PROGRESS_KEY, Math.max(0, Math.min(step, 3)));
    emitChange();
  }, []);

  const onComplete = useCallback(() => {
    const profileRaw = localStorage.getItem(USER_PROFILE_KEY);
    if (profileRaw) {
      writeJson(USER_PROFILE_KEY, JSON.parse(profileRaw));
    }
    writeJson(ONBOARDING_COMPLETE_KEY, true);
    removeKey(ONBOARDING_PROGRESS_KEY);
    emitChange();
  }, []);

  const onClose = useCallback(() => {
    writeJson(ONBOARDING_COMPLETE_KEY, true);
    emitChange();
  }, []);

  const resetOnboarding = useCallback(() => {
    removeKey(ONBOARDING_COMPLETE_KEY);
    removeKey(ONBOARDING_PROGRESS_KEY);
    removeKey(USER_PROFILE_KEY);
    emitChange();
  }, []);

  return {
    isOpen,
    currentStep,
    totalSteps: 4, // Welcome → Profile → Preferences → All Set
    profile,
    isComplete,
    updateProfile,
    nextStep,
    prevStep,
    goToStep,
    onComplete,
    onClose,
    resetOnboarding,
  };
}
