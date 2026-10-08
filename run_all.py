"""
Start every service at once.

    python run_all.py

Ctrl+C stops them all.

The Retrieval agent is not listed. The Orchestrator launches it over
MCP whenever it needs to search.
"""
import subprocess
import sys
import time

import requests

SERVICES = [
    ("Analysis    ", 8002,
     [sys.executable, "-m", "uvicorn",
      "agents.analysis.main:app", "--port", "8002"]),
    ("Orchestrator", 8000,
     [sys.executable, "-m", "uvicorn",
      "agents.orchestrator.main:app", "--port", "8000"]),
    ("Guardian    ", 8001,
     [sys.executable, "-m", "uvicorn",
      "agents.guardian.main:app", "--port", "8001"]),
]

processes = []


def wait_for(process, port, name, timeout=90):
    """The Analysis agent loads models, so give it time."""
    start = time.time()
    while time.time() - start < timeout:
        if process.poll() is not None:
            print(f"  {name} crashed (exit code {process.returncode})")
            return False
        try:
            r = requests.get(f"http://127.0.0.1:{port}/health", timeout=2)
            if r.status_code == 200:
                print(f"  {name} ready")
                return True
        except requests.RequestException:
            pass
        time.sleep(2)

    print(f"  {name} did not start in time")
    return False


try:
    for name, port, command in SERVICES:
        print(f"Starting {name}...")
        process = subprocess.Popen(command)
        processes.append(process)
        if not wait_for(process, port, name):
            raise SystemExit(f"{name.strip()} failed to start, see the error above")

    print("\nStarting the interface...")
    processes.append(
        subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", "frontend/app.py"]
        )
    )

    print("\n" + "=" * 52)
    print("CineMate is running:  http://localhost:8501")
    print("Ctrl+C to stop everything")
    print("=" * 52 + "\n")

    for p in processes:
        p.wait()

except (KeyboardInterrupt, SystemExit) as e:
    if isinstance(e, SystemExit):
        print(f"\n{e}")
    print("\nStopping...")
    for p in processes:
        p.terminate()
    for p in processes:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
    print("Stopped.")