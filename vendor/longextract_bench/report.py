from typing import Any, Dict


def format_markdown_report(score_dict: Dict[str, Any]) -> str:
    """Formats LongExtractBench score results into a clean markdown table."""
    sm = score_dict.get("summary", {})
    lines = [
        "## LongExtractBench Structured Extraction Benchmark",
        "",
        "| Metric | Score | Target |",
        "|---|---|---|",
        f"| Completion Rate | {sm.get('completion_rate_pct', 0.0)}% | 100.0% |",
        f"| Array Row Precision | {sm.get('mean_array_precision', 0.0):.3f} | >= 0.850 |",
        f"| Array Row Recall | {sm.get('mean_array_recall', 0.0):.3f} | >= 0.850 |",
        f"| Array Row F1 Score | {sm.get('array_f1', 0.0):.3f} | >= 0.850 |",
        f"| Matched Leaf Accuracy | {sm.get('mean_leaf_accuracy_pct', 0.0):.1f}% | >= 80.0% |"
    ]
    return "\n".join(lines)
