"""Run browser/MCP checks against a test PostgreSQL DB or explicit disposable SQLite smoke DB."""
import argparse
import tempfile
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
from urllib.request import urlopen
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite-smoke", action="store_true", help="Use a new disposable async SQLite database; does not verify PostgreSQL")
    parser.add_argument("--visual", action="store_true", help="Capture desktop/tablet/mobile light/dark screenshots after the workflow")
    args = parser.parse_args()
    env = dict(os.environ)
    if args.visual:
        env["E2E_VISUAL_DIR"] = str(ROOT / ".impeccable/review/current")
    if args.sqlite_smoke:
        scratch = ROOT / "test-temp"
        scratch.mkdir(exist_ok=True)
        database = Path(tempfile.mkdtemp(prefix="e2e-sqlite-", dir=scratch)) / "smoke.db"
        env["DATABASE_URL"] = "sqlite+aiosqlite:///" + database.as_posix()
        print("SQLite browser/MCP smoke mode; PostgreSQL is NOT verified.", flush=True)
    url = make_url(env.get("DATABASE_URL", ""))
    if not args.sqlite_smoke and (url.drivername != "postgresql+asyncpg" or not (url.database or "").endswith("_test")):
        raise RuntimeError("DATABASE_URL must target disposable PostgreSQL ending in _test")
    if env.get("ENVIRONMENT", "development") != "development":
        raise RuntimeError("Tests require isolated development configuration")
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node is required")
    env.update({"PYTHONPATH": str(ROOT / "backend"), "ENVIRONMENT": "development", "DEMO_MODE": "true", "PAYMENT_PROVIDER": "mock", "COOKIE_SECURE": "false", "FRONTEND_URL": "http://localhost:3000", "E2E_BASE_URL": "http://localhost:3000", "E2E_API_URL": "http://127.0.0.1:8000/api/v1", "PYTHON_EXECUTABLE": sys.executable})
    env.update({"STRIPE_SECRET_KEY": "", "STRIPE_WEBHOOK_SECRET": "", "STRIPE_CONNECT_ENABLED": "false", "PUBLIC_BOOKINGS_ENABLED": "false", "LLM_PROVIDER": "deterministic"})
    env["MAIL_DIR"] = str(ROOT / ".dependency-cache/e2e-mail")
    env["UPLOAD_DIR"] = str(ROOT / ".dependency-cache/e2e-uploads")
    env["E2E_MAIL_DIR"] = env["MAIL_DIR"]
    env["E2E_ADMIN_EMAIL"] = "admin-" + secrets.token_hex(6) + "@example.com"
    env["E2E_ADMIN_PASSWORD"] = secrets.token_urlsafe(32)
    subprocess.run([sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", "head"], cwd=ROOT, env=env, check=True)
    subprocess.run([sys.executable, "-m", "app.cli", "admin", "--email", env["E2E_ADMIN_EMAIL"], "--password-env", "E2E_ADMIN_PASSWORD"], cwd=ROOT, env=env, check=True)
    subprocess.run([sys.executable, "-m", "app.cli", "seed", "--password-env", "E2E_ADMIN_PASSWORD"], cwd=ROOT, env=env, check=True)
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    processes = []
    try:
        with open(ROOT / "backend-e2e.log", "w") as backend_log, open(ROOT / "frontend-e2e.log", "w") as frontend_log:
            processes.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"], cwd=ROOT, env=env, stdout=backend_log, stderr=subprocess.STDOUT, creationflags=flags))
            processes.append(subprocess.Popen([node, str(ROOT / "frontend/node_modules/next/dist/bin/next"), "start", "--hostname", "127.0.0.1"], cwd=ROOT / "frontend", env=env, stdout=frontend_log, stderr=subprocess.STDOUT, creationflags=flags))
            deadline = time.monotonic() + 50
            while True:
                if any(p.poll() is not None for p in processes):
                    raise RuntimeError("A test service exited. Inspect E2E logs.")
                try:
                    with urlopen("http://127.0.0.1:8000/health/ready", timeout=2), urlopen("http://localhost:3000", timeout=2):
                        break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Services did not become ready; inspect E2E logs") from None
                    time.sleep(.5)
            subprocess.run([node, str(ROOT / "frontend/node_modules/@playwright/test/cli.js"), "test"], cwd=ROOT / "frontend", env=env, check=True)
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
