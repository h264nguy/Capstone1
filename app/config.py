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


# Per-drink hardcoded seconds used for menu ETA + live display ETA
HARDCODED_DRINK_SECONDS = {
    "classic_fusion": 17.8,
    "cola_spark": 17.8,
    "chaos_punch": 13.3,
    "dark_amber": 17.8,
    "crystal_chill": 11.7,
    "voltage_fizz": 12.7,
    "amber_storm": 17.8,
    "citrus_shine": 15.0,
    "citrus_cloud": 13.3,
    "energy_sunrise": 16.9,
    "golden_breeze": 14.2,
    "sunset_fizz": 12.7,
    "sparkling_citrus": 10.7,
    "sparkling_citrus_mix": 10.7,
    "tropical_charge": 12.7,
    "base_water": 35.1,
    "base_sprite": 29.0,
    "base_ginger_ale": 32.0,
    "base_orange_juice": 30.0,
    "base_coca_cola": 35.6,
    "base_red_bull": 38.0
}

# Manual flush workflow state
MACHINE_STATE_FILE = DATA_DIR / 'machine_state.json'
