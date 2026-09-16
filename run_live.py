"""
HireTrace Live Launcher
=======================
One-command script to start Ollama and launch HireTrace live with zero friction:
1. Detects if Ollama is running at http://localhost:11434; if not, starts 'ollama serve' in background.
2. Checks that 'qwen2.5:3b' is pulled; if not, auto-pulls it.
3. Automatically opens default browser to http://127.0.0.1:8080.
4. Starts the HireTrace FastAPI/Uvicorn application server on port 8080.
5. Handles graceful shutdown on Ctrl+C.
"""

import os
import sys
import time
import shutil
import urllib.request
import urllib.error
import subprocess
import threading
import webbrowser

OLLAMA_URL = "http://localhost:11434"
MODEL_NAME = "qwen2.5:3b"
APP_PORT = 8080
APP_URL = f"http://127.0.0.1:{APP_PORT}"

banner = r"""
╔═══════════════════════════════════════════════════════════════════╗
║                      HIRETRACE LIVE LAUNCHER                     ║
║              Multi-Source Evidence-First Candidate Evaluator      ║
║                  Zero Paid API Calls • 100% Offline               ║
╚═══════════════════════════════════════════════════════════════════╝
"""


def is_ollama_running() -> bool:
    """Check if Ollama server responds on localhost:11434."""
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/version")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def start_ollama_service():
    """Attempt to spawn 'ollama serve' in the background if not active."""
    if is_ollama_running():
        print("[+] Ollama service is already running at http://localhost:11434.")
        return None

    ollama_bin = shutil.which("ollama")
    if not ollama_bin:
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        candidate = os.path.join(local_app_data, "Programs", "Ollama", "ollama.exe")
        if os.path.exists(candidate):
            ollama_bin = candidate

    if not ollama_bin:
        print("[!] 'ollama' executable not found in PATH or standard directories.")
        print("[!] HireTrace will start in offline mock fallback mode ($0.00 cost).")
        return None

    print(f"[*] Starting Ollama daemon in background ({ollama_bin} serve)...")
    try:
        creationflags = 0
        if sys.platform == "win32":
            creationflags = 0x00000200  # CREATE_NEW_PROCESS_GROUP

        proc = subprocess.Popen(
            [ollama_bin, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags
        )

        print("[*] Waiting for Ollama to initialize...", end="", flush=True)
        for _ in range(24):
            time.sleep(0.5)
            print(".", end="", flush=True)
            if is_ollama_running():
                print(" Ready!")
                return proc
        print(" [Warning: Ollama slow to respond, proceeding]")
        return proc
    except Exception as e:
        print(f"\n[!] Could not start Ollama automatically: {e}")
        print("[!] Running with offline mock evaluator fallback.")
        return None


def verify_model(model_name: str = MODEL_NAME):
    """Ensure the target model exists in Ollama; pull if missing."""
    if not is_ollama_running():
        return

    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = resp.read().decode("utf-8")
            if model_name in data:
                print(f"[+] Model '{model_name}' is verified and ready.")
                return

        print(f"[*] Model '{model_name}' not detected locally. Auto-pulling...")
        ollama_bin = shutil.which("ollama") or "ollama"
        subprocess.run([ollama_bin, "pull", model_name], check=False)
    except Exception as e:
        print(f"[!] Model verification note: {e}")


def is_port_in_use(port: int) -> bool:
    """Check if a local TCP port is currently bound."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def is_hiretrace_running(port: int) -> bool:
    """Check if an active HireTrace API instance is responding on target port."""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/system/mode")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def find_available_port(start_port: int = 8080, max_attempts: int = 10) -> int:
    """Find next open port if start_port is blocked."""
    for p in range(start_port, start_port + max_attempts):
        if not is_port_in_use(p):
            return p
    return start_port


def auto_open_browser(url: str, delay: float = 2.0):
    """Wait for server to bind port, then open web browser."""
    def _open():
        time.sleep(delay)
        print(f"\n[+] Opening browser at: {url}")
        try:
            webbrowser.open(url)
        except Exception:
            pass

    t = threading.Thread(target=_open, daemon=True)
    t.start()


def main():
    # Enable local development mode so authentication is bypassed for local UI viewing
    os.environ["HIRETRACE_DEV_MODE"] = "1"
    os.environ.setdefault("HIRETRACE_LOG_LEVEL", "INFO")

    print(banner)
    ollama_proc = start_ollama_service()
    verify_model()

    target_port = APP_PORT
    if is_port_in_use(target_port):
        if is_hiretrace_running(target_port):
            active_url = f"http://127.0.0.1:{target_port}"
            print(f"\n[+] HireTrace server is already actively running at {active_url}.")
            print(f"[+] Launching browser to active dashboard...")
            try:
                webbrowser.open(active_url)
            except Exception:
                pass
            print(f"\n{'='*65}")
            print(f"  HireTrace Live Dashboard: {active_url}")
            print(f"  (Background instance is running and healthy)")
            print(f"{'='*65}\n")
            return
        else:
            new_port = find_available_port(target_port + 1)
            print(f"[!] Port {target_port} is already bound by another process. Automatically using port {new_port}.")
            target_port = new_port

    target_url = f"http://127.0.0.1:{target_port}"
    auto_open_browser(target_url, delay=1.8)

    print(f"\n{'='*65}")
    print(f"  HireTrace Live Dashboard: {target_url}")
    print(f"  Press Ctrl+C at any time to shut down.")
    print(f"{'='*65}\n")

    root_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(root_dir)

    # Launch FastAPI / Uvicorn server in foreground
    server_env = os.environ.copy()
    server_env["HIRETRACE_DEV_MODE"] = "1"
    cmd = [sys.executable, "-m", "ui.server", str(target_port)]
    try:
        subprocess.run(cmd, env=server_env)
    except KeyboardInterrupt:
        print("\n[*] Shutting down HireTrace...")

    finally:
        if ollama_proc:
            try:
                ollama_proc.terminate()
            except Exception:
                pass
        print("[+] Done. Goodbye!")


if __name__ == "__main__":
    main()
