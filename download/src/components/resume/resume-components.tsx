"use client";

import { useState, useCallback, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
  Upload,
  FileText,
  Download,
  History,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Shield,
  Brain,
  TrendingUp,
  Target,
  ScanLine,
  Loader2,
  Eye,
  Sparkles,
  ChevronRight,
  Zap,
  Clock,
  BarChart3,
  Lightbulb,
  AlertTriangle,
  FileCheck,
  Users,
  Briefcase,
} from "lucide-react";
import type { Application, ResumeUploadResult, RecommendationData } from "@/lib/types";
import { toast } from "sonner";

interface ResumeBuilderProps {
  applications: Application[];
  personas: { id: string; name: string }[];
  loading: boolean;
  onRefresh: () => void;
}

export function ResumeBuilder({ applications, personas, loading, onRefresh }: ResumeBuilderProps) {
  const [selectedAppId, setSelectedAppId] = useState<string>("");
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<ResumeUploadResult | null>(null);
  const [versions, setVersions] = useState<{ id: string; version: number; filePath: string; contentHash: string; createdAt: string }[]>([]);
  const [recommendations, setRecommendations] = useState<RecommendationData | null>(null);
  const [loadingRecs, setLoadingRecs] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const selectedApp = applications.find((a) => a.id === selectedAppId);
  const selectedPersona = personas.find((p) => p.id === selectedApp?.personaId);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) {
      validateAndSetFile(f);
    }
  };

  const validateAndSetFile = (f: File) => {
    const ext = f.name.substring(f.name.lastIndexOf(".")).toLowerCase();
    if (![".docx", ".pdf", ".txt"].includes(ext)) {
      toast.error("Please upload a .docx, .pdf, or .txt file");
      return;
    }
    if (f.size > 10 * 1024 * 1024) {
      toast.error("File size exceeds 10MB limit");
      return;
    }
    setFile(f);
  };

  // Drag and drop handlers
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) validateAndSetFile(f);
  }, []);

  const handleUpload = async () => {
    if (!selectedAppId || !file) {
      toast.error("Select an application and upload a file");
      return;
    }

    setUploading(true);
    setUploadResult(null);

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("applicationId", selectedAppId);

      const res = await fetch("/api/resume/upload", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error || "Upload failed");
      }

      const data: ResumeUploadResult = await res.json();
      setUploadResult(data);
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";

      toast.success(`"${data.upload.fileName}" uploaded and analyzed successfully`);

      // Refresh versions
      fetchVersions(selectedAppId);
      // Refresh parent data (updated scores)
      onRefresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to upload resume");
    } finally {
      setUploading(false);
    }
  };

  const fetchVersions = async (appId: string) => {
    try {
      const res = await fetch(`/api/resume/versions?applicationId=${appId}`);
      if (res.ok) setVersions(await res.json());
    } catch {
      // silently handle
    }
  };

  const handleFetchRecommendations = async () => {
    if (!selectedApp?.personaId) {
      toast.error("No persona associated with this application");
      return;
    }

    setLoadingRecs(true);
    try {
      const res = await fetch("/api/recommendations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          personaId: selectedApp.personaId,
          applicationId: selectedAppId,
        }),
      });

      if (!res.ok) throw new Error("Failed to generate recommendations");
      const data: RecommendationData = await res.json();
      setRecommendations(data);
    } catch {
      toast.error("Failed to generate recommendations");
    } finally {
      setLoadingRecs(false);
    }
  };

  // Load versions when application is selected
  const handleAppChange = (appId: string) => {
    setSelectedAppId(appId);
    setUploadResult(null);
    setRecommendations(null);
    fetchVersions(appId);
  };

  const getScoreColor = (score: number) => {
    if (score >= 70) return "text-emerald-500";
    if (score >= 40) return "text-amber-500";
    return "text-red-500";
  };

  const getScoreBg = (score: number) => {
    if (score >= 70) return "bg-emerald-500";
    if (score >= 40) return "bg-amber-500";
    return "bg-red-500";
  };

  const getPriorityColor = (priority: string) => {
    if (priority === "high") return "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300";
    if (priority === "medium") return "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300";
    return "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400";
  };

  return (
    <div className="space-y-4">
      {/* Upload Section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6">
        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <Upload className="h-4 w-4 text-primary" />
                Upload Resume
              </CardTitle>
              <CardDescription>
                Upload your resume (.docx, .pdf, .txt) to auto-detect skills, check ATS compatibility, and track versions.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label>Select Application</Label>
                <Select value={selectedAppId} onValueChange={handleAppChange}>
                  <SelectTrigger className="h-9 text-sm">
                    <SelectValue placeholder={applications.length === 0 ? "Create an application first" : "Choose an application..."} />
                  </SelectTrigger>
                  <SelectContent>
                    {applications.map((app) => (
                      <SelectItem key={app.id} value={app.id}>
                        {app.company} — {app.roleTitle}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div
                className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-all ${
                  isDragging
                    ? "border-primary bg-primary/5 scale-[1.02]"
                    : file
                    ? "border-primary/50 bg-primary/5"
                    : "hover:border-primary/50 hover:bg-muted/50"
                }`}
                onClick={() => fileInputRef.current?.click()}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
              >
                <input
                  ref={fileInputRef}
                  id="resume-upload"
                  type="file"
                  accept=".docx,.pdf,.txt"
                  className="hidden"
                  onChange={handleFileChange}
                />
                {file ? (
                  <div className="space-y-2">
                    <FileCheck className="h-8 w-8 mx-auto text-primary" />
                    <p className="text-sm font-medium">{file.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {(file.size / 1024).toFixed(1)} KB •{" "}
                      {file.name.split(".").pop()?.toUpperCase()}
                    </p>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-xs"
                      onClick={(e) => {
                        e.stopPropagation();
                        setFile(null);
                        if (fileInputRef.current) fileInputRef.current.value = "";
                      }}
                    >
                      Remove file
                    </Button>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <Upload className="h-8 w-8 mx-auto text-muted-foreground/40" />
                    <p className="text-sm text-muted-foreground">
                      Drop your resume here or click to browse
                    </p>
                    <p className="text-xs text-muted-foreground/70">
                      Supports .docx, .pdf, .txt (max 10MB)
                    </p>
                  </div>
                )}
              </div>

              <Button
                className="w-full"
                onClick={handleUpload}
                disabled={!selectedAppId || !file || uploading}
              >
                {uploading ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Uploading & Analyzing...
                  </>
                ) : (
                  <>
                    <ScanLine className="h-4 w-4 mr-2" />
                    Upload & Analyze
                  </>
                )}
              </Button>

              {uploadResult?.analysis.ocrUsed && (
                <div className="flex items-center gap-2 p-2 bg-amber-50 dark:bg-amber-900/20 rounded-md text-xs text-amber-700 dark:text-amber-300">
                  <AlertTriangle className="h-3 w-3 shrink-0" />
                  OCR was used to extract text (image-based or scanned document detected)
                </div>
              )}
            </CardContent>
          </Card>

          {/* Version History */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <History className="h-4 w-4 text-primary" />
                Version History
              </CardTitle>
            </CardHeader>
            <CardContent>
              {versions.length > 0 ? (
                <div className="space-y-2">
                  {versions.map((v) => (
                    <div key={v.id} className="flex items-center justify-between p-2 rounded-md bg-muted/50 text-sm">
                      <div className="flex items-center gap-2">
                        <FileText className="h-4 w-4 text-muted-foreground" />
                        <span className="font-medium">Version {v.version}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-muted-foreground">
                          {new Date(v.createdAt).toLocaleDateString()}
                        </span>
                        <Badge variant="outline" className="text-[10px]">
                          {v.contentHash}
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-6">
                  <History className="h-8 w-8 mx-auto text-muted-foreground/30 mb-2" />
                  <p className="text-xs text-muted-foreground">
                    {selectedAppId
                      ? "No resume versions yet. Upload a resume to get started."
                      : "Select an application to view version history."}
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Analysis Results Panel */}
        <div className="space-y-4">
          {uploading && (
            <Card>
              <CardContent className="py-16 text-center">
                <div className="space-y-4">
                  <Loader2 className="h-10 w-10 mx-auto text-primary animate-spin" />
                  <div>
                    <p className="text-sm font-medium">Processing Resume</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Extracting text, detecting sections, running ATS analysis...
                    </p>
                  </div>
                  <div className="max-w-xs mx-auto space-y-1">
                    <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                      <div className="h-full bg-primary rounded-full animate-pulse" style={{ width: "70%" }} />
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {!uploading && uploadResult && (
            <Tabs defaultValue="analysis" className="w-full">
              <TabsList className="grid w-full grid-cols-3">
                <TabsTrigger value="analysis" className="text-xs">
                  <ScanLine className="h-3 w-3 mr-1" />
                  Analysis
                </TabsTrigger>
                <TabsTrigger value="skills" className="text-xs">
                  <Brain className="h-3 w-3 mr-1" />
                  Skills
                </TabsTrigger>
                <TabsTrigger value="recommendations" className="text-xs" onClick={handleFetchRecommendations}>
                  <Lightbulb className="h-3 w-3 mr-1" />
                  Tips
                </TabsTrigger>
              </TabsList>

              {/* Analysis Tab */}
              <TabsContent value="analysis" className="space-y-4 mt-4">
                {/* Score Cards */}
                <div className="grid grid-cols-2 gap-3">
                  <Card>
                    <CardContent className="pt-4 pb-4 text-center">
                      <div className={`text-3xl font-bold ${getScoreColor(uploadResult.analysis.atsScore)}`}>
                        {uploadResult.analysis.atsScore}
                      </div>
                      <p className="text-xs text-muted-foreground mt-1">ATS Score</p>
                      <Progress
                        value={uploadResult.analysis.atsScore}
                        className="h-1.5 mt-2"
                      />
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="pt-4 pb-4 text-center">
                      <div className={`text-3xl font-bold ${getScoreColor(uploadResult.analysis.matchScore)}`}>
                        {uploadResult.analysis.matchScore}
                      </div>
                      <p className="text-xs text-muted-foreground mt-1">Match Score</p>
                      <Progress
                        value={uploadResult.analysis.matchScore}
                        className="h-1.5 mt-2"
                      />
                    </CardContent>
                  </Card>
                </div>

                {/* Document Metadata */}
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-semibold">Document Info</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div className="flex justify-between p-1.5 rounded bg-muted/50">
                        <span className="text-muted-foreground">Words</span>
                        <span className="font-medium">{uploadResult.analysis.wordCount}</span>
                      </div>
                      <div className="flex justify-between p-1.5 rounded bg-muted/50">
                        <span className="text-muted-foreground">Sections</span>
                        <span className="font-medium">{uploadResult.analysis.detectedSections.length}</span>
                      </div>
                      <div className="flex justify-between p-1.5 rounded bg-muted/50">
                        <span className="text-muted-foreground">Type</span>
                        <span className="font-medium">{uploadResult.upload.fileType}</span>
                      </div>
                      <div className="flex justify-between p-1.5 rounded bg-muted/50">
                        <span className="text-muted-foreground">Size</span>
                        <span className="font-medium">{(uploadResult.upload.fileSize / 1024).toFixed(1)} KB</span>
                      </div>
                    </div>

                    {/* Detected Sections */}
                    {uploadResult.analysis.detectedSections.length > 0 && (
                      <div className="mt-2">
                        <p className="text-xs text-muted-foreground mb-1">Detected Sections</p>
                        <div className="flex flex-wrap gap-1">
                          {uploadResult.analysis.detectedSections.map((section) => (
                            <Badge key={section} variant="secondary" className="text-[10px] capitalize">
                              {section}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Contact Info */}
                    {Object.keys(uploadResult.analysis.contactInfo).length > 0 && (
                      <div className="mt-2">
                        <p className="text-xs text-muted-foreground mb-1">Detected Contact</p>
                        <div className="space-y-1">
                          {Object.entries(uploadResult.analysis.contactInfo).map(([key, value]) => (
                            <div key={key} className="text-xs p-1.5 rounded bg-muted/50">
                              <span className="text-muted-foreground capitalize">{key}: </span>
                              <span className="font-medium">{value}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* ATS Issues */}
                {uploadResult.analysis.issues.length > 0 && (
                  <Card className="border-amber-200 dark:border-amber-900/50">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-semibold flex items-center gap-2 text-amber-700 dark:text-amber-400">
                        <AlertCircle className="h-3.5 w-3.5" />
                        ATS Issues ({uploadResult.analysis.issues.length})
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-1.5">
                      {uploadResult.analysis.issues.map((issue, i) => (
                        <div key={i} className="flex items-start gap-2 text-xs">
                          <XCircle className="h-3 w-3 text-amber-500 mt-0.5 shrink-0" />
                          <span>{issue}</span>
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                )}
              </TabsContent>

              {/* Skills Tab */}
              <TabsContent value="skills" className="space-y-4 mt-4">
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-semibold flex items-center gap-2">
                      <Target className="h-3.5 w-3.5 text-primary" />
                      Detected Skills ({uploadResult.analysis.detectedSkills.length})
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    {uploadResult.analysis.detectedSkills.length > 0 ? (
                      <div className="flex flex-wrap gap-1.5">
                        {uploadResult.analysis.detectedSkills.map((skill) => (
                          <Badge
                            key={skill}
                            variant="secondary"
                            className="text-xs bg-primary/10 text-primary hover:bg-primary/20"
                          >
                            {skill}
                          </Badge>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-muted-foreground">
                        No specific technical skills detected. Try uploading a more detailed resume.
                      </p>
                    )}
                  </CardContent>
                </Card>

                {/* Match Summary */}
                {selectedApp && (
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm font-semibold">Match Summary</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <div className="flex items-center gap-3">
                        <div className="text-2xl font-bold">
                          {Math.round((selectedApp.matchScore + uploadResult.analysis.matchScore) / 2)}%
                        </div>
                        <div className="text-xs text-muted-foreground">
                          <p>Combined match score</p>
                          <p>Persona + Resume analysis</p>
                        </div>
                      </div>
                      <Separator />
                      {selectedPersona && (
                        <div className="text-xs">
                          <span className="text-muted-foreground">Persona: </span>
                          <span className="font-medium">{selectedPersona.name}</span>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                )}
              </TabsContent>

              {/* Recommendations Tab */}
              <TabsContent value="recommendations" className="space-y-4 mt-4">
                {loadingRecs ? (
                  <Card>
                    <CardContent className="py-12 text-center">
                      <Loader2 className="h-8 w-8 mx-auto text-primary animate-spin mb-3" />
                      <p className="text-sm text-muted-foreground">Generating recommendations...</p>
                    </CardContent>
                  </Card>
                ) : recommendations ? (
                  <>
                    {/* Competitive Positioning */}
                    <Card>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-semibold flex items-center gap-2">
                          <BarChart3 className="h-3.5 w-3.5 text-primary" />
                          Readiness Score
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-3">
                        <div className="flex items-center gap-3">
                          <div className={`text-3xl font-bold ${getScoreColor(recommendations.competitivePositioning.overallReadiness)}`}>
                            {recommendations.competitivePositioning.overallReadiness}%
                          </div>
                          <Progress
                            value={recommendations.competitivePositioning.overallReadiness}
                            className="h-2 flex-1"
                          />
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {recommendations.skillCount} skills identified across your persona
                        </p>
                      </CardContent>
                    </Card>

                    {/* Strengths */}
                    {recommendations.competitivePositioning.strengths.length > 0 && (
                      <Card className="border-emerald-200 dark:border-emerald-900/50">
                        <CardHeader className="pb-2">
                          <CardTitle className="text-sm font-semibold flex items-center gap-2 text-emerald-700 dark:text-emerald-400">
                            <CheckCircle2 className="h-3.5 w-3.5" />
                            Strength Areas
                          </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-2">
                          {recommendations.competitivePositioning.strengths.slice(0, 4).map((s) => (
                            <div key={s.category} className="p-2 rounded bg-emerald-50 dark:bg-emerald-900/20">
                              <div className="flex items-center justify-between mb-1">
                                <span className="text-xs font-medium">{s.category}</span>
                                <Badge variant="outline" className="text-[10px] text-emerald-600 border-emerald-300 dark:text-emerald-400">
                                  {s.level}
                                </Badge>
                              </div>
                              <div className="flex flex-wrap gap-1">
                                {s.skills.slice(0, 5).map((sk) => (
                                  <span key={sk} className="text-[10px] text-emerald-700 dark:text-emerald-300 bg-emerald-100 dark:bg-emerald-900/30 px-1.5 py-0.5 rounded">
                                    {sk}
                                  </span>
                                ))}
                              </div>
                            </div>
                          ))}
                        </CardContent>
                      </Card>
                    )}

                    {/* Top Skill Gaps */}
                    {recommendations.skillGaps.length > 0 && (
                      <Card>
                        <CardHeader className="pb-2">
                          <CardTitle className="text-sm font-semibold flex items-center gap-2">
                            <AlertTriangle className="h-3.5 w-3.5 text-amber-500" />
                            Top Skill Gaps
                          </CardTitle>
                          <CardDescription>High-demand skills missing from your profile</CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-2">
                          {recommendations.skillGaps.slice(0, 8).map((gap) => (
                            <div key={gap.skill} className="flex items-center justify-between p-2 rounded bg-muted/50 text-xs">
                              <div className="flex items-center gap-2">
                                <Badge className={getPriorityColor(gap.priority)}>{gap.priority}</Badge>
                                <span className="font-medium">{gap.skill}</span>
                              </div>
                              <div className="flex items-center gap-2 text-muted-foreground">
                                <span>{gap.estimatedWeeks}w</span>
                                <span>•</span>
                                <span>{gap.marketDemand}% demand</span>
                              </div>
                            </div>
                          ))}
                        </CardContent>
                      </Card>
                    )}

                    {/* Trade Recommendations */}
                    {recommendations.tradeRecommendations.length > 0 && (
                      <Card>
                        <CardHeader className="pb-2">
                          <CardTitle className="text-sm font-semibold flex items-center gap-2">
                            <TrendingUp className="h-3.5 w-3.5 text-primary" />
                            Trade Recommendations
                          </CardTitle>
                          <CardDescription>Role match analysis based on your current skills</CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-3">
                          {recommendations.tradeRecommendations.slice(0, 5).map((rec) => (
                            <div key={rec.targetRole} className="p-3 rounded-lg border space-y-2">
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                  <Briefcase className="h-3.5 w-3.5 text-muted-foreground" />
                                  <span className="text-sm font-medium">{rec.targetRole}</span>
                                </div>
                                <div className={`text-sm font-bold ${getScoreColor(rec.alignmentScore)}`}>
                                  {rec.alignmentScore}%
                                </div>
                              </div>
                              <Progress value={rec.alignmentScore} className="h-1" />
                              <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                                <span>
                                  ${rec.salaryRange.min.toLocaleString()} - ${rec.salaryRange.max.toLocaleString()}
                                </span>
                                <span>{rec.missingSkills.length} skill gaps</span>
                              </div>
                              <p className="text-[10px] text-muted-foreground">{rec.marketOutlook}</p>
                              {rec.actionSteps.length > 0 && (
                                <div className="space-y-0.5">
                                  {rec.actionSteps.slice(0, 2).map((step, i) => (
                                    <div key={i} className="flex items-start gap-1.5 text-[10px]">
                                      <ChevronRight className="h-2.5 w-2.5 text-primary mt-0.5 shrink-0" />
                                      <span>{step}</span>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          ))}
                        </CardContent>
                      </Card>
                    )}

                    {/* ATS Recommendations */}
                    {uploadResult.analysis.recommendations.length > 0 && (
                      <Card>
                        <CardHeader className="pb-2">
                          <CardTitle className="text-sm font-semibold flex items-center gap-2">
                            <Lightbulb className="h-3.5 w-3.5 text-amber-500" />
                            ATS Improvement Tips
                          </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-2">
                          {uploadResult.analysis.recommendations.map((rec, i) => (
                            <div key={i} className="flex items-start gap-2 text-xs p-2 rounded bg-amber-50 dark:bg-amber-900/20">
                              <Sparkles className="h-3 w-3 text-amber-500 mt-0.5 shrink-0" />
                              <span>{rec}</span>
                            </div>
                          ))}
                        </CardContent>
                      </Card>
                    )}

                    {/* Pipeline Telemetry */}
                    <Card>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-semibold flex items-center gap-2">
                          <Zap className="h-3.5 w-3.5 text-primary" />
                          Pipeline Telemetry
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="grid grid-cols-3 gap-2 text-center">
                          <div className="p-2 rounded bg-muted/50">
                            <div className="text-lg font-bold">{recommendations.pipelineTelemetry.totalApplications}</div>
                            <p className="text-[10px] text-muted-foreground">Applications</p>
                          </div>
                          <div className="p-2 rounded bg-muted/50">
                            <div className="text-lg font-bold">{recommendations.pipelineTelemetry.averageMatchScore}%</div>
                            <p className="text-[10px] text-muted-foreground">Avg Match</p>
                          </div>
                          <div className="p-2 rounded bg-muted/50">
                            <div className="text-lg font-bold text-emerald-600">{recommendations.pipelineTelemetry.highMatchCount}</div>
                            <p className="text-[10px] text-muted-foreground">High Match</p>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  </>
                ) : (
                  <Card>
                    <CardContent className="py-8 text-center">
                      <Brain className="h-8 w-8 mx-auto text-muted-foreground/30 mb-3" />
                      <p className="text-sm text-muted-foreground">
                        Click &quot;Tips&quot; to generate personalized recommendations
                      </p>
                    </CardContent>
                  </Card>
                )}
              </TabsContent>
            </Tabs>
          )}

          {!uploading && !uploadResult && selectedApp && (
            <Card>
              <CardContent className="py-12 text-center">
                <div className="space-y-3">
                  <ScanLine className="h-10 w-10 mx-auto text-muted-foreground/30" />
                  <div>
                    <p className="text-sm font-medium">Ready to Analyze</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Upload a resume to see ATS scoring, skill detection, and personalized recommendations.
                    </p>
                  </div>
                  <div className="flex items-center justify-center gap-4 text-[10px] text-muted-foreground">
                    <div className="flex items-center gap-1"><Shield className="h-3 w-3" /> ATS Check</div>
                    <div className="flex items-center gap-1"><Brain className="h-3 w-3" /> Skill Detection</div>
                    <div className="flex items-center gap-1"><Eye className="h-3 w-3" /> OCR Support</div>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {!uploading && !uploadResult && !selectedApp && (
            <Card>
              <CardContent className="py-12 text-center">
                <FileText className="h-10 w-10 mx-auto text-muted-foreground/30 mb-3" />
                <p className="text-sm text-muted-foreground">
                  Select an application to begin resume analysis.
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
