"""Run backend + frontend with one command.

Cross-platform. Auto-detects the venv. Pipes both outputs to this terminal
with color-coded prefixes. Ctrl+C cleanly kills both.

Usage (from project root):
    python run.py                  # backend + frontend (next dev, HMR)
    python run.py --prod           # backend + frontend (next start, built)
    python run.py --build          # build frontend first, then run
    python run.py --backend-only   # just the API (no UI)
    python run.py --frontend-only  # just the UI (no API)
    python run.py --port 9000      # change API port
    python run.py --no-color       # plain output (for CI / piping)

After the first run, the helpers `run.bat` and `run.ps1` let you launch it
with a single command from any Windows shell.
"""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import IO, Optional

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


# ----- colors (auto-disabled on non-tty or with --no-color) -----

class C:
    RESET = "\033[0m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"


def colorize(enabled: bool):
    if not enabled:
        # Strip any ANSI from the class attrs by mapping to empty strings.
        for k in ("RESET", "DIM", "BOLD", "RED", "GREEN", "YELLOW",
                  "BLUE", "MAGENTA", "CYAN"):
            setattr(C, k, "")


# ----- venv detection -----

def find_venv_python() -> Optional[Path]:
    """Look for backend/.venv/Scripts/python.exe (Windows) or
    backend/.venv/bin/python (Unix). Returns None if not found."""
    base = BACKEND / ".venv"
    candidates = [
        base / "Scripts" / "python.exe",   # Windows
        base / "Scripts" / "python",       # Windows (no .exe)
        base / "bin" / "python",           # Unix
        base / "bin" / "python3",          # Unix
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def find_node_npm() -> tuple[Optional[str], Optional[str]]:
    """Return (node, npm) absolute paths or (None, None)."""
    return shutil.which("node"), shutil.which("npm")


# ----- stream pump -----

class Pump:
    """Reads a subprocess stream line-by-line, prefixes each line, and
    writes to our stdout. Dies when the stream closes."""

    def __init__(self, stream: IO[str], prefix: str, color: str, use_color: bool):
        self.stream = stream
        self.prefix = prefix
        self.color = color
        self.use_color = use_color
        self._closed = False

    def run(self) -> None:
        try:
            for line in iter(self.stream.readline, ""):
                if not line:
                    break
                self._write(line)
        except (ValueError, OSError):
            # stream closed underneath us
            pass
        finally:
            try:
                self.stream.close()
            except Exception:
                pass

    def _write(self, line: str) -> None:
        line = line.rstrip("\n")
        if not line:
            return
        if self.use_color:
            sys.stdout.write(f"{C.DIM}{self.color}{self.prefix}{C.RESET} {line}\n")
        else:
            sys.stdout.write(f"{self.prefix} {line}\n")
        sys.stdout.flush()


# ----- process group helper -----

def _list_children(parent_pid: int) -> list[int]:
    """Return all PIDs whose parent is `parent_pid` (Windows + Unix)."""
    children: list[int] = []
    if os.name == "nt":
        try:
            out = subprocess.check_output(
                ["wmic", "process", "where",
                 f"ParentProcessId={parent_pid}",
                 "get", "ProcessId"],
                text=True, stderr=subprocess.DEVNULL,
            )
            for line in out.splitlines():
                line = line.strip()
                if line.isdigit():
                    children.append(int(line))
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
    else:
        try:
            import psutil  # type: ignore
            children = [p.pid for p in psutil.Process(parent_pid).children(recursive=True)]
        except (ImportError, Exception):
            pass
    return children


def kill_proc(proc: subprocess.Popen, name: str) -> None:
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            # /T = terminate the whole process tree, /F = force
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                capture_output=True, check=False,
            )
            # Some runtimes (uvicorn with --reload) use multiprocessing spawn,
            # which detaches the child from the parent's job object. Find and
            # kill those stragglers by parent PID.
            for child_pid in _list_children(proc.pid):
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(child_pid)],
                    capture_output=True, check=False,
                )
        else:
            proc.terminate()
    except Exception as e:
        print(f"[runner] failed to kill {name}: {e}", file=sys.stderr)


# ----- backend launcher -----

def start_backend(python: Path, port: int, use_color: bool) -> subprocess.Popen:
    cmd = [
        str(python), "-m", "uvicorn", "main:app",
        "--host", "127.0.0.1", "--port", str(port),
    ]
    if "--reload" not in sys.argv:
        cmd.append("--reload")
    print(f"[runner] backend  : {' '.join(cmd)}")
    return subprocess.Popen(
        cmd,
        cwd=str(BACKEND),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        # New process group on Windows so taskkill /T can take down children.
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )


# ----- frontend launcher -----

def start_frontend(mode: str, port: int, use_color: bool) -> Optional[subprocess.Popen]:
    node, npm = find_node_npm()
    if not (node and npm):
        print("[runner] node/npm not found on PATH; skipping frontend",
              file=sys.stderr)
        return None

    if mode == "dev":
        cmd = ["npm", "run", "dev", "--", "-p", str(port)]
        cwd = str(FRONTEND)
    else:  # prod
        cmd = ["npm", "run", "start", "--", "-p", str(port)]
        cwd = str(FRONTEND)

    print(f"[runner] frontend : {' '.join(cmd)}")
    return subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        shell=(os.name == "nt"),  # npm.cmd on Windows
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )


