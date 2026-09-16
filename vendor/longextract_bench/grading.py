import re
from typing import Any, Dict, List, Tuple, Optional


def canonical(val: Any) -> str:
    """Normalizes cosmetic differences in extracted strings, dates, and numbers."""
    if val is None:
        return ""
    s = str(val).strip().lower()
    if s in ("n/a", "none", "null"):
        return ""
    # Remove number formatting commas (e.g. 1,000 -> 1000)
    s = re.sub(r'(?<=\d),(?=\d)', '', s)
    # Remove trailing .0 from floats (e.g. 45.0 -> 45)
    s = re.sub(r'\.0$', '', s)
    # Collapse multiple spaces
    s = re.sub(r'\s+', ' ', s)
    return s


def _leaf_match(gt_val: Any, pred_val: Any) -> bool:
    if isinstance(gt_val, dict) and isinstance(pred_val, dict):
        keys = set(gt_val.keys()).union(pred_val.keys())
        return all(_leaf_match(gt_val.get(k), pred_val.get(k)) for k in keys)
    elif isinstance(gt_val, list) and isinstance(pred_val, list):
        if len(gt_val) != len(pred_val):
            return False
        return all(canonical(a) == canonical(b) for a, b in zip(sorted(gt_val, key=str), sorted(pred_val, key=str)))
    else:
        return canonical(gt_val) == canonical(pred_val)


def grade(gt: Dict[str, Any], pred: Dict[str, Any], schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Grades predicted structured CV against ground truth.
    Pairs array rows by content and computes precision, recall, and leaf accuracy.
    """
    gt_history = gt.get("employment_history", [])
    pred_history = pred.get("employment_history", [])

    matched = 0
    leaf_correct = 0
    leaf_total = 0

    # Match employment history rows
    used_pred = set()
    for gt_item in gt_history:
        gt_emp = canonical(gt_item.get("employer"))
        gt_title = canonical(gt_item.get("title"))
        best_match_idx = None

        for p_idx, pred_item in enumerate(pred_history):
            if p_idx in used_pred:
                continue
            p_emp = canonical(pred_item.get("employer"))
            p_title = canonical(pred_item.get("title"))
            if gt_emp == p_emp or gt_title == p_title:
                best_match_idx = p_idx
                break

        if best_match_idx is not None:
            matched += 1
            used_pred.add(best_match_idx)
            pred_item = pred_history[best_match_idx]
            for k in ("employer", "title", "start_date", "end_date", "is_current"):
                if k in gt_item or k in pred_item:
                    leaf_total += 1
                    if _leaf_match(gt_item.get(k), pred_item.get(k)):
                        leaf_correct += 1

    # Check top-level scalar fields (e.g. candidate_name)
    for k in ("candidate_name",):
        if k in gt or k in pred:
            leaf_total += 1
            if canonical(gt.get(k)) == canonical(pred.get(k)):
                leaf_correct += 1

    # Check skills array
    gt_skills = [canonical(s) for s in gt.get("skills", []) if canonical(s)]
    pred_skills = [canonical(s) for s in pred.get("skills", []) if canonical(s)]
    if gt_skills or pred_skills:
        for sk in gt_skills:
            leaf_total += 1
            if sk in pred_skills:
                leaf_correct += 1

    precision = (matched / max(1, len(pred_history))) if pred_history else 1.0
    recall = (matched / max(1, len(gt_history))) if gt_history else 1.0
    leaf_accuracy = (leaf_correct / max(1, leaf_total)) * 100.0 if leaf_total else 100.0

    return {
        "matched": matched,
        "precision": precision,
        "recall": recall,
        "leaf_accuracy": leaf_accuracy,
        "leaf_correct": leaf_correct,
        "leaf_total": leaf_total
    }
