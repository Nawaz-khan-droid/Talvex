"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import {
  Zap,
  CheckCircle2,
  XCircle,
  Sparkles,
  Plus,
  Target,
  Globe,
  MapPin,
  Building2,
  Clock,
  DollarSign,
  Briefcase,
  Loader2,
  Brain,
  Webhook,
  Link2,
  Tag,
  Info,
  Lightbulb,
  TrendingUp,
  MessageSquare,
} from "lucide-react";
import type { JobPersona, JDParseResult } from "@/lib/types";
import { PLATFORMS, getPlatformInfo } from "@/lib/types";
import { toast } from "sonner";

interface JobAnalyzerProps {
  personas: JobPersona[];
  loading: boolean;
  onRefresh: () => void;
  onNavigate: (tab: string) => void;
}

export function JobAnalyzer({ personas, loading, onRefresh, onNavigate }: JobAnalyzerProps) {
  const [jobDescription, setJobDescription] = useState("");
  const [selectedPersona, setSelectedPersona] = useState<string>("");
  const [selectedPlatform, setSelectedPlatform] = useState<string>("manual");
  const [analyzing, setAnalyzing] = useState(false);
  const [useLLM, setUseLLM] = useState(true);
  const [result, setResult] = useState<{
    matchScore: number;
    matchedKeywords: string[];
    missingKeywords: string[];
    recommendedPersona: string | null;
    atsScore: number;
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
  } | null>(null);
  const [parsedJD, setParsedJD] = useState<JDParseResult | null>(null);

  const handleAnalyze = async () => {
    if (!jobDescription.trim()) {
      toast.error("Please paste a job description");
      return;
    }

    setAnalyzing(true);
    setResult(null);
    setParsedJD(null);

    try {
      const res = await fetch("/api/jd/parse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          jobDescription: jobDescription.trim(),
          personaId: selectedPersona || undefined,
          platform: selectedPlatform,
        }),
      });

      if (!res.ok) throw new Error("Failed to analyze");

      const data = await res.json();
      setResult({
        ...data.analysis,
        enhanced: data.enhanced || null,
      });
      setParsedJD({
        ...data.parsed,
        rawDescription: jobDescription.trim(),
      });

      if (data.meta?.llmUsed) {
        toast.success("AI-powered parsing complete");
      } else {
        toast.success("Analysis complete (regex fallback)");
      }
    } catch {
      toast.error("Failed to analyze job description");
    } finally {
      setAnalyzing(false);
    }
  };

  const handleCreateApplication = async () => {
    if (!parsedJD || !selectedPersona) {
      toast.error("Please analyze a job description and select a persona first");
      return;
    }

    try {
      const res = await fetch("/api/applications", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          personaId: selectedPersona,
          company: parsedJD.company || "Unknown Company",
          roleTitle: parsedJD.title || "Unknown Role",
          jobDescription: parsedJD.rawDescription,
          matchScore: result?.matchScore || 0,
          atsScore: result?.atsScore || 0,
          extractedKeywords: JSON.stringify(result?.matchedKeywords || []),
          // New fields
          platform: selectedPlatform,
          salaryMin: parsedJD.salaryMin,
          salaryMax: parsedJD.salaryMax,
          salaryCurrency: parsedJD.salaryCurrency,
          workMode: parsedJD.workMode,
          tenure: parsedJD.tenure,
          perks: parsedJD.perks,
          location: parsedJD.location,
          companySize: parsedJD.companySize,
        }),
      });

      if (!res.ok) throw new Error("Failed to create application");

      toast.success("Application created and added to pipeline");
      setJobDescription("");
      setParsedJD(null);
      setResult(null);
      onRefresh();
      onNavigate("pipeline");
    } catch {
      toast.error("Failed to create application");
    }
  };

  const getScoreColor = (score: number) => {
    if (score >= 70) return "text-emerald-500";
    if (score >= 40) return "text-amber-500";
    return "text-red-500";
  };

  const getScoreLabel = (score: number) => {
    if (score >= 80) return "Excellent Match";
    if (score >= 60) return "Good Match";
    if (score >= 40) return "Fair Match";
    return "Low Match";
  };

  const platformInfo = getPlatformInfo(selectedPlatform);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6">
      <div className="space-y-4">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-semibold flex items-center gap-2">
              <Zap className="h-4 w-4 text-primary" />
              Job Description
            </CardTitle>
            <CardDescription>
              Paste a job description or use browser extension to auto-capture
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-2">
                <Label>Select Persona</Label>
                <Select value={selectedPersona} onValueChange={setSelectedPersona}>
                  <SelectTrigger className="h-9 text-sm">
                    <SelectValue placeholder="Auto-detect" />
                  </SelectTrigger>
                  <SelectContent>
                    {personas.map((p) => (
                      <SelectItem key={p.id} value={p.id}>
                        {p.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Source Platform</Label>
                <Select value={selectedPlatform} onValueChange={setSelectedPlatform}>
                  <SelectTrigger className="h-9 text-sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PLATFORMS.map((p) => (
                      <SelectItem key={p.id} value={p.id}>
                        <div className="flex items-center gap-2">
                          <div className="w-2 h-2 rounded-full" style={{ backgroundColor: p.color }} />
                          {p.name}
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* LLM Toggle */}
            <div className="flex items-center justify-between p-2 rounded-lg bg-muted/50">
              <div className="flex items-center gap-2">
                <Brain className="h-3.5 w-3.5 text-primary" />
                <Label className="text-xs font-medium">AI-Powered Parsing (OpenRouter)</Label>
              </div>
              <Button
                variant={useLLM ? "default" : "outline"}
                size="sm"
                className="h-7 text-xs"
                onClick={() => setUseLLM(!useLLM)}
              >
                {useLLM ? "ON" : "OFF"}
              </Button>
            </div>

            {/* Job URL input */}
            <div className="space-y-2">
              <Label className="flex items-center gap-1">
                <Link2 className="h-3 w-3" />
                Job URL (optional)
              </Label>
              <Input
                placeholder="https://linkedin.com/jobs/view/..."
                className="h-9 text-sm"
                id="job-url"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="job-desc">Paste Job Description</Label>
              <Textarea
                id="job-desc"
                placeholder="Paste the full job description here..."
                value={jobDescription}
                onChange={(e) => setJobDescription(e.target.value)}
                rows={10}
                className="text-sm resize-none"
              />
            </div>

            <Button
              className="w-full"
              onClick={handleAnalyze}
              disabled={analyzing || !jobDescription.trim()}
            >
              {analyzing ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  AI Analyzing...
                </>
              ) : (
                <>
                  <Target className="h-4 w-4 mr-2" />
                  Analyze Match
                </>
              )}
            </Button>
          </CardContent>
        </Card>
      </div>

      <div className="space-y-4">
        {analyzing && (
          <Card>
            <CardContent className="py-12 text-center">
              <div className="space-y-3">
                <Loader2 className="h-8 w-8 mx-auto text-primary animate-spin" />
                <p className="text-sm font-medium">Analyzing with AI</p>
                <p className="text-xs text-muted-foreground">
                  Extracting skills, salary, mode, tenure, and computing match score...
                </p>
              </div>
            </CardContent>
          </Card>
        )}

        {!analyzing && !result && (
          <Card>
            <CardContent className="py-12 text-center">
              <Target className="h-10 w-10 mx-auto text-muted-foreground/30 mb-3" />
              <p className="text-sm text-muted-foreground">
                Paste a job description and click &quot;Analyze Match&quot; to see AI-powered results.
              </p>
              <div className="flex items-center justify-center gap-3 mt-3 text-[10px] text-muted-foreground">
                <div className="flex items-center gap-1"><Brain className="h-3 w-3" /> LLM Parsing</div>
                <div className="flex items-center gap-1"><DollarSign className="h-3 w-3" /> Salary</div>
                <div className="flex items-center gap-1"><Globe className="h-3 w-3" /> Work Mode</div>
                <div className="flex items-center gap-1"><Clock className="h-3 w-3" /> Tenure</div>
              </div>
            </CardContent>
          </Card>
        )}

        {!analyzing && result && (
          <>
            {/* Parsed JD Metadata */}
            {parsedJD && (
              <Card className="border-primary/20">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-semibold flex items-center gap-2">
                    <Info className="h-3.5 w-3.5 text-primary" />
                    Extracted Information
                    {useLLM && (
                      <Badge variant="outline" className="text-[10px] text-primary border-primary/30">
                        AI Parsed
                      </Badge>
                    )}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="p-2 rounded bg-muted/50">
                      <span className="text-muted-foreground">Title</span>
                      <p className="font-medium mt-0.5">{parsedJD.title || "Not detected"}</p>
                    </div>
                    <div className="p-2 rounded bg-muted/50">
                      <span className="text-muted-foreground">Company</span>
                      <p className="font-medium mt-0.5">{parsedJD.company || "Not detected"}</p>
                    </div>
                    <div className="p-2 rounded bg-muted/50">
                      <span className="text-muted-foreground">Location</span>
                      <p className="font-medium mt-0.5">{parsedJD.location || "Not mentioned"}</p>
                    </div>
                    <div className="p-2 rounded bg-muted/50">
                      <span className="text-muted-foreground">Platform</span>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        <div className="w-2 h-2 rounded-full" style={{ backgroundColor: platformInfo.color }} />
                        <span className="font-medium">{platformInfo.name}</span>
                      </div>
                    </div>
                    <div className="p-2 rounded bg-muted/50">
                      <span className="text-muted-foreground">Salary Range</span>
                      <p className="font-medium mt-0.5">
                        {parsedJD.salaryMin && parsedJD.salaryMax
                          ? `${parsedJD.salaryCurrency} ${(parsedJD.salaryMin / 1000).toFixed(0)}K - ${(parsedJD.salaryMax / 1000).toFixed(0)}K`
                          : parsedJD.salaryMin
                          ? `From ${parsedJD.salaryCurrency} ${(parsedJD.salaryMin / 1000).toFixed(0)}K`
                          : "Not mentioned"}
                      </p>
                    </div>
                    <div className="p-2 rounded bg-muted/50">
                      <span className="text-muted-foreground">Work Mode</span>
                      <p className="font-medium mt-0.5 capitalize">{parsedJD.workMode || "Not specified"}</p>
                    </div>
                    <div className="p-2 rounded bg-muted/50">
                      <span className="text-muted-foreground">Tenure Type</span>
                      <p className="font-medium mt-0.5 capitalize">{parsedJD.tenure || "Not specified"}</p>
                    </div>
                    <div className="p-2 rounded bg-muted/50">
                      <span className="text-muted-foreground">Company Size</span>
                      <p className="font-medium mt-0.5 capitalize">{parsedJD.companySize || "Not specified"}</p>
                    </div>
                  </div>

                  {parsedJD.experienceRequired && (
                    <div className="text-xs p-2 rounded bg-muted/50">
                      <span className="text-muted-foreground">Experience Required: </span>
                      <span className="font-medium">{parsedJD.experienceRequired}</span>
                    </div>
                  )}

                  {parsedJD.perks && parsedJD.perks.length > 0 && (
                    <div>
                      <p className="text-xs text-muted-foreground mb-1">Perks & Benefits</p>
                      <div className="flex flex-wrap gap-1">
                        {parsedJD.perks.map((perk, i) => (
                          <Badge key={i} variant="outline" className="text-[10px]">
                            {perk}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}

                  {parsedJD.skills && parsedJD.skills.length > 0 && (
                    <div>
                      <p className="text-xs text-muted-foreground mb-1">
                        <Tag className="h-3 w-3 inline mr-1" />
                        Detected Skills ({parsedJD.skills.length})
                      </p>
                      <div className="flex flex-wrap gap-1">
                        {parsedJD.skills.slice(0, 15).map((skill) => (
                          <Badge key={skill} variant="secondary" className="text-[10px]">
                            {skill}
                          </Badge>
                        ))}
                        {parsedJD.skills.length > 15 && (
                          <Badge variant="secondary" className="text-[10px]">
                            +{parsedJD.skills.length - 15} more
                          </Badge>
                        )}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            {/* Match Score */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-semibold">Match Score</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-center py-4">
                  <div className="relative w-32 h-32">
                    <svg className="w-32 h-32 -rotate-90" viewBox="0 0 120 120">
                      <circle cx="60" cy="60" r="50" fill="none" stroke="currentColor" className="text-muted/30" strokeWidth="8" />
                      <circle cx="60" cy="60" r="50" fill="none" stroke="currentColor" className={getScoreColor(result.matchScore)} strokeWidth="8" strokeDasharray={`${(result.matchScore / 100) * 314} 314`} strokeLinecap="round" />
                    </svg>
                    <div className="absolute inset-0 flex flex-col items-center justify-center">
                      <span className={`text-2xl font-bold ${getScoreColor(result.matchScore)}`}>{result.matchScore}</span>
                      <span className="text-[10px] text-muted-foreground">%</span>
                    </div>
                  </div>
                </div>
                <p className={`text-sm text-center font-medium ${getScoreColor(result.matchScore)}`}>{getScoreLabel(result.matchScore)}</p>
                {result.recommendedPersona && !selectedPersona && (
                  <div className="text-center">
                    <p className="text-xs text-muted-foreground">Recommended persona:</p>
                    <Badge className="mt-1">{result.recommendedPersona}</Badge>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* ATS Score */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-semibold">ATS Score</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Applicant Tracking System Compatibility</span>
                  <span className="font-semibold">{result.atsScore}%</span>
                </div>
                <Progress value={result.atsScore} className="h-2" />
              </CardContent>
            </Card>

            {/* Keywords */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-semibold">Keywords</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {result.matchedKeywords.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-emerald-600 dark:text-emerald-400 mb-2 flex items-center gap-1">
                      <CheckCircle2 className="h-3 w-3" />
                      Matched ({result.matchedKeywords.length})
                    </p>
                    <div className="flex flex-wrap gap-1">
                      {result.matchedKeywords.slice(0, 15).map((kw) => (
                        <Badge key={kw} variant="secondary" className="text-xs bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300">{kw}</Badge>
                      ))}
                    </div>
                  </div>
                )}
                {result.missingKeywords.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-red-600 dark:text-red-400 mb-2 flex items-center gap-1">
                      <XCircle className="h-3 w-3" />
                      Missing ({result.missingKeywords.length})
                    </p>
                    <div className="flex flex-wrap gap-1">
                      {result.missingKeywords.slice(0, 15).map((kw) => (
                        <Badge key={kw} variant="secondary" className="text-xs bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300">{kw}</Badge>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Enhanced Scoring Breakdown */}
            {result.enhanced && (
              <>
                <Card className="border-primary/20">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm font-semibold flex items-center gap-2">
                      <TrendingUp className="h-3.5 w-3.5 text-primary" />
                      Score Breakdown
                    </CardTitle>
                    <CardDescription>60% keywords + 40% phrases + section bonus</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="space-y-2">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-muted-foreground">Keyword Match</span>
                        <span className="font-semibold">{result.enhanced.keywordMatchPct}%</span>
                      </div>
                      <Progress value={result.enhanced.keywordMatchPct} className="h-1.5" />
                      <p className="text-[10px] text-muted-foreground">Weight: 60%</p>
                    </div>
                    <Separator />
                    <div className="space-y-2">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-muted-foreground flex items-center gap-1">
                          <MessageSquare className="h-3 w-3" />
                          Phrase Match
                        </span>
                        <span className="font-semibold">{result.enhanced.phraseMatchPct}%</span>
                      </div>
                      <Progress value={result.enhanced.phraseMatchPct} className="h-1.5" />
                      <p className="text-[10px] text-muted-foreground">Weight: 40%</p>
                    </div>
                    <Separator />
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-muted-foreground">Section Bonus</span>
                      <Badge variant="outline" className="text-[10px]">+{result.enhanced.sectionBonus} pts</Badge>
                    </div>
                  </CardContent>
                </Card>

                {/* Matched Phrases */}
                {result.enhanced.matchedPhrases.length > 0 && (
                  <Card>
                    <CardHeader className="pb-3">
                      <CardTitle className="text-sm font-semibold flex items-center gap-2">
                        <MessageSquare className="h-3.5 w-3.5 text-emerald-500" />
                        Matched Phrases ({result.enhanced.matchedPhrases.length})
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="flex flex-wrap gap-1 max-h-32 overflow-y-auto">
                        {result.enhanced.matchedPhrases.slice(0, 15).map((phrase) => (
                          <Badge key={phrase} variant="secondary" className="text-[10px] bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300">
                            {phrase}
                          </Badge>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* Missing Phrases */}
                {result.enhanced.missingPhrases.length > 0 && (
                  <Card>
                    <CardHeader className="pb-3">
                      <CardTitle className="text-sm font-semibold flex items-center gap-2">
                        <XCircle className="h-3.5 w-3.5 text-red-500" />
                        Missing Phrases ({result.enhanced.missingPhrases.length})
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="flex flex-wrap gap-1 max-h-32 overflow-y-auto">
                        {result.enhanced.missingPhrases.slice(0, 10).map((phrase) => (
                          <Badge key={phrase} variant="secondary" className="text-[10px] bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300">
                            {phrase}
                          </Badge>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* Recommendations */}
                {result.enhanced.recommendations.length > 0 && (
                  <Card className="border-amber-200 dark:border-amber-900/50">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-sm font-semibold flex items-center gap-2 text-amber-700 dark:text-amber-400">
                        <Lightbulb className="h-3.5 w-3.5" />
                        Recommendations
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      {result.enhanced.recommendations.slice(0, 6).map((rec, i) => (
                        <div key={i} className="flex items-start gap-2 text-xs">
                          <Sparkles className="h-3 w-3 text-amber-500 mt-0.5 shrink-0" />
                          <span>{rec}</span>
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                )}
              </>
            )}

            {selectedPersona && (
              <Button className="w-full" onClick={handleCreateApplication}>
                <Plus className="h-4 w-4 mr-2" />
                Add to Pipeline
              </Button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
