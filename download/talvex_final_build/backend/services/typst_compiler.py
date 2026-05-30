"""
TALVEX Typst Compiler Service

Converts HTML resumes to Typst markup and compiles them to PDF.
Provides graceful fallback when the Typst CLI is not installed.

Public API:
    - html_to_typst(html, template_type) -> str
    - compile_typst(typst_source, output_path) -> bytes
    - is_typst_available() -> bool
    - html_to_pdf(html, template_type, output_path) -> bytes | None
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "typst"

# ---------------------------------------------------------------------------
# Typst CLI detection
# ---------------------------------------------------------------------------

_TYPST_BIN: Optional[str] = None


def _detect_typst() -> Optional[str]:
    """Locate the Typst CLI binary. Returns path or None."""
    global _TYPST_BIN
    if _TYPST_BIN is not None:
        return _TYPST_BIN

    for candidate in ("typst", "/usr/local/bin/typst"):
        path = shutil.which(candidate)
        if path:
            _TYPST_BIN = path
            return _TYPST_BIN

    _TYPST_BIN = ""  # sentinel: already checked, not found
    return None


def is_typst_available() -> bool:
    """Return True if the Typst CLI is available on the system."""
    return _detect_typst() is not None


# ---------------------------------------------------------------------------
# HTML -> structured text extraction
# ---------------------------------------------------------------------------

class _ResumeHTMLParser(HTMLParser):
    """
    Extract structured content blocks from a rendered TALVEX HTML resume.
    Identifies sections by their CSS classes and produces clean text blocks.
    """

    def __init__(self) -> None:
        super().__init__()
        self.blocks: dict[str, str] = {
            "full_name": "",
            "email": "",
            "phone": "",
            "location": "",
            "linkedin": "",
            "portfolio": "",
            "professional_summary": "",
            "work_experience_html": "",  # kept as HTML for structured parsing
            "skills_section_html": "",   # kept as HTML for structured parsing
            "education_html": "",        # kept as HTML for structured parsing
        }
        self._current_section: str = ""
        self._in_header = False
        self._in_contact = False
        self._section_stack: list[str] = []  # track nested elements
        self._text_parts: list[str] = []
        self._skip = False
        self._contact_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = ""
        for name, value in attrs:
            if name == "class":
                classes = value or ""
                break

        if tag in ("script", "style"):
            self._skip = True
            return

        # Header detection
        if "resume-header" in classes:
            self._in_header = True

        # Name
        if tag == "h1" and self._in_header:
            self._current_section = "full_name"
            self._text_parts = []

        # Contact info
        if "contact-info" in classes:
            self._in_contact = True
            self._contact_parts = []

        # Professional summary
        if "summary-text" in classes:
            self._current_section = "professional_summary"
            self._text_parts = []

        # Work experience section
        if "job-entry" in classes:
            self._current_section = "work"
            self._text_parts = []
            self._section_stack.append(tag)

        # Job title/company/date/location
        if "job-title" in classes and self._current_section == "work":
            self._text_parts.append("\n<<TITLE>>")
        if "job-company" in classes and self._current_section == "work":
            self._text_parts.append("<<COMPANY_START>>")
        if "job-date" in classes and self._current_section == "work":
            self._text_parts.append("<<DATE_START>>")
        if "job-location" in classes and self._current_section == "work":
            self._text_parts.append("\n<<LOCATION_START>>")

        # Skills subsections
        if "skills-subsection" in classes:
            self._current_section = "skills"
            self._text_parts = []

        if "skills-subsection-title" in classes and self._current_section == "skills":
            self._text_parts.append("\n<<SKILL_CAT>>")

        if "skills-list" in classes:
            self._section_stack.append("skills-list")

        # Education entries
        if "edu-entry" in classes:
            self._current_section = "education"
            self._text_parts = []
            self._section_stack.append(tag)

        if "edu-degree" in classes and self._current_section == "education":
            self._text_parts.append("\n<<DEGREE>>")
        if "edu-school" in classes and self._current_section == "education":
            self._text_parts.append("<<SCHOOL_START>>")
        if "edu-date" in classes and self._current_section == "education":
            self._text_parts.append("<<EDU_DATE_START>>")

        # Bullet lists
        if tag == "li":
            if self._current_section == "work" and "skills-list" not in self._section_stack:
                self._text_parts.append("<<BULLET>>")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip = False
            return

        # End markers
        if tag == "h1" and self._current_section == "full_name":
            self.blocks["full_name"] = "".join(self._text_parts).strip()
            self._current_section = ""

        if tag == "a" and self._in_contact:
            link_text = "".join(self._contact_parts).strip()
            self._contact_parts = []
            if "@" in link_text:
                self.blocks["email"] = link_text
            elif "linkedin" in link_text.lower():
                self.blocks["linkedin"] = link_text
            elif "portfolio" in link_text.lower() or "github" in link_text.lower():
                self.blocks["portfolio"] = link_text
            else:
                self._contact_parts = [link_text]  # might not be a special link

        if "contact-info" in self._get_endtag_class(tag):
            self._in_contact = False
            # Parse remaining contact text
            contact_text = " ".join(self._contact_parts).strip()
            self._parse_contact_text(contact_text)

        # Summary end
        if "summary-text" in self._get_endtag_class(tag) or (tag == "p" and self._current_section == "professional_summary"):
            self.blocks["professional_summary"] = "".join(self._text_parts).strip()
            self._current_section = ""

        # Job entry end
        if tag == "div" and self._current_section == "work" and self._section_stack and self._section_stack[-1] == "div":
            self._section_stack.pop()
            if not self._section_stack:
                self.blocks["work_experience_html"] += _join_text(self._text_parts) + "\n\n"
                self._current_section = ""
                self._text_parts = []

        # Skills list item end
        if tag == "li" and self._current_section == "skills":
            pass  # text collected in handle_data

        # Skills subsection end
        if "skills-subsection" in self._get_endtag_class(tag):
            self.blocks["skills_section_html"] += _join_text(self._text_parts) + "\n\n"
            self._current_section = ""
            self._text_parts = []

        if "skills-list" in self._get_endtag_class(tag):
            if "skills-list" in self._section_stack:
                self._section_stack.remove("skills-list")

        # Education entry end
        if tag == "div" and self._current_section == "education" and self._section_stack and self._section_stack[-1] == "div":
            self._section_stack.pop()
            if not self._section_stack:
                self.blocks["education_html"] += _join_text(self._text_parts) + "\n\n"
                self._current_section = ""
                self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        text = data.strip()
        if not text:
            return

        if self._current_section in ("full_name", "professional_summary"):
            self._text_parts.append(data)
        elif self._current_section == "work":
            self._text_parts.append(data)
        elif self._current_section == "skills":
            self._text_parts.append(data)
        elif self._current_section == "education":
            self._text_parts.append(data)
        elif self._in_contact:
            self._contact_parts.append(data)

    def _get_endtag_class(self, tag: str) -> str:
        """Stubs for end-tag class tracking — simplified."""
        return ""

    def _parse_contact_text(self, text: str) -> None:
        """Parse pipe-separated contact info text."""
        if not text:
            return
        parts = re.split(r"\s*\|\s*", text)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if re.match(r"[\d\s().+\-]{7,}", part) and "@" not in part:
                self.blocks["phone"] = part
            elif "@" in part:
                self.blocks["email"] = part
            elif re.match(r"https?://", part, re.IGNORECASE):
                if "linkedin" in part.lower():
                    self.blocks["linkedin"] = part
                else:
                    self.blocks["portfolio"] = part
            elif not self.blocks["location"]:
                self.blocks["location"] = part


def _join_text(parts: list[str]) -> str:
    """Join text parts, collapsing whitespace but preserving markers."""
    result = " ".join(p for p in parts if p)
    # Clean up whitespace around markers
    result = re.sub(r"\s+<<", " <<", result)
    result = re.sub(r">>\s+", ">> ", result)
    return result.strip()


# ---------------------------------------------------------------------------
# Typst markup generation from parsed HTML
# ---------------------------------------------------------------------------

def _escape_typst(text: str) -> str:
    """
    Escape special Typst characters in content text.
    Typst special chars: # $ @ < > _ * + - / = & { } [ ] ( )
    We only escape the most critical ones that would break markup.
    """
    # Escape backslash first
    text = text.replace("\\", "\\\\")
    # Escape hash (content mode escape)
    text = text.replace("#", "\\#")
    # Escape dollar (math mode)
    text = text.replace("$", "\\$")
    # Escape at-sign (references)
    text = text.replace("@", "\\@")
    # Escape angle brackets (label/ref syntax)
    text = text.replace("<", "\\<")
    text = text.replace(">", "\\>")
    # Escape underscores in the middle of words
    text = re.sub(r"(?<!^)(?<!\w)_(?=\w)", "\\_", text)
    text = re.sub(r"(?<=\w)_(?!\w)", "\\_", text)
    return text


def _render_work_typst(html_block: str) -> str:
    """
    Convert parsed work experience HTML block to Typst markup.
    """
    if not html_block.strip():
        return "#text(fill: gray)[No work experience listed.]"

    lines = []
    jobs = html_block.strip().split("\n\n")

    for job_text in jobs:
        if not job_text.strip():
            continue

        # Extract title
        title = ""
        company = ""
        dates = ""
        location = ""
        bullets: list[str] = []

        # Parse title
        title_match = re.search(r"<<TITLE>>(.*?)(?=<<|$)", job_text)
        if title_match:
            title = title_match.group(1).strip()

        # Parse company
        company_match = re.search(r"<<COMPANY_START>>(.*?)(?=(?:<<|$))", job_text)
        if company_match:
            company = company_match.group(1).strip()

        # Parse dates
        date_match = re.search(r"<<DATE_START>>(.*?)(?=(?:<<|$))", job_text)
        if date_match:
            dates = date_match.group(1).strip()

        # Parse location
        loc_match = re.search(r"<<LOCATION_START>>(.*?)(?=(?:<<|$))", job_text)
        if loc_match:
            location = loc_match.group(1).strip()

        # Parse bullets
        bullet_matches = re.split(r"<<BULLET>>", job_text)
        for bm in bullet_matches:
            bm = bm.strip()
            # Remove markers
            bm = re.sub(r"<<\w+>>", "", bm).strip()
            bm = re.sub(r"<<\w+_START>>", "", bm).strip()
            if bm and bm != title and bm != company:
                bullets.append(bm)

        if not title:
            # Fallback: try to extract what we can
            clean = re.sub(r"<<\w+>>", "", job_text).strip()
            clean = re.sub(r"<<\w+_START>>", "", clean).strip()
            if clean:
                lines.append(_escape_typst(clean))
                lines.append("#v(4pt)")
                continue

        # Build Typst output
        if title or company:
            header_parts = []
            if title:
                header_parts.append(_escape_typst(title))
            if company:
                header_parts.append(f" — {_escape_typst(company)}")

            lines.append(f"#text(size: 12pt, weight: \"bold\")[{_escape_typst(title)}]")
            if company:
                lines.append(f"#text(size: 11pt, weight: 600, fill: body-color)[ — {_escape_typst(company)}]")
            if dates:
                lines.append(f"#h(1fr) #text(size: 10pt, fill: muted)[{_escape_typst(dates)}]")
            if location:
                lines.append(f"#text(size: 10pt, fill: muted, style: \"italic\")[{_escape_typst(location)}]")
            lines.append("#v(4pt)")

        if bullets:
            for bullet in bullets:
                bullet = _escape_typst(bullet.strip())
                if bullet:
                    lines.append(f"+ {bullet}")
            lines.append("")

    return "\n".join(lines) if lines else "#text(fill: gray)[No work experience listed.]"


def _render_skills_typst(html_block: str) -> str:
    """
    Convert parsed skills HTML block to Typst markup.
    """
    if not html_block.strip():
        return "#text(fill: gray)[No skills listed.]"

    lines = []
    subsections = html_block.strip().split("\n\n")

    for subsection in subsections:
        if not subsection.strip():
            continue

        # Check for category heading
        cat_match = re.search(r"<<SKILL_CAT>>(.*?)(?=<<|$)", subsection)
        if cat_match:
            category = cat_match.group(1).strip()
            lines.append(f"#text(size: 11pt, weight: \"bold\", fill: body-color)[{_escape_typst(category)}]")
            lines.append("")

        # Extract individual skills from list items
        # Remove all markers first
        clean = re.sub(r"<<\w+>>", "", subsection)
        clean = re.sub(r"<<\w+_START>>", "", clean)

        # Split by common separators and create a comma-separated inline list
        # Look for individual skill items (they come from <li> elements)
        # The parser doesn't perfectly capture individual <li> items, so we parse the text
        parts = re.split(r"[•,\n]", clean)
        skills = [p.strip() for p in parts if p.strip() and len(p.strip()) > 1]

        # Filter out the category name
        if cat_match:
            cat_name = cat_match.group(1).strip()
            skills = [s for s in skills if s.lower() != cat_name.lower()]

        if skills:
            lines.append("#list(")
            for skill in skills:
                lines.append(f"  [{_escape_typst(skill)}],")
            lines.append(")")
            lines.append("")

    return "\n".join(lines) if lines else "#text(fill: gray)[No skills listed.]"


def _render_education_typst(html_block: str) -> str:
    """
    Convert parsed education HTML block to Typst markup.
    """
    if not html_block.strip():
        return "#text(fill: gray)[No education listed.]"

    lines = []
    entries = html_block.strip().split("\n\n")

    for entry in entries:
        if not entry.strip():
            continue

        degree = ""
        institution = ""
        year = ""

        deg_match = re.search(r"<<DEGREE>>(.*?)(?=<<|$)", entry)
        if deg_match:
            degree = deg_match.group(1).strip()

        school_match = re.search(r"<<SCHOOL_START>>(.*?)(?=(?:<<|$))", entry)
        if school_match:
            institution = school_match.group(1).strip()

        date_match = re.search(r"<<EDU_DATE_START>>(.*?)(?=(?:<<|$))", entry)
        if date_match:
            year = date_match.group(1).strip()

        if not degree:
            clean = re.sub(r"<<\w+>>", "", entry).strip()
            clean = re.sub(r"<<\w+_START>>", "", clean).strip()
            if clean:
                lines.append(_escape_typst(clean))
                lines.append("#v(4pt)")
                continue

        lines.append(f"#text(size: 11pt, weight: \"bold\")[{_escape_typst(degree)}]")
        if institution:
            lines.append(f"#text(size: 11pt, fill: body-color)[ — {_escape_typst(institution)}]")
        if year:
            lines.append(f"#h(1fr) #text(size: 10pt, fill: muted)[{_escape_typst(year)}]")
        lines.append("#v(6pt)")

    return "\n".join(lines) if lines else "#text(fill: gray)[No education listed.]"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def html_to_typst(html: str, template_type: str = "chronological") -> str:
    """
    Convert a rendered TALVEX HTML resume into Typst markup.

    Parameters
    ----------
    html : str
        Complete HTML document produced by the resume generator pipeline.
    template_type : str
        One of ``"chronological"``, ``"functional"``, ``"combination"``,
        ``"targeted"``. Determines which Typst template is loaded.

    Returns
    -------
    str
        Complete Typst source ready for compilation.
    """
    # 1. Parse HTML into structured blocks
    parser = _ResumeHTMLParser()
    try:
        parser.feed(html)
    except Exception as exc:
        logger.warning("HTML parsing failed, using fallback extraction: %s", exc)
        parser.blocks = _fallback_parse(html)

    # 1b. If structured parser yielded nothing, use fallback (handles generic HTML
    #     that lacks TALVEX-specific CSS classes like "resume-header")
    if not parser.blocks.get("full_name") and not parser.blocks.get("professional_summary"):
        logger.info("Structured parser found no content — using fallback extraction.")
        parser.blocks = _fallback_parse(html)

    # 2. Load Typst template
    template_type = template_type.lower().strip()
    template_path = _TEMPLATES_DIR / f"{template_type}.typ"
    if not template_path.exists():
        logger.warning("Typst template '%s' not found, falling back to chronological.", template_type)
        template_path = _TEMPLATES_DIR / "chronological.typ"
        if not template_path.exists():
            raise FileNotFoundError(f"Typst template directory not found: {_TEMPLATES_DIR}")

    with open(template_path, "r", encoding="utf-8") as f:
        template = f.read()

    # 3. Render Typst content blocks
    work_typst = _render_work_typst(parser.blocks["work_experience_html"])
    skills_typst = _render_skills_typst(parser.blocks["skills_section_html"])
    edu_typst = _render_education_typst(parser.blocks["education_html"])

    # 4. Build contact line (pipe-separated, only non-empty fields)
    contact_parts: list[str] = []
    if parser.blocks.get("location"):
        contact_parts.append(_escape_typst(parser.blocks["location"]))
    if parser.blocks.get("phone"):
        contact_parts.append(_escape_typst(parser.blocks["phone"]))
    if parser.blocks.get("email"):
        contact_parts.append(_escape_typst(parser.blocks["email"]))
    linkedin = parser.blocks.get("linkedin", "")
    if linkedin:
        contact_parts.append(f"LinkedIn: {_escape_typst(linkedin)}")
    portfolio = parser.blocks.get("portfolio", "")
    if portfolio:
        contact_parts.append(f"Portfolio: {_escape_typst(portfolio)}")

    contact_line = " | ".join(contact_parts) if contact_parts else ""

    # 5. Substitute placeholders in template
    output = template
    output = output.replace("#full_name", f"[{_escape_typst(parser.blocks.get('full_name', 'Candidate Name'))}]")
    output = output.replace("#contact_line", f"[{contact_line}]")
    output = output.replace("#professional_summary", f"[{_escape_typst(parser.blocks.get('professional_summary', ''))}]")
    output = output.replace("#work_experience", work_typst)
    output = output.replace("#skills_section", skills_typst)
    output = output.replace("#education", edu_typst)

    # 6. Clean up any residual #if conditional blocks (defensive)
    output = re.sub(
        r'#if\s+\w+\s*!=\s*""\s*\{[^}]*\}',
        "",
        output,
        flags=re.DOTALL,
    )

    return output


def _fallback_parse(html: str) -> dict[str, str]:
    """
    Fallback extraction using simple regex on HTML text.
    Used when the structured parser fails.
    """
    blocks: dict[str, str] = {
        "full_name": "",
        "email": "",
        "phone": "",
        "location": "",
        "linkedin": "",
        "portfolio": "",
        "professional_summary": "",
        "work_experience_html": "",
        "skills_section_html": "",
        "education_html": "",
    }

    # Extract name from <h1>
    name_match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL)
    if name_match:
        blocks["full_name"] = re.sub(r"<[^>]+>", "", name_match.group(1)).strip()

    # Extract email
    email_match = re.search(r"mailto:([^\"']+)", html)
    if email_match:
        blocks["email"] = email_match.group(1).strip()

    # Extract phone (simple heuristic)
    phone_match = re.search(r">\s*([+\d\s().\-]{7,})\s*<", html)
    if phone_match:
        blocks["phone"] = phone_match.group(1).strip()

    # Extract summary
    summary_match = re.search(r"class=\"summary-text\"[^>]*>(.*?)</p>", html, re.DOTALL)
    if summary_match:
        blocks["professional_summary"] = re.sub(r"<[^>]+>", "", summary_match.group(1)).strip()

    # Extract work experience section text
    exp_section = re.search(
        r"Work Experience.*?</h2>(.*?)(?=<h2|</div>\s*</div>\s*</body)",
        html, re.DOTALL
    )
    if exp_section:
        blocks["work_experience_html"] = exp_section.group(1)

    # Extract skills section
    skills_section = re.search(
        r"Skills.*?</h2>(.*?)(?=<h2|</div>\s*</div>\s*</body)",
        html, re.DOTALL
    )
    if skills_section:
        blocks["skills_section_html"] = skills_section.group(1)

    # Extract education
    edu_section = re.search(
        r"Education.*?</h2>(.*?)(?=<h2|</div>\s*</div>\s*</body)",
        html, re.DOTALL
    )
    if edu_section:
        blocks["education_html"] = edu_section.group(1)

    return blocks


def compile_typst(typst_source: str, output_path: str | None = None) -> bytes:
    """
    Compile Typst source to PDF.

    Parameters
    ----------
    typst_source : str
        Complete Typst markup source code.
    output_path : str, optional
        File path for the output PDF. If None, uses a temp file.

    Returns
    -------
    bytes
        Compiled PDF document bytes.

    Raises
    ------
    RuntimeError
        If Typst CLI is not available.
    FileNotFoundError
        If compilation fails.
    """
    typst_bin = _detect_typst()
    if not typst_bin:
        raise RuntimeError(
            "Typst CLI is not installed. Cannot compile Typst to PDF. "
            "Install Typst from https://github.com/typst/typst or use HTML fallback."
        )

    with tempfile.TemporaryDirectory(prefix="talvex_typst_") as tmpdir:
        src_path = os.path.join(tmpdir, "resume.typ")
        out_path = output_path or os.path.join(tmpdir, "resume.pdf")

        # Write source
        with open(src_path, "w", encoding="utf-8") as f:
            f.write(typst_source)

        # Compile
        try:
            result = subprocess.run(
                [typst_bin, "compile", src_path, out_path],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=tmpdir,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("Typst compilation timed out after 30 seconds.")
        except FileNotFoundError:
            raise RuntimeError(f"Typst binary not found at '{typst_bin}'.")

        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip()
            raise FileNotFoundError(
                f"Typst compilation failed (exit code {result.returncode}): {error_msg}"
            )

        # Read output PDF
        with open(out_path, "rb") as f:
            return f.read()


def html_to_pdf(
    html: str,
    template_type: str = "chronological",
    output_path: str | None = None,
) -> Optional[bytes]:
    """
    End-to-end: convert HTML resume to PDF via Typst.

    Returns None if Typst is not available (caller should fall back to HTML).
    """
    if not is_typst_available():
        logger.info("Typst CLI not available — returning None for PDF fallback.")
        return None

    try:
        typst_source = html_to_typst(html, template_type)
        pdf_bytes = compile_typst(typst_source, output_path)
        logger.info("Successfully compiled Typst PDF (%d bytes).", len(pdf_bytes))
        return pdf_bytes
    except Exception as exc:
        logger.error("Typst PDF generation failed: %s", exc)
        return None
