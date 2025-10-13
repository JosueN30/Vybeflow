# FIX 1: Add the application entry point
wsgi_app = "wsgi:app" 

# Server socket
bind = "0.0.0.0:8000"
# ... (rest of process and logging config)

# Process naming
proc_name = "vybeflow"

# Server mechanics
daemon = False
# FIX 2: Use a persistent location for the PID file
pidfile = "/var/run/vybeflow/vybeflow.pid" 
# FIX 3: Set a dedicated, non-root user for security
user = "vybeflow" 
group = "vybeflow"
tmp_upload_dir = None
# Gunicorn configuration file for VybeFlow production

# FIX: Add the application entry point
wsgi_app = "wsgi:app"

# Server socket
bind = "0.0.0.0:8000"
# ... (backlog, worker_class, connections, timeout, keepalive, security limits remain the same)

# Process naming
proc_name = "vybeflow"

# Server mechanics
daemon = False
# FIX: Use a persistent location for the PID file
pidfile = "/var/run/vybeflow/vybeflow.pid"
# FIX: Set a dedicated, non-root user for security
user = "vybeflow"
group = "vybeflow"
tmp_upload_dir = None
# Gunicorn configuration file for VybeFlow production

# Server socket
bind = "0.0.0.0:8000"
backlog = 2048

# Worker processes
workers = 4
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2

# Restart workers after this many requests, to prevent memory leaks
max_requests = 1000
max_requests_jitter = 100

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = "vybeflow"

# Server mechanics
daemon = False
pidfile = "/tmp/vybeflow.pid"
user = None
group = None
tmp_upload_dir = None

# SSL (uncomment if you have SSL certificates)
# keyfile = "/path/to/keyfile"
# certfile = "/path/to/certfile"
