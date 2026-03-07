from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List
from pathlib import Path
import hashlib
import json
from collections import Counter
from datetime import datetime
import httpx

from starlette.middleware.sessions import SessionMiddleware

app = FastAPI()

# =========================
# CONFIG
# =========================
CANVA_URL = "https://smartbartender.my.canva.site/dag-sgpflmm"

ESP_BASE_URL = "http://172.20.10.3"   # your ESP IP (works locally)
ESP_ENDPOINT = "/make-drink"

# =========================
# FILES + STATIC
# =========================
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

USERS_FILE = BASE_DIR / "users.json"
ORDERS_FILE = BASE_DIR / "orders.json"

# Drinks are auto-loaded from this file
DRINKS_FILE = BASE_DIR / "drinks.json"

# =========================
# SESSIONS
# =========================
# NOTE: SessionMiddleware requires: pip install itsdangerous
app.add_middleware(SessionMiddleware, secret_key="CHANGE_THIS_TO_ANY_RANDOM_SECRET_123")

def current_user(request: Request):
    return request.session.get("user")

def require_login(request: Request):
    return current_user(request) is not None

# =========================
# USERS (LOGIN)
# =========================
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def load_users() -> dict:
    if not USERS_FILE.exists():
        return {}
    txt = USERS_FILE.read_text().strip()
    if not txt:
        return {}
    return json.loads(txt)

def save_users(users: dict):
    USERS_FILE.write_text(json.dumps(users, indent=2))

def init_default_admin():
    users = load_users()
    if "admin" not in users:
        users["admin"] = hash_password("1234")
        save_users(users)

init_default_admin()

# =========================
# DRINKS (MENU)
# =========================
def load_drinks() -> list:
    """Load drinks from drinks.json. Returns [] if missing."""
    if not DRINKS_FILE.exists():
        return []
    raw = DRINKS_FILE.read_text().strip()
    if not raw:
        return []
    try:
        drinks = json.loads(raw)
        if not isinstance(drinks, list):
            return []
        cleaned = []
        for d in drinks:
            if not isinstance(d, dict):
                continue
            did = str(d.get("id", "")).strip()
            name = str(d.get("name", "")).strip()
            cal = d.get("calories", 0)
            if not did or not name:
                continue
            try:
                cal = int(cal)
            except Exception:
                cal = 0
            cleaned.append({"id": did, "name": name, "calories": cal})
        return cleaned
    except Exception:
        return []

def ensure_drinks_file():
    """Create drinks.json with your full drink list if it doesn't exist."""
    if DRINKS_FILE.exists():
        return

    starter = [
        {"id": "amber_storm", "name": "Amber Storm", "calories": 104},
        {"id": "classic_fusion", "name": "Classic Fusion", "calories": 76},
        {"id": "chaos_punch", "name": "Chaos Punch", "calories": 204},
        {"id": "crystal_chill", "name": "Crystal Chill", "calories": 56},
        {"id": "cola_spark", "name": "Cola Spark", "calories": 81},
        {"id": "dark_amber", "name": "Dark Amber", "calories": 65},
        {"id": "voltage_fizz", "name": "Voltage Fizz", "calories": 117},
        {"id": "citrus_cloud", "name": "Citrus Cloud", "calories": 84},
        {"id": "golden_breeze", "name": "Golden Breeze", "calories": 64},
        {"id": "sparkling_citrus_mix", "name": "Sparkling Citrus Mix", "calories": 118},
        {"id": "citrus_shine", "name": "Citrus Shine", "calories": 71},
        {"id": "energy_sunrise", "name": "Energy Sunrise", "calories": 67},
        {"id": "sunset_fizz", "name": "Sunset Fizz", "calories": 87},
        {"id": "tropical_charge", "name": "Tropical Charge", "calories": 86},
        {"id": "base_orange_juice", "name": "Orange Juice", "calories": 45},
        {"id": "base_water", "name": "Water", "calories": 0},
        {"id": "base_coca_cola", "name": "Coca-Cola", "calories": 140},
        {"id": "base_sprite", "name": "Sprite", "calories": 140},
        {"id": "base_ginger_ale", "name": "Ginger Ale", "calories": 120},
        {"id": "base_red_bull", "name": "Red Bull", "calories": 110},
    ]

    DRINKS_FILE.write_text(json.dumps(starter, indent=2))