# ----- main loop -----

def run(args: argparse.Namespace) -> int:
    use_color = sys.stdout.isatty() and not args.no_color
    colorize(use_color)

    # ---- preflight ----
    if not args.frontend_only:
        # If we're here, this script is already running under some python;
        # we don't need to check for python-on-PATH. We do need the venv.
        py = find_venv_python()
        if py is None:
            print(
                f"[runner] ERROR: backend/.venv not found at "
                f"{BACKEND / '.venv'}.\n"
                f"        Run setup first:\n"
                f"          Windows: .\\setup.ps1\n"
                f"          Unix   : bash setup.sh\n"
                f"        Or manually:\n"
                f"          python -m venv backend/.venv\n"
                f"          backend\\.venv\\Scripts\\python.exe -m pip install -r "
                f"backend/requirements.txt",
                file=sys.stderr,
            )
            return 2
        print(f"[runner] venv    : {py}")

    if not args.backend_only and not (FRONTEND / "node_modules").exists():
        print(
            f"[runner] frontend/node_modules missing. Run:\n"
            f"        cd frontend && npm install",
            file=sys.stderr,
        )
        return 2

    # ---- optional build ----
    if args.build and not args.frontend_only:
        print("[runner] building frontend…")
        r = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(FRONTEND), shell=(os.name == "nt"),
        )
        if r.returncode != 0:
            print("[runner] frontend build failed", file=sys.stderr)
            return r.returncode

    # ---- start processes ----
    procs: list[tuple[str, subprocess.Popen]] = []

    if not args.frontend_only:
        py = find_venv_python()
        assert py is not None
        backend = start_backend(py, args.port, use_color)
        procs.append(("backend", backend))
        # Pump backend output
        b_pump = Pump(backend.stdout, "[backend] ",
                      C.GREEN if use_color else "", use_color)
        threading.Thread(target=b_pump.run, daemon=True).start()

    if not args.backend_only:
        mode = "prod" if args.prod else "dev"
        frontend = start_frontend(mode, 3000, use_color)
        if frontend is not None:
            procs.append(("frontend", frontend))
            f_pump = Pump(frontend.stdout, "[frontend]",
                          C.CYAN if use_color else "", use_color)
            threading.Thread(target=f_pump.run, daemon=True).start()

    # ---- wait, with graceful Ctrl+C ----
    if not procs:
        print("[runner] nothing to run", file=sys.stderr)
        return 1

    api_url = f"http://localhost:{args.port}"
    ui_url = "http://localhost:3000"
    print()
    print(f"[runner] {C.BOLD}API:{C.RESET} {api_url}/api/health")
    if not args.backend_only:
        print(f"[runner] {C.BOLD}UI :{C.RESET} {ui_url}")
    print(f"[runner] press {C.BOLD}Ctrl+C{C.RESET} to stop everything\n")

    stop = threading.Event()

    def _signal_handler(signum, frame):
        stop.set()

    try:
        signal.signal(signal.SIGINT, _signal_handler)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _signal_handler)
    except ValueError:
        # Not in main thread (shouldn't happen here)
        pass

    try:
        while not stop.is_set():
            for name, p in procs:
                rc = p.poll()
                if rc is not None:
                    print(
                        f"[runner] {name} exited with code {rc}; "
                        f"stopping everything",
                        file=sys.stderr,
                    )
                    stop.set()
                    break
            if stop.is_set():
                break
            time.sleep(0.3)
    except KeyboardInterrupt:
        stop.set()

    # ---- shutdown ----
    print("\n[runner] shutting down…")
    for name, p in procs:
        kill_proc(p, name)

    # Give them 3s to exit cleanly, then SIGKILL
    deadline = time.time() + 3
    while time.time() < deadline:
        if all(p.poll() is not None for _, p in procs):
            break
        time.sleep(0.1)
    for name, p in procs:
        if p.poll() is None:
            try:
                p.kill()
            except Exception:
                pass

    print("[runner] done")
    return 0


# ----- arg parsing -----

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run RoastGPT backend + frontend in one terminal.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--prod", action="store_true",
                   help="Use `next start` (production) instead of `next dev`")
    p.add_argument("--build", action="store_true",
                   help="Run `next build` before starting the frontend")
    p.add_argument("--backend-only", action="store_true",
                   help="Only run the backend API")
    p.add_argument("--frontend-only", action="store_true",
                   help="Only run the frontend (assumes backend is up)")
    p.add_argument("--port", type=int, default=8000,
                   help="Backend port (default: 8000)")
    p.add_argument("--no-color", action="store_true",
                   help="Disable ANSI colors in the output")
    p.add_argument("--no-reload", action="store_true",
                   help="Disable uvicorn --reload on the backend")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(run(parse_args()))
