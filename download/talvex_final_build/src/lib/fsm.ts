import type { ApplicationStatus } from "./types";

export interface FSMTransition {
  from: ApplicationStatus;
  to: ApplicationStatus;
  label: string;
  isTerminal?: boolean;
}

export const FSM_STATES: ApplicationStatus[] = [
  "SCRAPED",
  "TAILORED",
  "SUBMITTED",
  "SCREENING",
  "ASSESSMENT",
  "INTERVIEWING",
  "OFFER",
  "REJECTED",
  "GHOSTED",
];

export const TERMINAL_STATES: ApplicationStatus[] = ["OFFER", "REJECTED", "GHOSTED"];

export const FSM_TRANSITIONS: FSMTransition[] = [
  { from: "SCRAPED", to: "TAILORED", label: "Start Tailoring" },
  { from: "SCRAPED", to: "REJECTED", label: "Skip / Not Applying", isTerminal: true },
  { from: "TAILORED", to: "SUBMITTED", label: "Submit Application" },
  { from: "TAILORED", to: "REJECTED", label: "Skip / Not Applying", isTerminal: true },
  { from: "SUBMITTED", to: "SCREENING", label: "Under Review / Screening" },
  { from: "SUBMITTED", to: "ASSESSMENT", label: "Assessment / Test Sent" },
  { from: "SUBMITTED", to: "INTERVIEWING", label: "Interview Scheduled" },
  { from: "SUBMITTED", to: "GHOSTED", label: "No Response (Ghosted)", isTerminal: true },
  { from: "SUBMITTED", to: "REJECTED", label: "Rejected", isTerminal: true },
  { from: "SCREENING", to: "ASSESSMENT", label: "Assessment / Test Sent" },
  { from: "SCREENING", to: "INTERVIEWING", label: "Interview Scheduled" },
  { from: "SCREENING", to: "REJECTED", label: "Rejected After Screening", isTerminal: true },
  { from: "SCREENING", to: "GHOSTED", label: "Ghosted After Screening", isTerminal: true },
  { from: "ASSESSMENT", to: "INTERVIEWING", label: "Interview Scheduled" },
  { from: "ASSESSMENT", to: "REJECTED", label: "Rejected After Assessment", isTerminal: true },
  { from: "ASSESSMENT", to: "GHOSTED", label: "Ghosted After Assessment", isTerminal: true },
  { from: "INTERVIEWING", to: "OFFER", label: "Offer Received", isTerminal: true },
  { from: "INTERVIEWING", to: "REJECTED", label: "Rejected After Interview", isTerminal: true },
  { from: "INTERVIEWING", to: "GHOSTED", label: "Ghosted After Interview", isTerminal: true },
];

export function getNextTransitions(currentStatus: ApplicationStatus): FSMTransition[] {
  if (TERMINAL_STATES.includes(currentStatus)) {
    return [];
  }
  return FSM_TRANSITIONS.filter((t) => t.from === currentStatus);
}

export function canTransition(from: ApplicationStatus, to: ApplicationStatus): boolean {
  return FSM_TRANSITIONS.some((t) => t.from === from && t.to === to);
}

export function isTerminal(status: ApplicationStatus): boolean {
  return TERMINAL_STATES.includes(status);
}

export function getStatusLabel(status: ApplicationStatus): string {
  const labels: Record<ApplicationStatus, string> = {
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
  return labels[status];
}

export function getStatusEmoji(status: ApplicationStatus): string {
  const emojis: Record<ApplicationStatus, string> = {
    SCRAPED: "📥",
    TAILORED: "✂️",
    SUBMITTED: "📤",
    SCREENING: "🔍",
    ASSESSMENT: "📝",
    INTERVIEWING: "🎯",
    OFFER: "🎉",
    REJECTED: "❌",
    GHOSTED: "👻",
  };
  return emojis[status];
}
