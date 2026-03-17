from pathlib import Path
import os


# =========================
# APP CONFIG
# =========================

# ESP8266 / ESP32 (optional, local network)
ESP_BASE_URL = "http://172.20.10.3"  # change to your ESP IP
ESP_ENDPOINT = "/make-drink"         # must match ESP route

# Session secret (change this before deploying)
SESSION_SECRET = "CHANGE_THIS_TO_ANY_RANDOM_SECRET_123"

# Project paths
BASE_DIR = Path(__file__).resolve().parent
REPO_DIR = BASE_DIR.parent

STATIC_DIR = REPO_DIR / "static"
DATA_DIR = BASE_DIR / "data"

USERS_FILE = DATA_DIR / "users.json"
ORDERS_FILE = DATA_DIR / "orders.json"
DRINKS_FILE = DATA_DIR / "drinks.json"

# =========================
# ESP POLLING (for published / online deployments)
# =========================
# Put this in Render Environment Variables as ESP_POLL_KEY.
# Your ESP8266 uses the SAME value in its ESP_KEY.
ESP_POLL_KEY = os.getenv("ESP_POLL_KEY", "win12345key")

# Where queued orders are stored for the ESP to pick up.
ESP_QUEUE_FILE = DATA_DIR / "esp_queue.json"

# Completed orders (archive)
ESP_DONE_FILE = DATA_DIR / "esp_done.json"

# =========================
# ETA MODEL (Capstone)
# =========================
# Simple, explainable estimation model:
#   order_seconds = ETA_ORDER_OVERHEAD_SEC + total_qty * ETA_SECONDS_PER_DRINK
# Tune these values to match your physical pump timing.

ETA_ORDER_OVERHEAD_SEC = int(os.getenv("ETA_ORDER_OVERHEAD_SEC", "8"))
ETA_SECONDS_PER_DRINK = int(os.getenv("ETA_SECONDS_PER_DRINK", "25"))


# Prep time between drinks/orders for the machine to reset
ESP_PREP_SECONDS = int(os.getenv('ESP_PREP_SECONDS', '10'))
