"""Concurrent sign-in load test.

Creates N test accounts (loadtest-0001@nacb.test …) if missing, then signs them ALL in at the same time against a
running server and reports success rate and latency.

    python scripts/loadtest.py --users 1000 --concurrency 1000 --base http://127.0.0.1:8010

Run only against a local or staging server. Remove test accounts afterwards with --cleanup.
"""
import argparse
import http.cookiejar
import os
import re
import statistics
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import secrets as _secrets
# Random per run; the generated load-test accounts are deleted with --cleanup.
PASSWORD = os.environ.get("NACB_LOADTEST_PASSWORD") or ("Lt-" + _secrets.token_urlsafe(12) + "7!")


def setup_users(n):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django
    django.setup()
    from django.contrib.auth.hashers import make_password
    from accounts.models import User
    h = make_password(PASSWORD)
    existing = set(User.objects.filter(email__startswith="loadtest-").values_list("email", flat=True))
    new = [User(email=f"loadtest-{i:04d}@nacb.test", password=h, role=User.ARTIST, first_name="Load", last_name=str(i))
           for i in range(n) if f"loadtest-{i:04d}@nacb.test" not in existing]
    User.objects.bulk_create(new, batch_size=500)
    return len(new)


def cleanup():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django
    django.setup()
    from accounts.models import User
    print("deleted", User.objects.filter(email__startswith="loadtest-").delete())


def one_login(base, i, barrier):
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    html = opener.open(f"{base}/accounts/login/", timeout=300).read().decode()
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html).group(1)
    data = urllib.parse.urlencode({"csrfmiddlewaretoken": token, "email": f"loadtest-{i:04d}@nacb.test",
                                   "password": PASSWORD, "next": "/dashboard/"}).encode()
    req = urllib.request.Request(f"{base}/accounts/login/", data=data, headers={"Referer": f"{base}/accounts/login/"})
    barrier.wait()  # every client fires its sign-in at the same instant
    t = time.perf_counter()
    resp = opener.open(req, timeout=600)
    body = resp.read().decode(errors="ignore")
    ok = "/dashboard/" in resp.url and "Sign in |" not in body
    return ok, time.perf_counter() - t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=1000)
    ap.add_argument("--concurrency", type=int, default=1000)
    ap.add_argument("--base", default="http://127.0.0.1:8010")
    ap.add_argument("--cleanup", action="store_true")
    a = ap.parse_args()
    if a.cleanup:
        return cleanup()
    print("created", setup_users(a.users), "test accounts")
    barrier = threading.Barrier(min(a.users, a.concurrency))
    start = time.perf_counter()
    results = []
    with ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        futs = [ex.submit(one_login, a.base, i, barrier) for i in range(a.users)]
        for f in futs:
            try:
                results.append(f.result())
            except Exception as e:  # noqa: BLE001
                results.append((False, 0.0))
                print("error:", type(e).__name__, str(e)[:120])
    wall = time.perf_counter() - start
    ok = [t for s, t in results if s]
    print(f"\nSign-ins attempted: {len(results)}  succeeded: {len(ok)}  failed: {len(results) - len(ok)}")
    if ok:
        q = statistics.quantiles(ok, n=100)
        print(f"Latency  median {statistics.median(ok):.1f}s  p95 {q[94]:.1f}s  max {max(ok):.1f}s")
    print(f"Wall time {wall:.1f}s  throughput {len(ok) / wall:.1f} sign-ins/s")


if __name__ == "__main__":
    main()
