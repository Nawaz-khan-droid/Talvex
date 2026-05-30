#!/usr/bin/env python3
"""
TALVEX Typst Compilation Helper Script

CLI wrapper for converting HTML resumes to PDF via Typst.
Designed to be called from the Next.js API route.

Usage:
    python scripts/compile_typst.py --html <html_content> --template <type> [--output <path>]
    echo '<html>...</html>' | python scripts/compile_typst.py --template chronological
    python scripts/compile_typst.py --file resume.html --template combination

Options:
    --html        HTML content as string argument
    --file        Path to HTML file (alternative to --html)
    --template    Template type: chronological, functional, combination, targeted
    --output      Output PDF file path (default: stdout as binary)

Exit codes:
    0   Success — PDF bytes written to output
    1   Typst not available — prints fallback HTML to stdout
    2   Invalid arguments
    3   Compilation error
"""

from __future__ import annotations

import argparse
import json
import sys
import os

# Add backend to path so we can import services
BACKEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, BACKEND_DIR)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="TALVEX Typst PDF compiler — converts HTML resumes to PDF",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--html",
        type=str,
        default=None,
        help="HTML content as a string argument",
    )
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Path to an HTML file to convert",
    )
    parser.add_argument(
        "--template",
        type=str,
        default="chronological",
        choices=["chronological", "functional", "combination", "targeted"],
        help="Resume template type (default: chronological)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output PDF file path (default: stdout as binary)",
    )
    parser.add_argument(
        "--json-status",
        action="store_true",
        help="Output result status as JSON to stderr",
    )

    args = parser.parse_args()

    # Read HTML input
    html_content = args.html
    if not html_content and args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                html_content = f.read()
        except FileNotFoundError:
            _emit_status(args.json_status, {"success": False, "error": f"File not found: {args.file}"}, exit_code=2)
            return
    if not html_content:
        # Try reading from stdin
        if not sys.stdin.isatty():
            html_content = sys.stdin.read()
        if not html_content:
            _emit_status(args.json_status, {"success": False, "error": "No HTML input provided"}, exit_code=2)
            return

    # Import and compile
    try:
        from services.typst_compiler import html_to_pdf, is_typst_available
    except ImportError as exc:
        _emit_status(
            args.json_status,
            {"success": False, "error": f"Cannot import typst_compiler: {exc}"},
            exit_code=3,
        )
        return

    # Check if Typst is available
    if not is_typst_available():
        _emit_status(
            args.json_status,
            {"success": False, "typst_available": False, "error": "Typst CLI not installed"},
            exit_code=1,
        )
        # Output HTML fallback to stdout
        _emit_html_fallback(html_content)
        return

    # Compile
    pdf_bytes = html_to_pdf(html_content, args.template, args.output)

    if pdf_bytes is None:
        _emit_status(
            args.json_status,
            {"success": False, "typst_available": True, "error": "Compilation returned empty result"},
            exit_code=3,
        )
        _emit_html_fallback(html_content)
        return

    # Output PDF
    if args.output:
        _emit_status(
            args.json_status,
            {
                "success": True,
                "typst_available": True,
                "output": args.output,
                "size_bytes": len(pdf_bytes),
            },
        )
    else:
        # Write PDF to stdout (binary)
        sys.stdout.buffer.write(pdf_bytes)
        _emit_status(
            args.json_status,
            {
                "success": True,
                "typst_available": True,
                "output": "stdout",
                "size_bytes": len(pdf_bytes),
            },
        )


def _emit_status(use_json: bool, status: dict, exit_code: int = 0) -> None:
    """Emit status info to stderr."""
    if use_json:
        import json
        sys.stderr.write(json.dumps(status) + "\n")
    if exit_code:
        sys.exit(exit_code)


def _emit_html_fallback(html: str) -> None:
    """
    Output a print-ready HTML fallback to stdout.
    Wraps the original HTML with enhanced print styles for browser-based PDF.
    """
    # Extract the body content from the HTML
    import re

    body_match = re.search(r"<body[^>]*>(.*?)</body>", html, re.DOTALL)
    if body_match:
        body_content = body_match.group(1)
    else:
        body_content = html

    print_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>TALVEX Resume — Print to PDF</title>
<style>
  @page {{
    margin: 0;
    size: letter;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'Calibri', 'Carlito', Arial, sans-serif;
    font-size: 11pt;
    line-height: 1.4;
    color: #333;
  }}
  .resume {{
    max-width: 8.5in;
    margin: 0 auto;
  }}
  @media print {{
    body {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  }}
</style>
<script>
  // Auto-trigger print dialog when loaded
  window.addEventListener('load', function() {{
    setTimeout(function() {{ window.print(); }}, 500);
  }});
</script>
</head>
<body>
<div class="resume">
{body_content}
</div>
</body>
</html>"""
    sys.stdout.buffer.write(print_html.encode("utf-8"))


if __name__ == "__main__":
    main()
