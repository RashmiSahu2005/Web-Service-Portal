#!/usr/bin/env python3
import os
import sys

if __name__ == '__main__':
    print("Starting Celery worker for ApplicationHub...")
    print("Ensure Redis is running (e.g. redis-server) before starting this worker.")
    
    # Run the Celery worker
    exit_code = os.system("celery -A app.services.celery_app.celery_app worker --loglevel=info")
    sys.exit(exit_code)
