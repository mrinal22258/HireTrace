import json
import os
import sys

# Ensure project root is in sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from eval_cases.dataset import CASES, SHARED_JD

target_dir = os.path.join(root_dir, "eval_cases")
os.makedirs(target_dir, exist_ok=True)

count = 0
for case in CASES:
    cid = case["candidate_id"]
    filepath = os.path.join(target_dir, f"{cid}.json")
    data = dict(case)
    if "jd_text" not in data or not data["jd_text"]:
        data["jd_text"] = SHARED_JD
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    count += 1

print(f"SUCCESS: Exported {count} cases to {target_dir}")
