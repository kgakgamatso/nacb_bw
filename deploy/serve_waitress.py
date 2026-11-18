"""Production-style WSGI server for Windows hosts (use gunicorn on Linux, see deploy/gunicorn.conf.py).

    python deploy/serve_waitress.py --port 8010 --threads 64
Put IIS / nginx in front for TLS and static files."""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from waitress import serve  # noqa: E402

from config.wsgi import application  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8010)
    ap.add_argument("--threads", type=int, default=64)
    a = ap.parse_args()
    # connection_limit and backlog sized for 1000+ simultaneous clients
    serve(application, host=a.host, port=a.port, threads=a.threads, connection_limit=4000, backlog=4096,
          channel_timeout=300, asyncore_use_poll=True)
