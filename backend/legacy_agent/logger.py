import logging
import os
import sys

os.makedirs("agent/logs", exist_ok=True)

# Configure root logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

# File handler
file_handler = logging.FileHandler("agent/logs/agent.log")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

def get_logger(name):
    return logging.getLogger(name)
