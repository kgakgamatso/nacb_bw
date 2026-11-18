# Linux production: gunicorn -c deploy/gunicorn.conf.py config.wsgi
import multiprocessing

bind = "127.0.0.1:8000"
workers = multiprocessing.cpu_count() * 2 + 1      # one process per core (+1), password hashing is CPU bound
threads = 8                                        # gthread worker: 8 concurrent requests per process
worker_class = "gthread"
backlog = 4096                                     # queue for bursts of 1000+ simultaneous connections
timeout = 120
keepalive = 5
max_requests = 5000                                # recycle workers to avoid memory creep
max_requests_jitter = 500
accesslog = "-"
