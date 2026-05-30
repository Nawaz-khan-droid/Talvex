"""
TALVEX Resume Customizer Service
Generates customized .docx resumes from templates using persona and job data.
Uses python-docx for template manipulation.
"""

import io
import logging
import os
import uuid
from pathlib import Path
from typing import Any

from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

logger = logging.getLogger(__name__)

# Template storage (relative paths for Docker compatibility)
TEMPLATES_DIR = str(Path(__file__).resolve().parent.parent / "templates")
CUSTOM_TEMPLATES_DIR = str(Path(__file__).resolve().parent.parent / "templates" / "custom")


class ResumeCustomizer:
    """Service for customizing resume .docx templates with persona and job data."""

    def __init__(self):
        os.makedirs(TEMPLATES_DIR, exist_ok=True)
        os.makedirs(CUSTOM_TEMPLATES_DIR, exist_ok=True)
        self._ensure_default_template()

    def _ensure_default_template(self):
        """Create default resume template if it doesn't exist."""
        default_path = os.path.join(TEMPLATES_DIR, "default_resume.docx")
        if os.path.exists(default_path):
            return

        doc = Document()

        # Set default font
        style = doc.styles['Normal']
        font = style.font
        font.name = 'Calibri'
        font.size = Pt(11)
        font.color.rgb = RGBColor(0x33, 0x33, 0x33)

        # Set narrow margins
        for section in doc.sections:
            section.top_margin = Inches(0.5)
            section.bottom_margin = Inches(0.5)
            section.left_margin = Inches(0.7)
            section.right_margin = Inches(0.7)

        # Name placeholder
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run("[NAME]")
        run.bold = True
        run.font.size = Pt(22)
        run.font.color.rgb = RGBColor(0x2D, 0x2D, 0x2D)

        # Contact info placeholder
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run("[EMAIL] | [PHONE] | [LINKEDIN]")
        run.font.size = Pt(10)
        run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

        # Divider line
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run("─" * 80)
        run.font.size = Pt(8)
        run.font.color.rgb = RGBColor(0xBB, 0xBB, 0xBB)

        # Professional Summary
        h = doc.add_heading("Professional Summary", level=1)
        for run in h.runs:
            run.font.color.rgb = RGBColor(0x2D, 0x2D, 0x2D)
            run.font.size = Pt(14)
        doc.add_paragraph("[PROFESSIONAL SUMMARY]")

        # Technical Skills
        h = doc.add_heading("Technical Skills", level=1)
        for run in h.runs:
            run.font.color.rgb = RGBColor(0x2D, 0x2D, 0x2D)
            run.font.size = Pt(14)
        doc.add_paragraph("[SKILLS]")

        # Experience
        h = doc.add_heading("Professional Experience", level=1)
        for run in h.runs:
            run.font.color.rgb = RGBColor(0x2D, 0x2D, 0x2D)
            run.font.size = Pt(14)

        # Add 2 experience entry placeholders
        for i in range(2):
            p = doc.add_paragraph()
            run = p.add_run(f"[JOB TITLE] — [COMPANY]")
            run.bold = True
            run.font.size = Pt(12)

            p = doc.add_paragraph()
            run = p.add_run("[DATES]")
            run.font.size = Pt(10)
            run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
            run.italic = True

            for _ in range(3):
                doc.add_paragraph("[BULLET POINT]", style='List Bullet')

            # Spacer
            doc.add_paragraph("")

        # Education
        h = doc.add_heading("Education", level=1)
        for run in h.runs:
            run.font.color.rgb = RGBColor(0x2D, 0x2D, 0x2D)
            run.font.size = Pt(14)
        doc.add_paragraph("[EDUCATION]")

        # Certifications
        h = doc.add_heading("Certifications", level=1)
        for run in h.runs:
            run.font.color.rgb = RGBColor(0x2D, 0x2D, 0x2D)
            run.font.size = Pt(14)
        doc.add_paragraph("[CERTIFICATIONS]")

        doc.save(default_path)
        logger.info(f"Default resume template created at {default_path}")

    def customize_resume(
        self,
        template_path: str | None,
        persona_data: dict[str, Any],
        job_data: dict[str, Any],
    ) -> bytes:
        """
        Take a .docx template (or default), fill in persona-specific content,
        inject job-matched keywords. Returns the customized .docx file as bytes.

        persona_data: {
            "name": "...",
            "email": "...",
            "phone": "...",
            "linkedin": "...",
            "summary": "...",
            "skills": ["Python", "React", ...],
            "experience": [{"title": "...", "company": "...", "bullets": ["..."], "dates": "..."}],
            "education": [{"degree": "...", "institution": "...", "dates": "..."}],
            "certifications": ["..."]
        }
        job_data: {
            "title": "...",
            "company": "...",
            "required_skills": ["Python", "AWS", ...],
            "description": "..."
        }
        """
        if not template_path or not os.path.exists(template_path):
            template_path = os.path.join(TEMPLATES_DIR, "default_resume.docx")

        doc = Document(template_path)

        # Build replacement map
        replacements = self._build_replacements(persona_data, job_data)

        # Replace placeholders in all paragraphs
        for paragraph in doc.paragraphs:
            self._replace_in_paragraph(paragraph, replacements)

        # Replace in tables too
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        self._replace_in_paragraph(paragraph, replacements)

        # If the template had placeholder sections, rebuild the experience section
        self._rebuild_experience_section(doc, persona_data)
        self._rebuild_education_section(doc, persona_data)
        self._rebuild_certifications_section(doc, persona_data)

        # Save to bytes
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()

    def _build_replacements(
        self, persona_data: dict[str, Any], job_data: dict[str, Any]
    ) -> dict[str, str]:
        """Build a map of placeholder -> replacement text."""
        replacements = {
            "[NAME]": persona_data.get("name", ""),
            "[EMAIL]": persona_data.get("email", ""),
            "[PHONE]": persona_data.get("phone", ""),
            "[LINKEDIN]": persona_data.get("linkedin", ""),
            "[PROFESSIONAL SUMMARY]": persona_data.get("summary", ""),
            "[SKILLS]": self._format_skills(persona_data.get("skills", []), job_data.get("required_skills", [])),
            "[EDUCATION]": self._format_education(persona_data.get("education", [])),
            "[CERTIFICATIONS]": self._format_certifications(persona_data.get("certifications", [])),
            "[JOB TITLE]": persona_data.get("experience", [{}])[0].get("title", "") if persona_data.get("experience") else "",
            "[COMPANY]": persona_data.get("experience", [{}])[0].get("company", "") if persona_data.get("experience") else "",
            "[DATES]": persona_data.get("experience", [{}])[0].get("dates", "") if persona_data.get("experience") else "",
            "[BULLET POINT]": "",
        }
        return {k: v for k, v in replacements.items() if v}

    def _format_skills(
        self, persona_skills: list[str], required_skills: list[str] | None
    ) -> str:
        """Format skills list, prioritizing job-matched skills."""
        if not persona_skills:
            return ""

        # Deduplicate
        all_skills = list(dict.fromkeys(persona_skills))

        # Prioritize skills that match job requirements
        if required_skills:
            matched = [s for s in all_skills if s.lower() in [r.lower() for r in required_skills]]
            unmatched = [s for s in all_skills if s.lower() not in [r.lower() for r in required_skills]]
            all_skills = matched + unmatched

        # Categorize
        categories = {
            "Languages": ["python", "java", "javascript", "typescript", "go", "rust", "c++", "c#", "ruby", "php", "swift", "kotlin", "scala"],
            "Frameworks": ["react", "angular", "vue", "django", "flask", "spring", "fastapi", "next.js", "nuxt", "express", "rails", "laravel"],
            "Databases": ["sql", "mysql", "postgresql", "mongodb", "redis", "elasticsearch", "sqlite", "oracle", "dynamodb"],
            "Cloud & DevOps": ["aws", "azure", "gcp", "docker", "kubernetes", "terraform", "ansible", "jenkins", "ci/cd", "linux"],
            "Tools & Other": ["git", "github", "jira", "figma", "agile", "scrum", "rest api", "graphql", "tableau", "power bi"],
        }

        categorized: dict[str, list[str]] = {}
        uncategorized = []

        for skill in all_skills:
            skill_lower = skill.lower()
            found = False
            for cat, keywords in categories.items():
                if skill_lower in keywords or any(kw in skill_lower for kw in keywords if len(kw) > 3):
                    categorized.setdefault(cat, []).append(skill)
                    found = True
                    break
            if not found:
                uncategorized.append(skill)

        lines = []
        for cat in ["Languages", "Frameworks", "Databases", "Cloud & DevOps", "Tools & Other"]:
            if cat in categorized:
                lines.append(f"{cat}: {', '.join(categorized[cat])}")
        if uncategorized:
            lines.append(f"Other: {', '.join(uncategorized)}")

        return "  |  ".join(lines)

    def _format_education(self, education: list[dict] | None) -> str:
        """Format education entries."""
        if not education:
            return "Education details not provided."

        lines = []
        for edu in education:
            degree = edu.get("degree", "")
            institution = edu.get("institution", "")
            dates = edu.get("dates", "")
            line = f"{degree}"
            if institution:
                line += f" — {institution}"
            if dates:
                line += f" ({dates})"
            lines.append(line)

        return "\n".join(lines) if lines else "Education details not provided."

    def _format_certifications(self, certifications: list[str] | None) -> str:
        """Format certifications list."""
        if not certifications:
            return ""
        return "  •  ".join(certifications)

    def _replace_in_paragraph(self, paragraph, replacements: dict[str, str]):
        """Replace placeholders in a paragraph's runs."""
        full_text = paragraph.text
        for placeholder, replacement in replacements.items():
            if placeholder in full_text:
                # Simple approach: replace in the full paragraph text
                for run in paragraph.runs:
                    if placeholder in run.text:
                        run.text = run.text.replace(placeholder, replacement)
                        break
                else:
                    # Placeholder spans multiple runs, replace in first run and clear others
                    if paragraph.runs and placeholder in paragraph.text:
                        paragraph.runs[0].text = paragraph.text.replace(placeholder, replacement)
                        for run in paragraph.runs[1:]:
                            if placeholder in run.text:
                                run.text = ""

    def _rebuild_experience_section(self, doc: Document, persona_data: dict[str, Any]):
        """Rebuild the experience section with actual persona data."""
        experience = persona_data.get("experience", [])
        if not experience:
            return

        # Find the Experience heading and clear everything after it until the next heading
        heading_idx = None
        next_heading_idx = len(doc.paragraphs)

        for i, para in enumerate(doc.paragraphs):
            if para.style.name.startswith("Heading") and "experience" in para.text.lower():
                heading_idx = i
            elif heading_idx is not None and para.style.name.startswith("Heading"):
                next_heading_idx = i
                break

        if heading_idx is None:
            return

        # We need to be careful here. Instead of deleting paragraphs (which is complex in python-docx),
        # we'll replace the placeholder content in existing paragraphs
        exp_idx = 0
        for i in range(heading_idx + 1, min(next_heading_idx, heading_idx + 1 + len(experience) * 6)):
            para = doc.paragraphs[i]
            if exp_idx < len(experience):
                exp = experience[exp_idx]

                # Title line
                if "[JOB TITLE]" in para.text or "[COMPANY]" in para.text:
                    title = exp.get("title", "")
                    company = exp.get("company", "")
                    para.clear()
                    run = para.add_run(f"{title} — {company}")
                    run.bold = True
                    run.font.size = Pt(12)
                    continue

                # Dates line
                if "[DATES]" in para.text:
                    dates = exp.get("dates", "")
                    para.clear()
                    run = para.add_run(dates)
                    run.font.size = Pt(10)
                    run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
                    run.italic = True
                    continue

                # Bullet points
                if "[BULLET POINT]" in para.text:
                    bullets = exp.get("bullets", [])
                    para.clear()
                    if bullets:
                        # Find which bullet we're on
                        para_idx = i - (heading_idx + 1)
                        bullet_num = para_idx % 5  # Approximate
                        if bullet_num < len(bullets):
                            para.text = bullets[bullet_num]
                    continue

                # Move to next experience entry (empty line separator)
                if para.text.strip() == "" and i > heading_idx + 4:
                    exp_idx += 1

    def _rebuild_education_section(self, doc: Document, persona_data: dict[str, Any]):
        """Rebuild education section."""
        education = persona_data.get("education", [])
        if not education:
            return

        heading_idx = None
        for i, para in enumerate(doc.paragraphs):
            if para.style.name.startswith("Heading") and "education" in para.text.lower():
                heading_idx = i
                break

        if heading_idx is None:
            return

        # Replace the education placeholder paragraph
        if heading_idx + 1 < len(doc.paragraphs):
            edu_para = doc.paragraphs[heading_idx + 1]
            if "[EDUCATION]" in edu_para.text or not education:
                edu_para.clear()
                for edu in education:
                    degree = edu.get("degree", "")
                    institution = edu.get("institution", "")
                    dates = edu.get("dates", "")
                    run = edu_para.add_run(f"{degree}")
                    run.bold = True
                    if institution:
                        run = edu_para.add_run(f" — {institution}")
                    if dates:
                        run = edu_para.add_run(f" ({dates})")
                    run = edu_para.add_run("\n")

    def _rebuild_certifications_section(self, doc: Document, persona_data: dict[str, Any]):
        """Rebuild certifications section."""
        certs = persona_data.get("certifications", [])
        if not certs:
            return

        heading_idx = None
        for i, para in enumerate(doc.paragraphs):
            if para.style.name.startswith("Heading") and "certification" in para.text.lower():
                heading_idx = i
                break

        if heading_idx is None:
            return

        if heading_idx + 1 < len(doc.paragraphs):
            cert_para = doc.paragraphs[heading_idx + 1]
            cert_para.clear()
            for cert in certs:
                run = cert_para.add_run(f"• {cert}\n")

    def save_custom_template(self, file_bytes: bytes, template_name: str | None = None) -> str:
        """Save a custom .docx template. Returns the file path."""
        name = template_name or f"template_{uuid.uuid4().hex[:8]}"
        if not name.endswith(".docx"):
            name += ".docx"
        path = os.path.join(CUSTOM_TEMPLATES_DIR, name)

        with open(path, "wb") as f:
            f.write(file_bytes)

        logger.info(f"Custom template saved at {path}")
        return path

    def list_templates(self) -> list[dict[str, str]]:
        """List all available templates."""
        templates = []

        # Default template
        default_path = os.path.join(TEMPLATES_DIR, "default_resume.docx")
        if os.path.exists(default_path):
            templates.append({
                "name": "Default Resume",
                "path": default_path,
                "type": "default",
            })

        # Custom templates
        if os.path.exists(CUSTOM_TEMPLATES_DIR):
            for fname in sorted(os.listdir(CUSTOM_TEMPLATES_DIR)):
                if fname.endswith(".docx"):
                    fpath = os.path.join(CUSTOM_TEMPLATES_DIR, fname)
                    templates.append({
                        "name": fname.replace(".docx", "").replace("_", " ").title(),
                        "path": fpath,
                        "type": "custom",
                    })

        return templates


# Singleton instance
resume_customizer = ResumeCustomizer()
