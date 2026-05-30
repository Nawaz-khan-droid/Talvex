export type ApplicationStatus =
  | "SCRAPED"
  | "TAILORED"
  | "SUBMITTED"
  | "SCREENING"
  | "ASSESSMENT"
  | "INTERVIEWING"
  | "OFFER"
  | "REJECTED"
  | "GHOSTED";

export type PrivacyStatus = "CLEAN" | "LEAKED" | "MONITORING";

export type Platform = "linkedin" | "indeed" | "naukri" | "internshala" | "unstop" | "foundit" | "manual" | "webhook" | "email";

export type WorkMode = "remote" | "onsite" | "hybrid";
export type Tenure = "fulltime" | "parttime" | "contract" | "internship" | "freelance";
export type ResponseType = "rejection" | "interview" | "assessment" | "offer" | "ghosted" | "unknown";

export interface PlatformInfo {
  id: Platform;
  name: string;
  domain: string;
  color: string;
  priority: "critical" | "high" | "medium";
}

export const PLATFORMS: PlatformInfo[] = [
  { id: "linkedin", name: "LinkedIn", domain: "linkedin.com", color: "#0A66C2", priority: "critical" },
  { id: "indeed", name: "Indeed", domain: "indeed.com", color: "#2164F3", priority: "critical" },
  { id: "naukri", name: "Naukri", domain: "naukri.com", color: "#4A90D9", priority: "high" },
  { id: "internshala", name: "Internshala", domain: "internshala.com", color: "#0066FF", priority: "high" },
  { id: "unstop", name: "Unstop", domain: "unstop.com", color: "#FF6B00", priority: "high" },
  { id: "foundit", name: "Foundit", domain: "foundit.com", color: "#FF5A00", priority: "medium" },
  { id: "manual", name: "Manual Entry", domain: "", color: "#6B7280", priority: "low" },
  { id: "webhook", name: "Webhook", domain: "", color: "#8B5CF6", priority: "medium" },
  { id: "email", name: "Email Parse", domain: "", color: "#059669", priority: "medium" },
];

export function getPlatformInfo(platform: string): PlatformInfo {
  return PLATFORMS.find((p) => p.id === platform) || PLATFORMS[PLATFORMS.length - 1];
}

export interface JobPersona {
  id: string;
  name: string;
  skillsJson: string;
  masterBullets: string;
  summaryTemplate: string | null;
  createdAt: string;
  updatedAt: string;
  _count?: { applications: number };
}

export interface Application {
  id: string;
  personaId: string;
  company: string;
  roleTitle: string;
  jobDescription: string;
  status: ApplicationStatus;
  matchScore: number;
  atsScore: number;
  extractedKeywords: string | null;
  privacyStatus: PrivacyStatus;
  appliedDate: string | null;
  lastFollowUp: string | null;
  createdAt: string;
  updatedAt: string;
  // Multi-platform
  platform: string;
  jobUrl: string | null;
  salaryMin: number | null;
  salaryMax: number | null;
  salaryCurrency: string;
  workMode: string | null;
  tenure: string | null;
  perks: string | null;
  location: string | null;
  companySize: string | null;
  sourceEmail: string | null;
  // Follow-up
  nextFollowUp: string | null;
  followUpCount: number;
  lastResponseAt: string | null;
  responseType: string | null;
  notes: string | null;
  // Relations
  persona?: JobPersona;
  canary?: TrackingCanary | null;
  _count?: { resumeVersions: number; auditLogs: number };
}

export interface TrackingCanary {
  id: string;
  appId: string;
  canaryEmail: string;
  trackingSlug: string | null;
  leakFlagged: boolean;
  leakDetails: string | null;
  createdAt: string;
}

export interface ResumeVersion {
  id: string;
  appId: string;
  version: number;
  filePath: string;
  contentHash: string;
  createdAt: string;
}

export interface AuditLog {
  id: string;
  appId: string | null;
  action: string;
  actor: string;
  details: string | null;
  timestamp: string;
}

