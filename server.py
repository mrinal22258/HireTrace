"""
HireTrace UI Dashboard Server Entrypoint.

Delegates directly to ui/server.py to allow starting the server from the root directory:
    python server.py
or
    python ui/server.py
"""

import runpy
import sys
from pathlib import Path

if __name__ == "__main__":
    server_file = Path(__file__).parent / "ui" / "server.py"
    runpy.run_path(str(server_file), run_name="__main__")
