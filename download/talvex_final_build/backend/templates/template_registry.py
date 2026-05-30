"""
TALVEX Resume Template Registry

Maps template types to their HTML template files and provides
utility functions for template retrieval and listing.

Supported template types:
  - chronological: Traditional reverse-chronological format
  - functional:    Skills-first format emphasizing transferable abilities
  - combination:   Hybrid format with skills summary + detailed work history
  - targeted:      Keyword-optimized format tailored to a specific job description
"""

import os
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TEMPLATES_DIR = Path(__file__).resolve().parent

TEMPLATE_REGISTRY: dict[str, dict] = {
    "chronological": {
        "file": "chronological.html",
        "name": "Chronological",
        "description": (
            "Traditional reverse-chronological resume format. "
            "Best for candidates with a steady, progressive work history "
            "in a single industry or field."
        ),
        "best_for": (
            "Experienced professionals, career advancement seekers, "
            "candidates with consistent employment history"
        ),
        "section_order": [
            "Contact Info",
            "Professional Summary",
            "Work Experience (reverse-chronological)",
            "Skills",
            "Education",
        ],
    },
    "functional": {
        "file": "functional.html",
        "name": "Functional",
        "description": (
            "Skills-first resume format that highlights competencies and achievements "
            "rather than chronological work history. "
            "De-emphasizes employment gaps or frequent job changes."
        ),
        "best_for": (
            "Career changers, recent graduates, candidates with employment gaps, "
            "those with diverse or non-linear career paths"
        ),
        "section_order": [
            "Contact Info",
            "Professional Summary",
            "Relevant Skills & Thematic Accomplishments",
            "Work History (brief)",
            "Education",
        ],
    },
    "combination": {
        "file": "combination.html",
        "name": "Combination",
        "description": (
            "Hybrid resume format combining a skills/competencies summary at the top "
            "with a reverse-chronological work experience section below. "
            "Offers the best of both worlds."
        ),
        "best_for": (
            "Mid-career professionals, those with strong skills and solid work history, "
            "candidates transitioning to a new role within the same industry"
        ),
        "section_order": [
            "Contact Info",
            "Professional Summary",
            "Core Competencies / Skill Highlights",
            "Professional Experience",
            "Education",
        ],
    },
    "targeted": {
        "file": "targeted.html",
        "name": "Targeted",
        "description": (
            "Keyword-optimized resume format tailored to a specific job description. "
            "Mirrors JD language throughout and prioritizes qualifications requested "
            "by the employer."
        ),
        "best_for": (
            "Applying to a specific job posting, candidates who want to maximize "
            "ATS match scores, those tailoring each application individually"
        ),
        "section_order": [
            "Contact Info",
            "Professional Summary (JD-matched)",
            "Key Qualifications & Keywords",
            "Professional Experience",
            "Education & Certifications",
        ],
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_template(template_type: str) -> str:
    """
    Return the HTML content of the requested resume template.

    Parameters
    ----------
    template_type : str
        One of "chronological", "functional", "combination", "targeted".

    Returns
    -------
    str
        Full HTML template string ready for Jinja2 rendering.

    Raises
    ------
    ValueError
        If the template type is not recognized or the file is missing.
    """
    template_type = template_type.lower().strip()

    if template_type not in TEMPLATE_REGISTRY:
        valid = ", ".join(f'"{k}"' for k in TEMPLATE_REGISTRY)
        raise ValueError(
            f"Unknown template type '{template_type}'. "
            f"Valid types: {valid}"
        )

    file_name = TEMPLATE_REGISTRY[template_type]["file"]
    file_path = TEMPLATES_DIR / file_name

    if not file_path.exists():
        raise FileNotFoundError(
            f"Template file not found: {file_path}"
        )

    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def list_templates() -> list[dict]:
    """
    Return metadata for all available resume templates.

    Each entry contains:
      - type      : str   – internal key (e.g. "chronological")
      - name      : str   – human-readable name
      - description : str – one-paragraph description
      - best_for  : str   – who the template is best suited for
      - section_order : list[str] – ordered section headers
    """
    result = []
    for key, meta in TEMPLATE_REGISTRY.items():
        result.append(
            {
                "type": key,
                "name": meta["name"],
                "description": meta["description"],
                "best_for": meta["best_for"],
                "section_order": meta["section_order"],
            }
        )
    return result


def validate_template(template_type: str) -> bool:
    """Check whether a template type string is valid."""
    return template_type.lower().strip() in TEMPLATE_REGISTRY
