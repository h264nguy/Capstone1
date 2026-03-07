from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from pydantic import BaseModel
from typing import List
import uvicorn
import json
from collections import Counter
import httpx  # <--- NEW

app = FastAPI()

# ---------- Static files for images ----------
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ---------- ESP8266 (Robot) config ----------
ESP_BASE_URL = "http://172.20.10.3"   # <-- your ESP IP
ESP_ENDPOINT = "/make-drink"


async def send_to_esp(items: list):
    """
    Send order to ESP8266.
    Payload format:
      {"items":[{"drinkId":..., "drinkName":..., "quantity":..., "calories":...}, ...]}
    """
    url = f"{ESP_BASE_URL}{ESP_ENDPOINT}"
    payload = {"items": items}

    timeout = httpx.Timeout(8.0, connect=3.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        return r.json()


# ---------- Simple order history storage ----------
ORDERS_FILE = BASE_DIR / "orders.json"


def load_orders() -> list:
    """Load all past orders from orders.json."""
    if not ORDERS_FILE.exists():
        return []
    with open(ORDERS_FILE, "r") as f:
        return json.load(f)


def save_orders(orders: list):
    """Save all orders back to orders.json."""
    with open(ORDERS_FILE, "w") as f:
        json.dump(orders, f, indent=2)


def get_top_drinks(limit: int = 3) -> List[str]:
    """Return top-N drink names by total quantity ordered."""
    orders = load_orders()
    if not orders:
        return []

    counter = Counter()
    for item in orders:
        name = item.get("drinkName")
        qty = int(item.get("quantity", 1))
        if name:
            counter[name] += qty

    return [name for name, _ in counter.most_common(limit)]


# ---------- Pydantic model for items from frontend ----------
class OrderItem(BaseModel):
    drinkId: str
    drinkName: str
    quantity: int
    calories: int


# ---------- Frontend page (builder) ----------
@app.get("/", response_class=HTMLResponse)
async def builder():
    return HTMLResponse("""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <title>Signature Mocktail Builder</title>
    <style>
        * { box-sizing: border-box; }
        body {
            margin: 0;
            padding: 0;
            font-family: "Playfair Display", serif;
            background-color: #000;
            background-image: url('/static/background-1.png');
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
            background-attachment: fixed;
            color: #1f130d;
        }
        .page {
            max-width: 1100px;
            margin: 0 auto;
            padding: 40px 20px 60px;
        }

        /*  BRIGHTER TITLE */
        h1 {
            font-size: 46px;
            letter-spacing: 3px;
            text-align: center;
            margin-bottom: 6px;

            /* Brighter + readable */
            color: #f5e6d3; /* warm cream */
            text-shadow:
                0 0 10px rgba(245, 230, 211, 0.65),
                0 0 22px rgba(245, 230, 211, 0.45),
                0 0 34px rgba(255, 190, 130, 0.25);
        }

        /*  BRIGHTER SUBTITLE TOO */
        .subtitle {
            text-align: center;
            font-size: 16px;
            margin-bottom: 18px;

            color: rgba(245, 230, 211, 0.92);
            text-shadow: 0 0 10px rgba(0,0,0,0.75);

            /* optional dark backing for readability */
            display: inline-block;
            padding: 6px 14px;
            border-radius: 12px;
            background: rgba(0,0,0,0.35);
        }

        /* Center the subtitle block nicely */
        .subtitle-wrap {
            text-align: center;
        }

        .builder-card {
            background: #fdfaf4;
            border-radius: 18px;
            padding: 22px 26px 26px;
            box-shadow: 0 6px 12px rgba(0,0,0,0.2);
        }
        .row {
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
            margin-bottom: 12px;
        }
        .col {
            flex: 1;
            min-width: 200px;
        }
        label {
            font-weight: 600;
            font-size: 18px;
        }
        select, input[type="number"] {
            margin-top: 4px;
            padding: 4px 8px;
            font-size: 15px;
            width: 100%;
            border-radius: 6px;
            border: 1px solid #b1844a;
            background: #fff7ea;
        }
        .calories-note {
            margin-top: 6px;
            font-size: 13px;
        }
        .btn-row {
            margin-top: 16px;
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }
        button {
            border-radius: 20px;
            border: 1px solid #1f130d;
            background: #1f130d;
            color: #fdf5e6;
            padding: 8px 16px;
            font-size: 14px;
            cursor: pointer;
        }
        button.secondary {
            background: transparent;
            color: #1f130d;
        }
        button:hover { opacity: 0.9; }
        .summary-card {
            margin-top: 22px;
            background: #f8eddc;
            border-radius: 14px;
            padding: 16px 20px;
            font-size: 14px;
        }
        .summary-title { font-weight: 700; margin-bottom: 6px; }
        .summary-empty { font-style: italic; color: #5c4935; }
        .summary-item { margin-bottom: 8px; }
        .summary-item:last-child { margin-bottom: 0; }
    </style>
</head>
<body>
<div class="page">
    <h1>SIGNATURE MOCKTAIL</h1>

    <div class="subtitle-wrap">
        <div class="subtitle">
            Choose your drink (100 mL) and quantity. No need to adjust ratios — recipes are pre-set.
        </div>
    </div>

    <div class="builder-card">
        <div class="row">
            <div class="col">
                <label for="drinkSelect">Drink</label>
                <select id="drinkSelect"></select>
                <div id="caloriesNote" class="calories-note"></div>
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
            <button class="secondary" onclick="window.location.href='/recommendations'">
                Recommendations
            </button>
        </div>
    </div>

    <div id="summaryCard" class="summary-card">
        <div class="summary-title">Order Summary</div>
        <div id="summaryContent" class="summary-empty">
            No drinks added yet. Build your cart to see the summary here.
        </div>
    </div>
</div>

<script>
const DRINKS = [
  { id: "tropical_charge", name: "Tropical Charge", calories: 86 }, // default (index 0)
  { id: "sunset_fizz", name: "Sunset Fizz", calories: 87 },
  { id: "sparkling_citrus_mix", name: "Sparkling Citrus Mix", calories: 118 },
  { id: "golden_breeze", name: "Golden Breeze", calories: 64 }, 
  { id: "energy_sunrise", name: "Energy Sunrise", calories: 67 }, 
  { id: "dark_amber", name: "Dark Amber", calories: 65 }, 
  { id: "crystal_chill", name: "Crystal Chill", calories: 56 }, 
  { id: "cola_spark", name: "Cola Spark", calories: 81 }, 
  { id: "classic_fusion", name: "Classic Fusion", calories: 76 }, 
  { id: "citrus_shine", name: "Citrus Shine", calories: 71 }, 
  { id: "citrus_cloud", name: "Citrus Cloud", calories: 84 },  
  { id: "chaos_punch", name: "Chaos Punch", calories: 204 },   
  { id: "voltage_fizz", name: "Voltage Fizz", calories: 117 },
  { id: "amber_storm", name: "Amber Storm", calories: 104 },
  { id: "base_orange_juice", name: "Orange Juice", calories: 45 },
  { id: "base_water", name: "Water", calories: 0 },
  { id: "base_coca_cola", name: "Coca-Cola", calories: 140 },
  { id: "base_sprite", name: "Sprite", calories: 140 },
  { id: "base_ginger_ale", name: "Ginger Ale", calories: 120 },
  { id: "base_red_bull", name: "Red Bull", calories: 110 }
];

let cart = [];
const CART_STORAGE_KEY = "mocktail_cart_v1_no_ratios";

function saveCart() {
    try { localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(cart)); }
    catch (e) { console.warn("Could not save cart:", e); }
}
function loadCart() {
    try {
        const raw = localStorage.getItem(CART_STORAGE_KEY);
        cart = raw ? JSON.parse(raw) : [];
    } catch (e) {
        console.warn("Could not load cart:", e);
        cart = [];
    }
    renderSummary();
}

const drinkSelect = document.getElementById("drinkSelect");
const caloriesNote = document.getElementById("caloriesNote");
const quantityInput = document.getElementById("quantityInput");
const addDrinkBtn = document.getElementById("addDrinkBtn");
const viewSummaryBtn = document.getElementById("viewSummaryBtn");
const clearBtn = document.getElementById("clearBtn");
const checkoutBtn = document.getElementById("checkoutBtn");
const summaryContent = document.getElementById("summaryContent");

function populateDrinkSelect() {
    DRINKS.forEach((d, index) => {
        const opt = document.createElement("option");
        opt.value = d.id;
        opt.textContent = d.name;
        if (index === 0) opt.selected = true;
        drinkSelect.appendChild(opt);
    });
}

function getSelectedDrink() {
    const id = drinkSelect.value;
    return DRINKS.find(d => d.id === id);
}

function renderSummary() {
    if (cart.length === 0) {
        summaryContent.className = "summary-empty";
        summaryContent.textContent = "No drinks added yet. Build your cart to see the summary here.";
        return;
    }
    summaryContent.className = "";
    summaryContent.innerHTML = "";
    cart.forEach((item, idx) => {
        const div = document.createElement("div");
        div.className = "summary-item";
        div.innerHTML = `
            <strong>${idx + 1}. ${item.drinkName}</strong> &times; ${item.quantity}<br/>
            <span>${item.calories} calories each</span>
        `;
        summaryContent.appendChild(div);
    });
}

addDrinkBtn.addEventListener("click", () => {
    const drink = getSelectedDrink();
    const qty = Math.max(1, Number(quantityInput.value) || 1);

    cart.push({
        drinkId: drink.id,
        drinkName: drink.name,
        quantity: qty,
        calories: drink.calories
    });
    saveCart();
    alert("Added " + qty + " × " + drink.name + " to your cart.");
    renderSummary();
});

viewSummaryBtn.addEventListener("click", () => {
    renderSummary();
    document.getElementById("summaryCard").scrollIntoView({ behavior: "smooth" });
});

clearBtn.addEventListener("click", () => {
    if (!confirm("Clear the entire order?")) return;
    cart = [];
    saveCart();
    renderSummary();
});

checkoutBtn.addEventListener("click", async () => {
    if (cart.length === 0) {
        alert("Your cart is empty.");
        return;
    }
    try {
        const response = await fetch("/checkout", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(cart)
        });

        const data = await response.json();
        if (!response.ok || data.status !== "ok") {
            throw new Error(data.message || ("Server error " + response.status));
        }

        alert(data.message || "Order completed!");

        cart = [];
        saveCart();
        renderSummary();
    } catch (err) {
        alert("Failed to complete order: " + err.message);
    }
});

drinkSelect.addEventListener("change", () => {
    const d = getSelectedDrink();
    caloriesNote.textContent = d.calories + " calories • Fixed recipe.";
});

populateDrinkSelect();
const initialDrink = getSelectedDrink();
caloriesNote.textContent = initialDrink.calories + " calories • Fixed recipe.";
loadCart();
</script>
</body>
</html>
    """)


# ---------- Checkout endpoint: SEND to ESP + save history ----------
@app.post("/checkout")
async def checkout(items: List[OrderItem]):
    esp_items = [
        {
            "drinkId": i.drinkId,
            "drinkName": i.drinkName,
            "quantity": i.quantity,
            "calories": i.calories
        }
        for i in items
    ]

    # 1) Send to robot
    try:
        esp_reply = await send_to_esp(esp_items)
    except Exception as e:
        return {"status": "error", "message": f"Could not reach robot: {str(e)}"}

    # 2) Save order history
    orders = load_orders()
    orders.extend(esp_items)
    save_orders(orders)

    return {"status": "ok", "message": "Order sent to robot and saved!", "esp": esp_reply}


# ---------- Recommendations page ----------
@app.get("/recommendations", response_class=HTMLResponse)
async def recommendations():
    top = get_top_drinks(limit=3)

    if not top:
        rec_html = "<p>You haven’t placed any orders yet. Start ordering to get recommendations!</p>"
    else:
        rec_html = "<ul>"
        for name in top:
            rec_html += f"<li>{name}</li>"
        rec_html += "</ul>"

    html = f"""
    <html>
    <head>
        <meta charset="utf-8" />
        <title>Recommended Drinks</title>
        <style>
            body {{
                margin: 0;
                padding: 0;
                font-family: Arial, sans-serif;
                background-color: #000;
                background-image: url('/static/background-1.png');
                background-size: cover;
                background-position: center;
                background-repeat: no-repeat;
                background-attachment: fixed;
                color: #e8ffe0;
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
            }}
            .card {{
                background: #111;
                padding: 32px 40px;
                border-radius: 18px;
                text-align: center;
                box-shadow: 0 0 18px rgba(0,0,0,0.5);
            }}
            h1 {{
                color: #7dff7d;
                margin-top: 0;
            }}
            button {{
                margin-top: 18px;
                padding: 10px 24px;
                border-radius: 18px;
                border: none;
                cursor: pointer;
                font-size: 14px;
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>Recommended Drinks</h1>
            <p>Based on past orders, you might like:</p>
            {rec_html}
            <button onclick="window.location.href='/'">Back to Builder</button>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(html)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8012, reload=True)
