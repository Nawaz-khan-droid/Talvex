/**
 * TALVEX — Shared Constants & Label Maps
 *
 * Single source of truth for all enum labels, template info, and static
 * reference data used by onboarding wizard, settings panel, and API routes.
 * Import from here — NEVER duplicate these maps.
 */

// ── Experience Levels ───────────────────────────────────────────
export type ExperienceLevel = "entry" | "mid" | "senior" | "executive";

export const EXPERIENCE_LABELS: Record<ExperienceLevel, string> = {
  entry: "Entry Level (0-2 yrs)",
  mid: "Mid Level (3-5 yrs)",
  senior: "Senior (6-10 yrs)",
  executive: "Executive (10+)",
};

// ── Industries ──────────────────────────────────────────────────
export type Industry =
  | "technology"
  | "finance"
  | "healthcare"
  | "consulting"
  | "education"
  | "manufacturing"
  | "other";

export const INDUSTRY_LABELS: Record<Industry, string> = {
  technology: "Technology",
  finance: "Finance",
  healthcare: "Healthcare",
  consulting: "Consulting",
  education: "Education",
  manufacturing: "Manufacturing",
  other: "Other",
};

// ── Resume Templates ────────────────────────────────────────────
export type ResumeTemplate =
  | "chronological"
  | "functional"
  | "combination"
  | "targeted";

export const TEMPLATE_INFO: Record<
  ResumeTemplate,
  { label: string; description: string }
> = {
  chronological: {
    label: "Chronological",
    description: "Standard format highlighting work history in reverse order",
  },
  functional: {
    label: "Functional",
    description: "Skills-focused format ideal for career changers or gaps",
  },
  combination: {
    label: "Combination",
    description: "Blends skills and experience for a balanced presentation",
  },
  targeted: {
    label: "Targeted",
    description: "Customized for a specific job description for maximum impact",
  },
};

// ── Work Mode ───────────────────────────────────────────────────
export type WorkMode = "remote" | "onsite" | "hybrid" | "no_preference";

export const WORK_MODE_LABELS: Record<WorkMode, string> = {
  remote: "Remote",
  onsite: "On-site",
  hybrid: "Hybrid",
  no_preference: "No preference",
};

// ── Employment Type ─────────────────────────────────────────────
export type EmploymentType =
  | "fulltime"
  | "parttime"
  | "contract"
  | "intern"
  | "no_preference";

export const EMPLOYMENT_LABELS: Record<EmploymentType, string> = {
  fulltime: "Full-time",
  parttime: "Part-time",
  contract: "Contract",
  intern: "Intern",
  no_preference: "No preference",
};

// ── LLM Agent Roles ────────────────────────────────────────────
export type AgentRole = "searcher" | "parser" | "architect" | "builder";

// ── FSM Statuses ───────────────────────────────────────────────
export const FSM_STATUSES = [
  "SCRAPED",
  "TAILORED",
  "SUBMITTED",
  "SCREENING",
  "ASSESSMENT",
  "INTERVIEWING",
  "OFFER",
  "REJECTED",
  "GHOSTED",
] as const;

export const STATUS_LABELS: Record<string, string> = {
  SCRAPED: "Scraped",
  TAILORED: "Tailored",
  SUBMITTED: "Submitted",
  SCREENING: "Screening",
  ASSESSMENT: "Assessment",
  INTERVIEWING: "Interviewing",
  OFFER: "Offer",
  REJECTED: "Rejected",
  GHOSTED: "Ghosted",
};
