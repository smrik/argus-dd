"""Table-preserving PDF text extraction (xpdf, not Poppler)."""

import os
import shutil
import subprocess


def pdftotext():
    tool = os.environ.get("PDFTOTEXT") or shutil.which("pdftotext")
    if not tool:
        return None
    try:
        help_text = subprocess.run([tool, "-h"], capture_output=True, encoding="utf-8", errors="replace")
    except OSError:
        return None
    return tool if "-table" in help_text.stdout + help_text.stderr else None


def pdf_lines(path):
    tool = pdftotext()
    if tool is None:
        raise ValueError("no pdftotext with -table; set PDFTOTEXT to xpdf")
    return subprocess.run([tool, "-table", str(path), "-"], check=True, capture_output=True,
                          encoding="utf-8").stdout.splitlines()
