"""
step5_storage.py — Output & Storage Module.

Saves processed data to:
  • JSON (full records)
  • CSV (flat table for spreadsheet use)
  • Excel (formatted report)
  • Markdown summary report
"""

import os
import json
from datetime import datetime

import pandas as pd

from .config import OUTPUT_DIR


def _ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def _company_folder(company_name: str) -> str:
    """Create and return a timestamped folder for this company's data."""
    safe_name = company_name.lower().replace(" ", "_").replace("/", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = os.path.join(OUTPUT_DIR, f"{safe_name}_{timestamp}")
    _ensure_dir(folder)
    return folder


# ─────────────────────────────────────────────
# Save Functions
# ─────────────────────────────────────────────

def save_json(records: list[dict], folder: str, company_name: str) -> str:
    """Save all records as a JSON file."""
    path = os.path.join(folder, "raw_records.json")
    # Remove non-serializable keys (e.g., dataframes inside records)
    serializable = [{k: v for k, v in r.items() if isinstance(v, (str, int, float, list, dict, bool, type(None)))}
                    for r in records]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2, ensure_ascii=False)
    print(f"    ✓ JSON saved: {path}")
    return path


def save_csv(df: pd.DataFrame, folder: str, company_name: str) -> str:
    """Save cleaned DataFrame as CSV."""
    path = os.path.join(folder, "processed_data.csv")
    # Drop complex columns for CSV
    csv_df = df.drop(columns=["topics"], errors="ignore").copy()
    if "topics" in df.columns:
        csv_df["topics"] = df["topics"].apply(
            lambda x: ", ".join(x) if isinstance(x, list) else str(x)
        )
    csv_df.to_csv(path, index=False, encoding="utf-8")
    print(f"    ✓ CSV saved: {path}")
    return path


def save_excel(df: pd.DataFrame, folder: str, company_name: str) -> str:
    """Save DataFrame as formatted Excel report."""
    path = os.path.join(folder, "company_intelligence.xlsx")
    try:
        excel_df = df.copy()
        if "topics" in excel_df.columns:
            excel_df["topics"] = excel_df["topics"].apply(
                lambda x: ", ".join(x) if isinstance(x, list) else str(x)
            )

        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            excel_df.to_excel(writer, sheet_name="All Data", index=False)

            # Ensure word_count column is present
            if "word_count" not in excel_df.columns:
                excel_df["word_count"] = excel_df["text"].apply(lambda t: len(str(t).split()))

            # Source breakdown sheet
            if "source" in excel_df.columns:
                summary = excel_df.groupby("source").agg(
                    records=("text", "count"),
                    avg_words=("word_count", "mean"),
                ).reset_index()
                summary.to_excel(writer, sheet_name="Source Summary", index=False)

            # Topics breakdown
            if "topics" in excel_df.columns:
                topics_flat = excel_df["topics"].str.split(", ").explode()
                topic_counts = topics_flat.value_counts().reset_index()
                topic_counts.columns = ["topic", "count"]
                topic_counts.to_excel(writer, sheet_name="Topics", index=False)

        print(f"    ✓ Excel saved: {path}")
    except Exception as e:
        print(f"    [WARN] Excel save failed (install openpyxl): {e}")
        path = ""
    return path


def save_markdown_report(
    company_name: str,
    company_info: dict,
    ai_summary: str,
    df: pd.DataFrame,
    folder: str,
) -> str:
    """Generate a readable Markdown intelligence report."""
    path = os.path.join(folder, "company_report.md")

    source_counts = df["source"].value_counts().to_dict() if "source" in df.columns else {}
    topics_all = []
    if "topics" in df.columns:
        for t in df["topics"]:
            if isinstance(t, list):
                topics_all.extend(t)
    from collections import Counter
    topic_freq = Counter(topics_all).most_common(10)

    lines = [
        f"# 🏢 Company Intelligence Report: {company_name}",
        f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
        "---",
        "",
        "## 📊 Data Collection Summary",
        "",
        f"| Source | Records |",
        f"|--------|---------|",
    ]
    for src, count in source_counts.items():
        lines.append(f"| {src} | {count} |")

    lines += [
        "",
        f"**Total chunks collected:** {len(df)}",
        "",
        "---",
        "",
        "## 🔍 Extracted Company Information",
        "",
    ]
    if company_info:
        for k, v in company_info.items():
            lines.append(f"- **{k.replace('_', ' ').title()}**: {v}")
    else:
        lines.append("- *No structured data extracted (may need manual review)*")

    lines += [
        "",
        "---",
        "",
        "## 🏷️ Topic Distribution",
        "",
    ]
    if topic_freq:
        for topic, count in topic_freq:
            bar = "█" * min(count, 20)
            lines.append(f"- **{topic.replace('_', ' ').title()}**: {bar} ({count})")
    else:
        lines.append("- *No topics detected*")

    lines += [
        "",
        "---",
        "",
        "## 🤖 AI-Generated Intelligence Summary",
        "",
    ]
    if ai_summary:
        lines.append(ai_summary)
    else:
        lines.append(
            "*AI summary not generated — set `OPENAI_API_KEY` or `GOOGLE_API_KEY` "
            "environment variable to enable this feature.*"
        )

    lines += [
        "",
        "---",
        "",
        "## 📄 Sample Data Snippets",
        "",
    ]
    sample_records = df[df["word_count"] > 30].head(5) if "word_count" in df.columns else df.head(5)
    for _, row in sample_records.iterrows():
        lines += [
            f"### [{row.get('source', 'unknown')}] {str(row.get('title', ''))[:80]}",
            f"> {str(row.get('text', ''))[:300]}...",
            "",
        ]

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"    ✓ Markdown report saved: {path}")
    return path


# ─────────────────────────────────────────────
# Main Entry Point
# ─────────────────────────────────────────────

def save_all(
    company_name: str,
    preprocessed: dict,
) -> dict:
    """
    Saves all output formats and returns paths.
    Args:
        company_name:  Target company name
        preprocessed:  Output from step4_preprocessor.preprocess()
    Returns:
        Dict of output file paths
    """
    print(f"\n{'='*60}")
    print(f"[STORAGE] Saving outputs for: {company_name}")
    print(f"{'='*60}")

    folder = _company_folder(company_name)
    df = preprocessed["dataframe"]
    records = preprocessed["records"]
    ai_summary = preprocessed.get("summary", "")
    company_info = preprocessed.get("company_info", {})

    paths = {
        "output_folder": folder,
        "json": save_json(records, folder, company_name),
        "csv": save_csv(df, folder, company_name),
        "excel": save_excel(df, folder, company_name),
        "report": save_markdown_report(company_name, company_info, ai_summary, df, folder),
    }

    print(f"\n  📁 All outputs saved to: {folder}")
    return paths