ensure_drinks_file()

# =========================
# ORDERS (HISTORY)
# =========================
def load_orders() -> list:
    if not ORDERS_FILE.exists():
        return []
    raw = ORDERS_FILE.read_text().strip()
    if not raw:
        return []
    return json.loads(raw)

def save_orders(orders: list):
    ORDERS_FILE.write_text(json.dumps(orders, indent=2))

def get_top_drinks_for_user(username: str, limit: int = 3) -> List[str]:
    orders = load_orders()
    counter = Counter()
    for item in orders:
        if item.get("username") == username:
            counter[item.get("drinkName")] += int(item.get("quantity", 1))
    return [name for name, _ in counter.most_common(limit)]

# =========================
# ESP SEND (optional)
# =========================
async def send_to_esp(items: list):
    url = f"{ESP_BASE_URL}{ESP_ENDPOINT}"
    payload = {"items": items}
    timeout = httpx.Timeout(8.0, connect=3.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        return r.json()

# =========================
# MODEL
# =========================
class OrderItem(BaseModel):
    drinkId: str
    drinkName: str
    quantity: int
    calories: int

# =========================
# STYLE
# =========================
STYLE = """
<style>
*{box-sizing:border-box}
body{
  margin:0; padding:0;
  font-family: "Playfair Display", serif;
  background:#000;
  background-image:url('/static/background-1.png');
  background-size:cover;
  background-position:center;
  background-repeat:no-repeat;
  background-attachment:fixed;
  color:#1f130d;
}
a{color:#f5e6d3}
.page{max-width:1100px;margin:0 auto;padding:40px 20px 60px}
h1{
  font-size:46px; letter-spacing:3px;
  text-align:center; margin:0 0 6px;
  color:#f5e6d3;
  text-shadow:0 0 10px rgba(245,230,211,.65),
             0 0 22px rgba(245,230,211,.45),
             0 0 34px rgba(255,190,130,.25);
}
.subtitle-wrap{text-align:center;margin-bottom:18px}
.subtitle{
  display:inline-block;
  padding:6px 14px;
  border-radius:12px;
  background:rgba(0,0,0,.35);
  color:rgba(245,230,211,.92);
  text-shadow:0 0 10px rgba(0,0,0,.75);
  font-size:16px;
}
.overlay{min-height:100vh;display:flex;align-items:center;justify-content:center}
.card{
  background: rgba(0,0,0,0.45);
  border: 1px solid rgba(245,230,211,0.25);
  border-radius: 16px;
  padding: 28px 34px;
  width: 92%;
  max-width: 460px;
  text-align: center;
  box-shadow: 0 0 18px rgba(0,0,0,0.5);
}
input{
  width:85%;max-width:280px;padding:10px;border-radius:10px;border:none;
  margin-bottom:12px;font-size:15px;
}
button{
  border-radius:20px;
  border:1px solid #f5e6d3;
  background:#f5e6d3;
  color:#1f130d;
  padding:10px 18px;
  font-size:14px;
  cursor:pointer;
  margin-top:8px;
  width: 260px;
}
button.secondary{
  background:transparent;
  color:#f5e6d3;
}
.small-text{font-size:13px;margin-top:10px;color:#f5e6d3}
.error{color:#ff6b6b}
.success{color:#7fff7f}

.builder-card{
  background:#fdfaf4;
  border-radius:18px;
  padding:22px 26px 26px;
  box-shadow:0 6px 12px rgba(0,0,0,.2);
}
.row{display:flex;gap:20px;flex-wrap:wrap;margin-bottom:12px}
.col{flex:1;min-width:200px}
label{font-weight:600;font-size:18px}
select,input[type="number"]{
  margin-top:4px;padding:6px 10px;font-size:15px;width:100%;
  border-radius:8px;border:1px solid #b1844a;background:#fff7ea;
}
.btn-row{margin-top:16px;display:flex;flex-wrap:wrap;gap:10px}
.btn-row button{
  width:auto;
  padding:10px 16px;
  border:1px solid #1f130d;
  background:#1f130d;
  color:#fdf5e6;
}
.btn-row button.secondary{
  background:transparent;
  color:#1f130d;
}
.summary-card{
  margin-top:22px;background:#f8eddc;border-radius:14px;padding:16px 20px;font-size:14px;
}
.summary-title{font-weight:700;margin-bottom:6px}
.summary-empty{font-style:italic;color:#5c4935}
</style>
"""

# =========================
# ROUTES
# =========================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    if require_login(request):
        return RedirectResponse("/dashboard", status_code=302)

    return HTMLResponse(f"""
    <html><head><title>Smart Bartender</title>{STYLE}</head>
    <body><div class="overlay"><div class="card">
      <h2 style="color:#f5e6d3;margin:0 0 6px;">SMART BARTENDER</h2>
      <p class="small-text" style="margin-top:0;">Login to access the Canva site + Order Drinks</p>
      <form action="/login" method="get"><button type="submit">Log in</button></form>
      <form action="/register" method="get"><button class="secondary" type="submit">Register</button></form>
    </div></div></body></html>
    """)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=302)

