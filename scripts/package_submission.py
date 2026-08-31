"""
Utility script to create a clean, pristine submission zip export.
Excludes stray dev files, local runners (e.g. powershell.cmd), scratch scripts,
raw video recording working directories, and compiled __pycache__ directories.
"""

import os
import sys
import zipfile
import shutil

EXCLUDE_DIRS = {
    "__pycache__",
    ".git",
    ".pytest_cache",
    "scratch",
    ".gemini",
    ".idea",
    ".vscode",
    "video"
}

EXCLUDE_FILES = {
    "powershell.cmd",
    ".DS_Store",
    "test_clip.mp4"
}

EXCLUDE_EXTENSIONS = (
    ".pyc",
    ".pyo",
    ".zip",
    ".screenrec",
    ".avi",
    ".wav"
)

def package_submission(output_zip: str = "hiretrace_clean_submission.zip", include_video: bool = False):
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    zip_path = os.path.join(root_dir, output_zip)

    # Remove existing zip if present to prevent nesting or stale artifacts
    if os.path.exists(zip_path):
        os.remove(zip_path)

    count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for current_root, dirs, files in os.walk(root_dir):
            # Prune excluded directories
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]

            for file in files:
                if file in EXCLUDE_FILES or file.endswith(EXCLUDE_EXTENSIONS):
                    continue
                if not include_video and file.endswith(".mp4"):
                    continue
                if file == output_zip or file.startswith("custom_"):
                    continue

                abs_file = os.path.join(current_root, file)
                if os.path.abspath(abs_file) == os.path.abspath(zip_path):
                    continue
                rel_file = os.path.relpath(abs_file, root_dir)
                zipf.write(abs_file, rel_file)
                count += 1

    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"SUCCESS: Packaged {count} clean files into {output_zip} ({size_mb:.2f} MB)")

if __name__ == "__main__":
    inc_video = "--with-video" in sys.argv
    # Generate clean standard submission zip
    package_submission("hiretrace_clean_submission.zip", include_video=False)
    if inc_video or os.path.exists(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hiretrace_walkthrough.mp4")):
        package_submission("hiretrace_submission_with_video.zip", include_video=True)
