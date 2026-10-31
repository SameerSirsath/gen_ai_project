"""
table_extractor.py — Layer 3: PDF table detection and Markdown conversion.

Tables in PDFs are tricky — pdfplumber finds them as raw 2D lists.
This module:
  1. Cleans and normalises raw cell values
  2. Detects header rows
  3. Outputs a proper GitHub-flavored Markdown table
  4. Optionally outputs a pandas DataFrame for structured analysis

Usage:
    from pipeline.ocr.table_extractor import raw_table_to_markdown
    md = raw_table_to_markdown(raw_table)
"""

import re
from typing import Optional


# ─────────────────────────────────────────────
# Cell Normalisation
# ─────────────────────────────────────────────

def _normalise_cell(value) -> str:
    """Convert any cell value to a clean string."""
    if value is None:
        return ""
    text = str(value).strip()
    # Remove newlines within cells (collapse to space)
    text = re.sub(r"\s+", " ", text)
    # Escape pipe chars that would break Markdown table
    text = text.replace("|", "\\|")
    return text


def _is_header_row(row: list[str], row_index: int) -> bool:
    """
    Heuristic: the first non-empty row is treated as header.
    Also checks if values look like typical header labels (short, capitalized).
    """
    if row_index == 0:
        return True
    # Short, mostly alpha cells suggest headers
    non_empty = [c for c in row if c]
    if not non_empty:
        return False
    avg_len = sum(len(c) for c in non_empty) / len(non_empty)
    alpha_ratio = sum(c.isalpha() for c in "".join(non_empty)) / max(len("".join(non_empty)), 1)
    return avg_len < 25 and alpha_ratio > 0.7 and row_index < 3


# ─────────────────────────────────────────────
# Core Converters
# ─────────────────────────────────────────────

def raw_table_to_markdown(raw_table: list[list], caption: str = "") -> str:
    """
    Convert a pdfplumber raw table (list of lists) to a Markdown table string.

    Args:
        raw_table: 2D list where raw_table[row][col] is a cell value.
        caption:   Optional table caption prepended as a bold label.

    Returns:
        Markdown-formatted table string, or "" if table is empty/invalid.
    """
    if not raw_table:
        return ""

    # Normalise all cells
    table = [[_normalise_cell(cell) for cell in row] for row in raw_table]

    # Remove completely empty rows
    table = [row for row in table if any(cell.strip() for cell in row)]
    if not table:
        return ""

    # Ensure consistent column count
    max_cols = max(len(row) for row in table)
    table = [row + [""] * (max_cols - len(row)) for row in table]

    lines = []

    if caption:
        lines.append(f"**{caption}**\n")

    # Header row (first non-empty row)
    header = table[0]
    data_rows = table[1:]

    # If header is blank, generate column letters
    if all(not h.strip() for h in header):
        header = [f"Col {i+1}" for i in range(max_cols)]
        data_rows = table  # all rows are data rows

    # Build Markdown table
    header_line = "| " + " | ".join(header) + " |"
    separator   = "| " + " | ".join(["---"] * max_cols) + " |"
    lines.append(header_line)
    lines.append(separator)

    for row in data_rows:
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def raw_table_to_dataframe(raw_table: list[list]):
    """
    Convert a raw table to a pandas DataFrame (for structured data analysis).
    Returns None if pandas is not available.
    """
    try:
        import pandas as pd
    except ImportError:
        return None

    if not raw_table:
        return None

    table = [[_normalise_cell(cell) for cell in row] for row in raw_table]
    table = [row for row in table if any(c.strip() for c in row)]

    if not table:
        return None

    max_cols = max(len(row) for row in table)
    table = [row + [""] * (max_cols - len(row)) for row in table]

    # Use first row as header
    header = table[0]
    if all(not h.strip() for h in header):
        header = [f"col_{i}" for i in range(max_cols)]
        data = table
    else:
        data = table[1:]

    # Deduplicate header names
    seen = {}
    clean_header = []
    for h in header:
        key = h.strip() or "col"
        count = seen.get(key, 0)
        clean_header.append(f"{key}_{count}" if count else key)
        seen[key] = count + 1

    return pd.DataFrame(data, columns=clean_header)


# ─────────────────────────────────────────────
# Multi-table extractor summary
# ─────────────────────────────────────────────

def format_tables_section(raw_tables: list[list[list]], page_num: int) -> str:
    """
    Format all tables from a single PDF page into one text block.

    Returns:
        Combined Markdown string for all tables on this page.
    """
    if not raw_tables:
        return ""

    sections = []
    for i, table in enumerate(raw_tables, start=1):
        md = raw_table_to_markdown(table, caption=f"Table {i} (Page {page_num})")
        if md:
            sections.append(md)

    return "\n\n".join(sections)
