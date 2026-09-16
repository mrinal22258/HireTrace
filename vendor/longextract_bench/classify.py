from typing import Any, Dict, Optional, Tuple


def classify(result_envelope: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    """
    Classifies a pipeline extraction output envelope into ('success', None) or ('failure', reason).
    """
    meta = result_envelope.get("_meta", {})
    if meta.get("status") == "failed":
        return "failure", meta.get("error", "execution failed")

    res = result_envelope.get("result")
    if res is None and "result" in result_envelope:
        return "failure", "empty result"

    if isinstance(res, dict) and not res:
        return "failure", "empty result"

    if not result_envelope:
        return "failure", "empty result"

    return "success", None
