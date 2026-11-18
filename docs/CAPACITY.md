# Capacity: 1,000+ simultaneous sign-ins

## What was changed in the application
- **Shared cache** (Redis via `NACB_REDIS_URL`, otherwise a database cache table) holds sessions, sign-in lockout counters and rate limits, so every server process sees the same state. The previous in-memory cache only worked with a single process.
- **Sessions** use `cached_db`: they are read from the cache and saved in the database, so they survive restarts and work across several app servers.
- **Database connections** are reused (`CONN_MAX_AGE`) with health checks.
- **Server configs**: `deploy/gunicorn.conf.py` (Linux: one process per CPU core plus threads, 4,096 connection backlog) and `deploy/serve_waitress.py` (Windows).
- **Load test**: `scripts/loadtest.py` signs in N accounts at exactly the same moment and reports success rate and latency.

## Test result on a developer laptop (17 Nov 2026)
Setup: one waitress process on a 14-core laptop, SQLite, no reverse proxy, 1,000 clients released at the same instant.

| Result | Value |
|---|---|
| Sign-ins succeeded | 650 of 1,000 |
| Refused connections | 350 |
| Median latency | 89 s |
| Throughput | 4.4 sign-ins per second |

**Why it fell short:**
1. **Refused connections.** Windows' connection queue overflowed because there was no reverse proxy in front.
2. **Throughput.** Each password check costs about 0.6 s of CPU on this laptop. This cost is intentional: it protects passwords against brute-force attacks. On top of that, SQLite allows only one write at a time, and every sign-in writes a session and an audit entry.

The laptop setup is not the production design. The test is included so the real servers can be measured before go-live.

## Production design that meets the target
| Component | Recommendation |
|---|---|
| Reverse proxy | nginx (or IIS with ARR) for TLS, static files and connection queuing |
| App servers | 2 × 8 vCPU VMs running gunicorn (17 processes × 8 threads each) |
| Database | PostgreSQL 15+, 4 vCPU / 16 GB, with PgBouncer |
| Cache / sessions | Redis 7, 2 GB |
| File storage | Private volume or object storage for `PRIVATE_MEDIA_ROOT`, backed up nightly |

Rough sizing: 1,000 sign-ins × ~0.3 CPU-seconds each on server-grade cores ≈ 300 CPU-seconds. With 16 cores, a burst of 1,000 people pressing "Sign in" at the same instant clears in about 20 seconds. Normal browsing by 1,000+ signed-in users costs only milliseconds per page.

## Re-running the test on staging
```bash
python deploy/serve_waitress.py --port 8010 --threads 96      # or gunicorn -c deploy/gunicorn.conf.py config.wsgi
python scripts/loadtest.py --users 1000 --concurrency 1000 --base https://staging.nacb.example
python scripts/loadtest.py --cleanup
```
Pass criteria: 100% success, 95th-percentile sign-in time under 30 s during the simultaneous burst, and normal page loads under 3 s.
