import multiprocessing

# Server socket
bind = "127.0.0.1:8086"

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 120
keepalive = 5

# Logging
accesslog = "/var/log/aerovip/access.log"
errorlog = "/var/log/aerovip/error.log"
loglevel = "info"

# Process naming
proc_name = "aerovip"

# Don't preload — let each worker create its own app so the background
# cache thread starts after fork (threads don't survive fork).
preload_app = False
daemon = False
