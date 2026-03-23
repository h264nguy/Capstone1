# Smart Bartender (Merged + Modular)

This repo merges your uploaded ZIP versions into **one** FastAPI project with a clean structure (pages + APIs + ML logic separated).

## Run locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Open:
- `http://localhost:8000/login`

Default user created automatically:
- **username:** admin
- **password:** 1234

## APIs

- `GET /api/drinks` – returns `drinks.json`
- `POST /checkout` – save order history (and best-effort send to ESP)
- `GET /api/history` – current user's order history
- `GET /api/recommendations?k=5` – drink recommendations (collaborative filtering style)

## Where things live

- `app/main.py` – app wiring
- `app/routers/*` – routes (pages + APIs)
- `app/core/*` – auth + storage
- `app/ml/recommender.py` – recommendation logic
- `app/data/*` – `users.json`, `orders.json`, `drinks.json`
- `static/` – images (background)

## Legacy versions

All uploaded ZIP versions were copied into `legacy_versions/` (cleaned of `.git`, `.venv`, cache files) so you still have every old codebase in one place.


## ESP8266 (single drink slot + 10s prep)

An example ESP8266 sketch is included at `esp/SmartBartender_ESP8266_Prep10s.ino`.
Set `WIFI_SSID`, `WIFI_PASS`, `SERVER_BASE`, and `ESP_KEY` (must match server `ESP_POLL_KEY`).
The sketch polls every 10 seconds when idle, and waits 10 seconds after each drink before requesting the next one.
