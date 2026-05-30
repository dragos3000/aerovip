# Server socket
bind = "127.0.0.1:8086"

# Worker processes.
# NOTE: this is a SHARED 96-core box running several apps, so cpu_count()*2+1
# would spawn ~193 workers — massive memory use and slowness. A small fixed pool
# of threaded workers is plenty here and handles blocking weather I/O well.
workers = 3
worker_class = "gthread"
threads = 4
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
