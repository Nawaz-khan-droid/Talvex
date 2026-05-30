const STOP_WORDS = new Set([
  "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "can",
  "could", "did", "do", "does", "doing", "don", "down", "during", "each",
  "few", "for", "from", "further", "get", "got", "had", "has", "have",
  "having", "he", "her", "here", "hers", "herself", "him", "himself",
  "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself",
  "just", "ll", "m", "ma", "me", "might", "more", "most", "must", "my",
  "myself", "need", "no", "nor", "not", "now", "of", "off", "on", "once",
  "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own",
  "per", "re", "s", "same", "she", "should", "so", "some", "such", "t",
  "than", "that", "the", "their", "theirs", "them", "themselves", "then",
  "there", "these", "they", "this", "those", "through", "to", "too", "under",
  "until", "up", "us", "ve", "very", "was", "we", "were", "what", "when",
  "where", "which", "while", "who", "whom", "why", "will", "with", "would",
  "you", "your", "yours", "yourself", "yourselves", "also", "about", "above",
  "after", "again", "all", "am", "any", "because", "before", "below",
  "between", "both", "dear", "did", "either", "else", "ever", "every",
  "go", "going", "gone", "good", "great", "has", "hello", "help", "high",
  "however", "keep", "know", "last", "like", "long", "look", "make",
  "many", "may", "much", "must", "name", "never", "new", "next", "one",
  "only", "part", "people", "put", "right", "said", "say", "see", "set",
  "show", "since", "something", "still", "take", "tell", "thing", "think",
  "three", "time", "turn", "two", "use", "used", "using", "want", "way",
  "well", "went", "come", "day", "even", "give", "find", "here", "just",
  "let", "live", "look", "man", "need", "number", "old", "place", "point",
  "right", "small", "sound", "spell", "still", "study", "their", "there",
  "these", "they", "thing", "think", "those", "thought", "through",
  "under", "upon", "water", "where", "which", "while", "word", "work",
  "world", "would", "write", "year", "ability", "able", "across",
  "actually", "addition", "allow", "along", "already", "although",
  "always", "amount", "another", "apply", "around", "away", "best",
  "better", "big", "bring", "build", "call", "case", "certain", "change",
  "child", "city", "clear", "close", "consider", "continue", "course",
  "cover", "cross", "different", "early", "effect", "end", "enough",
  "example", "experience", "face", "family", "far", "field", "first",
  "free", "full", "game", "general", "group", "growth", "hand", "hard",
  "head", "health", "hold", "home", "hope", "human", "important",
  "include", "including", "information", "inside", "instead", "interest",
  "job", "join", "keep", "kind", "large", "late", "learn", "leave",
  "level", "light", "line", "list", "local", "lost", "love", "main",
  "major", "market", "matter", "member", "million", "mind", "model",
  "money", "month", "moral", "move", "music", "nature", "night",
  "nothing", "often", "open", "order", "others", "outside", "over",
  "own", "page", "paper", "plan", "play", "point", "power", "present",
  "problem", "program", "provide", "public", "question", "quite",
  "rather", "reach", "read", "real", "reason", "receive", "remember",
  "report", "result", "return", "room", "run", "school", "second",
  "seem", "send", "serve", "service", "side", "simple", "sit",
  "society", "sort", "special", "stand", "start", "state", "stay",
  "step", "stop", "story", "student", "such", "sure", "system",
  "talk", "team", "together", "total", "town", "tree", "true",
  "understand", "union", "united", "until", "value", "video", "visit",
  "wait", "walk", "wall", "watch", "west", "whether", "without",
  "woman", "women", "young",
]);

// ============================================================
// Phrase Extraction
// ============================================================