# ---------- Register ----------
@app.get("/register", response_class=HTMLResponse)
async def register_form():
    return HTMLResponse(f"""
    <html><head><title>Register</title>{STYLE}</head>
    <body><div class="overlay"><div class="card">
      <h2 style="color:#f5e6d3;margin:0 0 12px;">Create Account</h2>
      <form method="post">
        <input name="username" placeholder="Username" required><br>
        <input name="password" type="password" placeholder="Password" required><br>
        <button type="submit">Register</button>
      </form>
      <p class="small-text"><a href="/">Back</a></p>
    </div></div></body></html>
    """)

@app.post("/register")
async def register(username: str = Form(...), password: str = Form(...)):
    users = load_users()
    if username in users:
        return HTMLResponse(
            f"<html><head>{STYLE}</head><body><div class='overlay'><div class='card'>"
            f"<h3 class='error'>Username already exists</h3>"
            f"<p class='small-text'><a href='/register'>Try again</a></p>"
            f"</div></div></body></html>"
        )
    users[username] = hash_password(password)
    save_users(users)
    return RedirectResponse("/login", status_code=302)

# ---------- Login ----------
@app.get("/login", response_class=HTMLResponse)
async def login_form():
    return HTMLResponse(f"""
    <html><head><title>Login</title>{STYLE}</head>
    <body><div class="overlay"><div class="card">
      <h2 style="color:#f5e6d3;margin:0 0 12px;">Login</h2>
      <form method="post">
        <input name="username" placeholder="Username" required><br>
        <input name="password" type="password" placeholder="Password" required><br>
        <button type="submit">Log in</button>
      </form>
      <p class="small-text"><a href="/">Back</a></p>
    </div></div></body></html>
    """)

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    users = load_users()
    if username in users and users[username] == hash_password(password):
        request.session["user"] = username
        return RedirectResponse("/dashboard", status_code=302)
    return HTMLResponse(
        f"<html><head>{STYLE}</head><body><div class='overlay'><div class='card'>"
        f"<h3 class='error'>Invalid username or password</h3>"
        f"<p class='small-text'><a href='/login'>Try again</a></p>"
        f"</div></div></body></html>"
    )

# ---------- Dashboard (Canva + Order Drinks) ----------
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    if not require_login(request):
        return RedirectResponse("/login", status_code=302)

    user = current_user(request)

    return HTMLResponse(f"""
    <html><head><title>Dashboard</title>{STYLE}</head>
    <body><div class="overlay"><div class="card">
      <h2 style="color:#f5e6d3;margin:0;">Welcome, {user}!</h2>
      <p class="small-text">Choose what you want to do:</p>

      <button onclick="window.open('{CANVA_URL}', '_blank')">Open Canva Site</button><br>
      <form action="/builder" method="get">
        <button type="submit">Order Drinks</button>
      </form>

      <form action="/history" method="get">
        <button class="secondary" type="submit">My Drink History</button>
      </form>

      <form action="/logout" method="get">
        <button class="secondary" type="submit">Logout</button>
      </form>
    </div></div></body></html>
    """)

