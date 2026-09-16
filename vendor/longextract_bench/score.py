from typing import Any, Dict, Optional
from vendor.longextract_bench.grading import grade


def score_single(gt: Dict[str, Any], pred: Dict[str, Any], schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Scores a single candidate prediction against ground truth."""
    return grade(gt, pred, schema)


def score_dataset(ground_truths: Dict[str, Any], predictions: Dict[str, Any], schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Scores a dataset of ground truth records against candidate predictions.
    Aggregates precision, recall, f1, leaf accuracy, and completion rate.
    """
    total = len(ground_truths)
    completed = 0
    precisions = []
    recalls = []
    leaf_accs = []
    per_case = {}

    for cid, gt in ground_truths.items():
        pred = predictions.get(cid, {})
        res = grade(gt, pred, schema)
        per_case[cid] = res
        if pred:
            completed += 1
        precisions.append(res["precision"])
        recalls.append(res["recall"])
        leaf_accs.append(res["leaf_accuracy"])

    mean_p = sum(precisions) / max(1, len(precisions))
    mean_r = sum(recalls) / max(1, len(recalls))
    f1 = (2 * mean_p * mean_r / (mean_p + mean_r)) if (mean_p + mean_r) > 0 else 0.0
    mean_leaf = sum(leaf_accs) / max(1, len(leaf_accs))

    summary = {
        "total_documents": total,
        "completed_documents": completed,
        "completion_rate_pct": round((completed / max(1, total)) * 100.0, 1),
        "mean_array_precision": round(mean_p, 3),
        "mean_array_recall": round(mean_r, 3),
        "array_f1": round(f1, 3),
        "mean_leaf_accuracy_pct": round(mean_leaf, 1)
    }

    return {
        "summary": summary,
        "per_case": per_case
    }
