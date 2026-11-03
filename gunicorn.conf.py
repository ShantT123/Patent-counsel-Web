import os
bind = f"0.0.0.0:{os.environ.get('PORT', '8080')}"
workers = 1
threads = 8
timeout = 150
graceful_timeout = 120
accesslog = None
errorlog = '-'