# ---------- Builder (Order Page) ----------
@app.get("/builder", response_class=HTMLResponse)
async def builder(request: Request):
    if not require_login(request):
        return RedirectResponse("/login", status_code=302)

    user = current_user(request)

    drinks = load_drinks()
    if not drinks:
        drinks = [
            {"id": "amber_storm", "name": "Amber Storm", "calories": 104},
        ]
    drinks_json = json.dumps(drinks)

    return HTMLResponse(f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"/><title>Signature Mocktail</title>{STYLE}</head>
<body>
<div class="page">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
    <div class="subtitle" style="background:rgba(0,0,0,.45);">
      Logged in as <b>{user}</b>
    </div>
    <div style="display:flex;gap:10px;flex-wrap:wrap;">
      <button class="secondary" onclick="window.location.href='/dashboard'">Dashboard</button>
      <button class="secondary" onclick="window.location.href='/logout'">Logout</button>
    </div>
  </div>

  <h1>SIGNATURE MOCKTAIL</h1>
  <div class="subtitle-wrap">
    <div class="subtitle">Choose your drink (100 mL) and quantity. No need to adjust ratios — recipes are pre-set.</div>
  </div>

  <div class="builder-card">
    <div class="row">
      <div class="col">
        <label for="drinkSelect">Drink</label>
        <select id="drinkSelect"></select>
        <div id="caloriesNote" style="margin-top:6px;font-size:13px;"></div>
      </div>
      <div class="col">
        <label for="quantityInput">Quantity</label>
        <input id="quantityInput" type="number" min="1" value="1" />
      </div>
    </div>

    <div class="btn-row">
      <button id="addDrinkBtn">+ Add Drink</button>
      <button id="viewSummaryBtn" class="secondary">View Order Summary</button>
      <button id="clearBtn" class="secondary">Clear Order</button>
      <button id="checkoutBtn">Complete Order</button>
      <button class="secondary" onclick="window.location.href='/recommendations'">Recommendations</button>
      <button class="secondary" onclick="window.location.href='/history'">My History</button>
    </div>
  </div>

  <div id="summaryCard" class="summary-card">
    <div class="summary-title">Order Summary</div>
    <div id="summaryContent" class="summary-empty">No drinks added yet.</div>
  </div>
</div>

<script>
const DRINKS = {drinks_json};

let cart = [];

const drinkSelect = document.getElementById("drinkSelect");
const caloriesNote = document.getElementById("caloriesNote");
const quantityInput = document.getElementById("quantityInput");
const addDrinkBtn = document.getElementById("addDrinkBtn");
const viewSummaryBtn = document.getElementById("viewSummaryBtn");
const clearBtn = document.getElementById("clearBtn");
const checkoutBtn = document.getElementById("checkoutBtn");
const summaryContent = document.getElementById("summaryContent");

function populateDrinkSelect() {{
  drinkSelect.innerHTML = "";
  DRINKS.forEach((d, idx) => {{
    const opt = document.createElement("option");
    opt.value = d.id;
    opt.textContent = d.name;
    if (idx === 0) opt.selected = true;
    drinkSelect.appendChild(opt);
  }});
}}

function getSelectedDrink() {{
  return DRINKS.find(d => d.id === drinkSelect.value) || DRINKS[0];
}}

function renderSummary() {{
  if (cart.length === 0) {{
    summaryContent.className = "summary-empty";
    summaryContent.textContent = "No drinks added yet.";
    return;
  }}
  summaryContent.className = "";
  summaryContent.innerHTML = "";
  cart.forEach((item, idx) => {{
    const div = document.createElement("div");
    div.style.marginBottom = "8px";
    div.innerHTML = `<strong>${{idx+1}}. ${{item.drinkName}}</strong> × ${{item.quantity}}<br/><span>${{item.calories}} calories each</span>`;
    summaryContent.appendChild(div);
  }});
}}

addDrinkBtn.addEventListener("click", () => {{
  const drink = getSelectedDrink();
  const qty = Math.max(1, Number(quantityInput.value) || 1);
  cart.push({{ drinkId: drink.id, drinkName: drink.name, quantity: qty, calories: drink.calories || 0 }});
  alert("Added " + qty + " × " + drink.name);
  renderSummary();
}});

viewSummaryBtn.addEventListener("click", () => {{
  renderSummary();
  document.getElementById("summaryCard").scrollIntoView({{ behavior:"smooth" }});
}});

clearBtn.addEventListener("click", () => {{
  if (!confirm("Clear the entire order?")) return;
  cart = [];
  renderSummary();
}});

checkoutBtn.addEventListener("click", async () => {{
  if (cart.length === 0) return alert("Your cart is empty.");
  const res = await fetch("/checkout", {{
    method:"POST",
    headers:{{"Content-Type":"application/json"}},
    body: JSON.stringify(cart)
  }});
  const data = await res.json();
  if (!res.ok || data.status !== "ok") return alert(data.message || "Error");
  alert("✅ Order saved to your account history!");
  cart = [];
  renderSummary();
}});

drinkSelect.addEventListener("change", () => {{
  const d = getSelectedDrink();
  caloriesNote.textContent = (d.calories || 0) + " calories • Fixed recipe.";
}});

populateDrinkSelect();
const initial = getSelectedDrink();
caloriesNote.textContent = (initial.calories || 0) + " calories • Fixed recipe.";
renderSummary();
</script>
</body>
</html>
    """)

# ---------- Checkout: save per user + optional ESP ----------
@app.post("/checkout")
async def checkout(request: Request, items: List[OrderItem]):
    user = current_user(request)
    if not user:
        return JSONResponse({"status": "error", "message": "Not logged in"}, status_code=401)

    stamped = []
    for i in items:
        stamped.append({
            "username": user,
            "drinkId": i.drinkId,
            "drinkName": i.drinkName,
            "quantity": i.quantity,
            "calories": i.calories,
            "ts": datetime.utcnow().isoformat()
        })

    try:
        await send_to_esp([{
            "drinkId": x["drinkId"],
            "drinkName": x["drinkName"],
            "quantity": x["quantity"],
            "calories": x["calories"]
        } for x in stamped])
    except Exception:
        pass

    orders = load_orders()
    orders.extend(stamped)
    save_orders(orders)

    return {"status": "ok", "message": "Saved"}

# ---------- History ----------
@app.get("/history", response_class=HTMLResponse)
async def history(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    orders = [o for o in load_orders() if o.get("username") == user]
    orders.reverse()

    if not orders:
        body = "<p style='color:#f5e6d3'>No history yet.</p>"
    else:
        body = "<ul>" + "".join([
            f"<li style='color:#f5e6d3'>{o.get('drinkName')} × {o.get('quantity')} <small>({o.get('ts','')})</small></li>"
            for o in orders[:50]
        ]) + "</ul>"

    return HTMLResponse(f"""
    <html><head><title>My History</title>{STYLE}</head>
    <body><div class="page">
      <h1>MY HISTORY</h1>
      <div class="subtitle-wrap"><div class="subtitle">Orders saved for <b>{user}</b></div></div>
      <div style="background:rgba(0,0,0,.45);padding:18px;border-radius:16px;border:1px solid rgba(245,230,211,.25);">
        {body}
        <div style="margin-top:14px;display:flex;gap:10px;flex-wrap:wrap;">
          <button class="secondary" onclick="window.location.href='/builder'">Back to Builder</button>
          <button class="secondary" onclick="window.location.href='/dashboard'">Dashboard</button>
        </div>
      </div>
    </div></body></html>
    """)

# ---------- Recommendations ----------
@app.get("/recommendations", response_class=HTMLResponse)
async def recommendations(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    top = get_top_drinks_for_user(user, limit=3)
    if not top:
        rec_html = "<p style='color:#f5e6d3'>No orders yet.</p>"
    else:
        rec_html = "<ul>" + "".join([f"<li style='color:#f5e6d3'>{n}</li>" for n in top]) + "</ul>"

    return HTMLResponse(f"""
    <html><head><title>Recommendations</title>{STYLE}</head>
    <body><div class="page">
      <h1>RECOMMENDATIONS</h1>
      <div class="subtitle-wrap"><div class="subtitle">Based on <b>{user}</b>'s history</div></div>
      <div style="background:rgba(0,0,0,.45);padding:18px;border-radius:16px;border:1px solid rgba(245,230,211,.25);">
        {rec_html}
        <div style="margin-top:14px;display:flex;gap:10px;flex-wrap:wrap;">
          <button class="secondary" onclick="window.location.href='/builder'">Back to Builder</button>
          <button class="secondary" onclick="window.location.href='/dashboard'">Dashboard</button>
        </div>
      </div>
    </div></body></html>
    """)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