export interface AnalysisResult {
  matchScore: number;
  matchedKeywords: string[];
  missingKeywords: string[];
  recommendedPersona: string | null;
  atsScore: number;
  // Enhanced scoring (available when persona skills are present)
  enhanced?: {
    keywordMatchPct: number;
    phraseMatchPct: number;
    sectionBonus: number;
    overallScore: number;
    matchedPhrases: string[];
    missingPhrases: string[];
    detectedSections: string[];
    recommendations: string[];
  } | null;
}

export interface JDParseResult {
  title: string;
  company: string;
  skills: string[];
  salaryMin: number | null;
  salaryMax: number | null;
  salaryCurrency: string;
  workMode: WorkMode | null;
  tenure: Tenure | null;
  perks: string[];
  location: string | null;
  companySize: string | null;
  experienceRequired: string | null;
  educationRequired: string | null;
  rawDescription: string;
}

export interface FollowUpAlert {
  applicationId: string;
  company: string;
  roleTitle: string;
  platform: string;
  daysSinceApplied: number;
  daysSinceLastFollowUp: number | null;
  followUpCount: number;
  suggestedTemplate: string;
  urgency: "urgent" | "normal" | "low";
}

export interface ResumeUploadResult {
  success: boolean;
  upload: {
    fileName: string;
    fileType: string;
    fileSize: number;
    contentHash: string;
    filePath: string;
    version: number;
  };
  analysis: {
    wordCount: number;
    atsScore: number;
    matchScore: number;
    ocrUsed: boolean;
    detectedSections: string[];
    contactInfo: Record<string, string>;
    detectedSkills: string[];
    issues: string[];
    recommendations: string[];
  };
}

export interface RecommendationData {
  personaName: string;
  currentSkills: string[];
  skillCount: number;
  skillGaps: {
    skill: string;
    category: string;
    priority: "high" | "medium" | "low";
    marketDemand: number;
    learningPath: string;
    estimatedWeeks: number;
  }[];
  tradeRecommendations: {
    targetRole: string;
    alignmentScore: number;
    missingSkills: {
      skill: string;
      category: string;
      priority: string;
      marketDemand: number;
      learningPath: string;
      estimatedWeeks: number;
    }[];
    salaryRange: { min: number; max: number };
    marketOutlook: string;
    actionSteps: string[];
  }[];
  pipelineTelemetry: {
    totalApplications: number;
    averageMatchScore: number;
    highMatchCount: number;
    statusBreakdown: Record<string, number>;
    topTargetRoles: { role: string; count: number; avgScore: number }[];
  };
  competitivePositioning: {
    strengths: { category: string; skills: string[]; level: string }[];
    weaknesses: { category: string; criticalGaps: string[]; impact: string }[];
    overallReadiness: number;
  };
  generatedAt: string;
}

export interface AnalyticsData {
  funnel: Record<ApplicationStatus, number>;
  avgDaysInState: Record<string, number>;
  scoreDistribution: { range: string; count: number }[];
  topCompanies: { company: string; count: number }[];
  followUpVelocity: number;
  totalApplications: number;
  totalPersonas: number;
  overallMatchRate: number;
  leakAlerts: number;
  // New platform analytics
  platformBreakdown: { platform: string; count: number; avgScore: number }[];
  followUpAlerts: number;
  responseRate: number;
}

export const STATUS_ORDER: ApplicationStatus[] = [
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

export const STATUS_COLORS: Record<ApplicationStatus, string> = {
  SCRAPED: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
  TAILORED: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300",
  SUBMITTED: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
  SCREENING: "bg-cyan-100 text-cyan-700 dark:bg-cyan-900/30 dark:text-cyan-300",
  ASSESSMENT: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300",
  INTERVIEWING: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
  OFFER: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
  REJECTED: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300",
  GHOSTED: "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400",
};

export const PRIVACY_COLORS: Record<PrivacyStatus, string> = {
  CLEAN: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
  MONITORING: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
  LEAKED: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300",
};