function extractPhrases(text: string, n: number): string[] {
  const cleaned = text
    .toLowerCase()
    .replace(/[^a-z0-9+#.\-\/\s]/g, " ")
    .split(/\s+/)
    .filter((w) => w.length > 1);

  const phrases = new Set<string>();
  for (let i = 0; i <= cleaned.length - n; i++) {
    const chunk = cleaned.slice(i, i + n);
    const nonStop = chunk.filter((w) => !STOP_WORDS.has(w));
    if (nonStop.length > 0) {
      phrases.add(chunk.join(" "));
    }
  }
  return [...phrases].sort();
}

function extractKeyPhrases(text: string): string[] {
  const p2 = extractPhrases(text, 2);
  const p3 = extractPhrases(text, 3);
  return [...new Set([...p2, ...p3])].sort();
}

// ============================================================
// Section Detection
// ============================================================

const RESUME_SECTIONS = [
  "experience", "education", "skills", "summary", "objective",
  "projects", "certifications", "contact", "references",
  "languages", "achievements", "professional experience",
  "work experience", "technical skills", "education background",
  "personal projects", "professional summary", "career objective",
  "publications", "volunteer", "honors", "awards", "training",
  "professional development", "additional information",
];

function detectSections(text: string): string[] {
  const lower = text.toLowerCase();
  return RESUME_SECTIONS.filter((section) => lower.includes(section)).sort();
}

// ============================================================
// Core Extraction (unchanged API)
// ============================================================

function extractKeywords(text: string): string[] {
  const words = text
    .toLowerCase()
    .replace(/[^a-z0-9+#.\-\/\s]/g, " ")
    .split(/\s+/)
    .filter((w) => w.length > 1 && !STOP_WORDS.has(w));

  const unique = [...new Set(words)];
  return unique.sort();
}

function calculateMatchScore(
  jobDescription: string,
  personaSkills: string[]
): {
  score: number;
  matched: string[];
  missing: string[];
} {
  const jdKeywords = extractKeywords(jobDescription);
  const skills = personaSkills.map((s) => s.toLowerCase().trim()).filter(Boolean);

  if (jdKeywords.length === 0) {
    return { score: 0, matched: [], missing: [] };
  }

  const skillSet = new Set(skills);
  const jdSet = new Set(jdKeywords);

  const matched: string[] = [];
  const missing: string[] = [];

  for (const keyword of jdKeywords) {
    let isMatch = false;
    for (const skill of skills) {
      if (keyword === skill || keyword.includes(skill) || skill.includes(keyword)) {
        isMatch = true;
        break;
      }
    }
    if (isMatch) {
      matched.push(keyword);
    } else {
      missing.push(keyword);
    }
  }

  const skillsNotInJd = skills.filter((s) => !jdSet.has(s) && !jdKeywords.some((k) => k.includes(s) || s.includes(k)));

  const score = Math.min(100, Math.round((matched.length / Math.max(1, jdKeywords.length)) * 100));

  return { score, matched: [...new Set(matched)], missing: [...new Set(missing)].slice(0, 20) };
}

// ============================================================
// ATS Score (enhanced, backward-compatible)
// ============================================================

function calculateATSScore(resumeText: string, jobDescription?: string): number {
  let score = 0;

  const standardHeaders = [
    "experience", "education", "skills", "summary",
    "objective", "projects", "certifications", "contact",
    "references", "languages", "achievements",
  ];
  const lower = resumeText.toLowerCase();

  for (const header of standardHeaders) {
    if (lower.includes(header)) {
      score += 2;
    }
  }
  if (score > 30) score = 30;

  if (!lower.includes("table") && !lower.includes("column")) {
    score += 20;
  }

  const words = lower.split(/\s+/).filter(Boolean);
  if (words.length > 100) {
    score += 10;
  }
  if (words.length > 200) {
    score += 5;
  }
  if (score > 35) score = 35;

  const sentences = resumeText.split(/[.!?]+/).filter((s) => s.trim().length > 0);
  if (sentences.length > 5) {
    score += 10;
  }
  if (sentences.length > 10) {
    score += 5;
  }

  const bulletPoints = (resumeText.match(/[-•*]/g) || []).length;
  if (bulletPoints > 3) {
    score += 10;
  }
  if (bulletPoints > 8) {
    score += 5;
  }

  const hasNumbers = /\d+/.test(resumeText);
  if (hasNumbers) score += 5;

  // JD-aware bonus (only when JD provided)
  if (jobDescription) {
    const detected = detectSections(resumeText);
    const sectionBonus = Math.min(10, detected.length * 2);
    score += sectionBonus;

    const resumeKw = new Set(extractKeywords(resumeText));
    const jdKw = new Set(extractKeywords(jobDescription));
    if (jdKw.size > 0) {
      const overlap = [...resumeKw].filter((k) => jdKw.has(k));
      const kwPct = overlap.length / jdKw.size;
      score += Math.min(10, Math.round(kwPct * 10));
    }

    const resumePhr = new Set(extractKeyPhrases(resumeText));
    const jdPhr = new Set(extractKeyPhrases(jobDescription));
    if (jdPhr.size > 0) {
      const phrOverlap = [...resumePhr].filter((p) => jdPhr.has(p));
      const phrPct = phrOverlap.length / jdPhr.size;
      score += Math.min(5, Math.round(phrPct * 5));
    }
  }

  return Math.min(100, score);
}

// ============================================================
// Enhanced Match Score (new API)
// ============================================================

export interface EnhancedMatchReport {
  keywordMatchPct: number;
  phraseMatchPct: number;
  sectionBonus: number;
  overallScore: number;
  matchedKeywords: string[];
  matchedPhrases: string[];
  missingKeywords: string[];
  missingPhrases: string[];
  detectedSections: string[];
  recommendations: string[];
}

function prioritizeKeywords(missingKeywords: Set<string>, jdText: string): string[] {
  const jdLower = jdText.toLowerCase();
  const TECHNICAL_SKILLS_SET = new Set([
    "python", "javascript", "typescript", "java", "go", "rust", "c++", "c#",
    "react", "angular", "vue.js", "node.js", "docker", "kubernetes",
    "aws", "azure", "gcp", "machine learning", "deep learning",
    "tensorflow", "pytorch", "pandas", "numpy", "power bi", "tableau",
    "excel", "sql", "data analysis", "spark", "llm", "fastapi", "django",
    "flask", "postgresql", "mongodb", "redis", "elasticsearch",
    "terraform", "ansible", "jenkins", "git", "linux", "kafka",
  ]);

  const scored: [string, number][] = [];
  for (const kw of missingKeywords) {
    let priority = 0;
    priority += Math.min((jdLower.match(new RegExp(kw.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "g")) || []).length, 5);
    if (TECHNICAL_SKILLS_SET.has(kw)) priority += 10;
    priority += Math.min(kw.length, 5);
    scored.push([kw, priority]);
  }

  scored.sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  return scored.map(([kw]) => kw);
}

function generateRecommendations(
  overallScore: number,
  keywordPct: number,
  phrasePct: number,
  sections: string[],
  missingCount: number,
): string[] {
  const recs: string[] = [];

  if (overallScore >= 80) {
    recs.push("Excellent match! Your resume aligns strongly with this job description.");
  } else if (overallScore >= 60) {
    recs.push("Good match overall. A few targeted improvements could push this higher.");
  } else if (overallScore >= 40) {
    recs.push("Fair match. Consider adding relevant keywords and phrases from the JD to strengthen alignment.");
  } else {
    recs.push("Low match score. Significant gaps exist between your resume and the job requirements.");
  }

  if (keywordPct < 50) {
    recs.push("Add more technical keywords from the job description to improve ATS keyword matching.");
  }

  if (phrasePct < 40) {
    recs.push("Include key phrases (e.g., 'data analysis', 'machine learning') exactly as they appear in the JD.");
  }

  const essential = ["experience", "education", "skills"];
  for (const section of essential) {
    if (!sections.includes(section)) {
      recs.push(`Add a clear '${section.charAt(0).toUpperCase() + section.slice(1)}' section to your resume for better ATS parsing.`);
    }
  }

  if (sections.length < 4) {
    recs.push("Consider adding more standard sections (Projects, Certifications, Summary) to improve structure score.");
  }

  if (missingCount > 10) {
    recs.push(`There are ${missingCount} keywords missing from your resume. Focus on the top 5-7 most relevant ones first.`);
  } else if (missingCount > 0) {
    recs.push("A few targeted keywords are missing. Adding them could improve your match score.");
  }

  if (keywordPct > phrasePct + 25) {
    recs.push("Your resume has good keyword coverage but low phrase matching. Try using the exact phrases from the JD.");
  }

  return recs;
}

function calculateMatchScoreEnhanced(
  resumeText: string,
  jdText: string,
): EnhancedMatchReport {
  // Keyword matching
  const resumeKw = new Set(extractKeywords(resumeText));
  const jdKw = new Set(extractKeywords(jdText));

  if (jdKw.size === 0) {
    return {
      keywordMatchPct: 0,
      phraseMatchPct: 0,
      sectionBonus: 0,
      overallScore: 0,
      matchedKeywords: [],
      matchedPhrases: [],
      missingKeywords: [],
      missingPhrases: [],
      detectedSections: [],
      recommendations: ["Job description is too short or empty. Please provide a more detailed JD."],
    };
  }

  const matchedKw = [...resumeKw].filter((k) => jdKw.has(k)).sort();
  const missingKwSet = [...jdKw].filter((k) => !resumeKw.has(k));
  const keywordPct = Math.round((matchedKw.length / jdKw.size) * 100);

  // Phrase matching
  const resumePhr = new Set(extractKeyPhrases(resumeText));
  const jdPhr = new Set(extractKeyPhrases(jdText));

  let matchedPhr: string[] = [];
  let missingPhr: string[] = [];
  let phrasePct = 0;

  if (jdPhr.size > 0) {
    matchedPhr = [...resumePhr].filter((p) => jdPhr.has(p)).sort();
    missingPhr = [...jdPhr].filter((p) => !resumePhr.has(p)).sort().slice(0, 10);
    phrasePct = Math.round((matchedPhr.length / jdPhr.size) * 100);
  }

  // Section bonus
  const sections = detectSections(resumeText);
  const sectionBonus = Math.min(10, sections.length * 2);

  // Weighted overall
  const baseScore = Math.round(keywordPct * 0.6 + phrasePct * 0.4);
  const overallScore = Math.min(100, baseScore + sectionBonus);

  // Prioritized missing keywords (top 15)
  const missingKwSorted = prioritizeKeywords(new Set(missingKwSet), jdText).slice(0, 15);

  // Recommendations
  const recommendations = generateRecommendations(
    overallScore, keywordPct, phrasePct, sections, missingKwSorted.length,
  );

  return {
    keywordMatchPct: keywordPct,
    phraseMatchPct: phrasePct,
    sectionBonus,
    overallScore,
    matchedKeywords: matchedKw,
    matchedPhrases: matchedPhr,
    missingKeywords: missingKwSorted,
    missingPhrases: missingPhr,
    detectedSections: sections,
    recommendations,
  };
}

// ============================================================
// Public API (backward-compatible)
// ============================================================

export function analyzeJobDescription(
  jobDescription: string,
  personaSkills: string[]
) {
  const { score, matched, missing } = calculateMatchScore(jobDescription, personaSkills);
  const atsScore = calculateATSScore(jobDescription);

  return {
    matchScore: score,
    matchedKeywords: matched,
    missingKeywords: missing,
    atsScore,
  };
}

export function extractKeywordsFromText(text: string): string[] {
  return extractKeywords(text);
}

export { calculateATSScore, calculateMatchScoreEnhanced, extractKeyPhrases, detectSections };
export type { EnhancedMatchReport };
