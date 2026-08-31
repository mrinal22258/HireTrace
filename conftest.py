"""
Pytest configuration for HireTrace.
Ensures root directory is always in sys.path during test execution.
"""

import sys
import os

root_dir = os.path.dirname(os.path.abspath(__file__))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)
