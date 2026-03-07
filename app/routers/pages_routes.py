from __future__ import annotations

import json

# -------------------------
# Ingredient labels (normalized id -> display)
# -------------------------
INGREDIENT_LABELS = {
  "coca_cola": "Coca-Cola",
  "red_bull": "Red Bull",
  "ginger_ale": "Ginger Ale",
  "orange_juice": "Orange Juice",
  "sprite": "Sprite",
  "water": "Water",
  "lemonade": "Lemonade",
  "water": "Splash of Water",
  "sprite": "Splash of Sprite",
}

def pretty_ingredient(ing: str) -> str:
    if not ing:
        return ""
    return INGREDIENT_LABELS.get(ing, ing.replace("_"," ").title())
from collections import Counter
from pathlib import Path
from string import Template

from fastapi import APIRouter, Request, Request
from fastapi.responses import HTMLResponse, RedirectResponse, RedirectResponse

from app.core.auth import current_user
from app.core.storage import ensure_drinks_file, load_drinks, load_orders
from app.ml.recommender import recommend_for_user

router = APIRouter()

# ---- Read the SAME orders.json used by orders_routes.py ----
REPO_ROOT = Path(__file__).resolve().parents[2]  # app/routers -> app -> repo_root
DATA_DIR = REPO_ROOT / "data"
ORDERS_FILE = DATA_DIR / "orders.json"


def _load_orders_shared():
    """Load orders written by /checkout."""
    return load_orders()


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
.grid{display:grid;gap:14px}
.cards{grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
.card{
  background:rgba(0,0,0,.55);
  border:1px solid rgba(245,230,211,.25);
  border-radius:18px;
  padding:18px;
  box-shadow:0 10px 30px rgba(0,0,0,.35);
}
.card.selected{
  border-color: rgba(255,190,130,.65);
  box-shadow: 0 0 0 1px rgba(255,190,130,.25), 0 14px 36px rgba(0,0,0,.45);
}
.card h2{margin:0 0 10px;color:#f5e6d3;letter-spacing:2px}
.btnrow{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}
.corner-actions{position:fixed;top:24px;left:0;right:0;pointer-events:none;z-index:50}
.corner{pointer-events:auto;position:fixed;top:24px}
.corner.left{left:24px}
.corner.right{right:24px}
@media(max-width:520px){.corner.left{left:14px}.corner.right{right:14px}.corner{top:14px}}

button,.primary,.secondary{
  appearance:none;border:0;cursor:pointer;
  padding:12px 14px;border-radius:14px;
  font-family:inherit;
  font-weight:700;
  letter-spacing:1px;
}
button[disabled]{opacity:.45;cursor:not-allowed;filter:saturate(.6)}
.btn-active{background:#f5e6d3;color:#1f130d}
.primary{background:#f5e6d3;color:#1f130d}
.secondary{background:rgba(0,0,0,.35);color:#f5e6d3;border:1px solid rgba(245,230,211,.25);text-decoration:none;display:inline-block}
.small{color:rgba(245,230,211,.85)}
hr{border:0;border-top:1px solid rgba(245,230,211,.18);margin:14px 0}
.table{width:100%;border-collapse:collapse;margin-top:10px}
.table th,.table td{border-bottom:1px solid rgba(245,230,211,.18);padding:10px 8px;color:#f5e6d3;text-align:left}
.table th{color:rgba(245,230,211,.92)}
.pill{display:inline-block;padding:6px 10px;border-radius:999px;background:rgba(245,230,211,.12);border:1px solid rgba(245,230,211,.18);color:#f5e6d3;font-size:12px}
.qty-pill{min-width:44px;text-align:center;display:inline-flex;align-items:center;justify-content:center}
.ing{margin-top:10px;color:rgba(245,230,211,.9)}
.ing ul{margin:8px 0 0 18px;padding:0}
.ing li{margin:4px 0;color:rgba(245,230,211,.85)}

/* --- ETA live countdown bar --- */
.etaBox{
  margin-top:12px;
  padding:12px 14px;
  border:1px solid rgba(245,230,211,.25);
  border-radius:14px;
  background:rgba(0,0,0,.35);
  color:#f5e6d3;
}
.etaTop{display:flex;justify-content:space-between;align-items:baseline;gap:12px}
.etaLabel{letter-spacing:.14em;font-weight:700;font-size:12px;opacity:.9}
.etaText{font-size:14px;opacity:.95}
.etaBarBg{
  margin-top:10px;
  height:10px;
  border-radius:999px;
  background:rgba(245,230,211,.18);
  overflow:hidden;
}
.etaBarFill{
  height:100%;
  border-radius:999px;
  background:rgba(245,230,211,.85);
  transition:width .35s linear;
}



/* Queue: per-drink ETA rows */
.orderRow{
  display:flex;
  justify-content:space-between;
  align-items:flex-start;
  gap:18px;
  margin-top:14px;
}
.orderTitle{
  font-weight:700;
  font-size:22px;
  letter-spacing:.2px;
}
.orderMeta{
  opacity:.9;
  font-size:16px;
  line-height:1.35;
  margin-top:4px;
}
.orderEta{
  text-align:right;
  min-width:180px;
  font-size:18px;
  opacity:.95;
  white-space:nowrap;
}

/* Separate top-left buttons (History + Logout) */
.corner.left{left:18px;}
.corner.left2{left:138px;}


.btn.secondary{background:transparent;color:#f5e6d3;border:1px solid rgba(245,230,211,.35)}

/* ===== Mood Buttons Glow ===== */
.mood-btn{position:relative;transition:transform .12s, box-shadow .18s, border-color .18s}
.mood-btn.active{
 border-color:rgba(80,160,255,.95)!important;
 box-shadow:0 0 0 3px rgba(80,160,255,.55),0 0 18px rgba(80,160,255,.85),0 0 42px rgba(80,160,255,.55);
 transform:translateY(-1px)
}
.mood-btn:hover{transform:translateY(-1px);box-shadow:0 0 14px rgba(80,160,255,.25)}

/* ===== Checkout Button Glow ===== */
.checkout-btn{position:relative;transition:transform .12s, box-shadow .22s}
.checkout-btn:hover{
 transform:translateY(-1px);
 box-shadow:0 0 0 2px rgba(80,160,255,.35),0 0 18px rgba(80,160,255,.55),0 0 44px rgba(80,160,255,.35)
}
.checkout-btn:active{
 transform:translateY(0) scale(.98);
 box-shadow:0 0 12px rgba(80,160,255,.35)
}


/* ===== Force top-right Checkout placement ===== */
.corner{position:fixed;top:18px;z-index:9999}
.corner.right{right:18px;left:auto}
.corner.left{left:18px;right:auto}

/* ===== Checkout click feedback ===== */
.checkout-btn.loading{
  opacity:0.85;
  pointer-events:none;
  transform:translateY(0) scale(0.98);
}
.checkout-btn.loading::before{
  content:"";
  display:inline-block;
  width:10px;height:10px;
  margin-right:8px;
  border:2px solid rgba(80,160,255,.55);
  border-top-color:rgba(80,160,255,1);
  border-radius:50%;
  animation:spin .7s linear infinite;
  vertical-align:middle;
}
@keyframes spin{to{transform:rotate(360deg)}}


/* ===== Ensure Checkout always clickable & visible ===== */
.corner{position:fixed;top:18px;z-index:99999}
.corner.right{right:18px;left:auto}
.checkout-btn{cursor:pointer;pointer-events:auto}
.checkout-btn.clicked{transform:translateY(1px) scale(.97)}


/* --- Drink search bar --- */
.drink-search-wrap{
  display:flex;
  gap:10px;
  align-items:center;
  margin: 14px 0 18px 0;
}
#drinkSearch{
  flex:1;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid rgba(255,255,255,0.18);
  background: rgba(0,0,0,0.35);
  color: rgba(255,255,255,0.92);
  font-size: 16px;
  outline: none;
}
#drinkSearch::placeholder{ color: rgba(255,255,255,0.55); }
#drinkSearch:focus{
  border-color: rgba(255,255,255,0.35);
  box-shadow: 0 0 0 3px rgba(255,255,255,0.10);
}
#drinkSearchClear{
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(255,255,255,0.18);
  background: rgba(0,0,0,0.35);
  color: rgba(255,255,255,0.80);
  cursor: pointer;
}
#drinkSearchClear:hover{ border-color: rgba(255,255,255,0.30); }

.why{ margin-top:10px; }
.why summary{ cursor:pointer; list-style:none; }
.why summary::-webkit-details-marker{ display:none; }
.why summary:after{ content:" ▼"; opacity:0.8; }
.why[open] summary:after{ content:" ▲"; }
.why ul{ margin:6px 0 0 18px; padding:0; }


/* --- Demo readability + subtle glow --- */
#recBanner{
  color:#ffffff !important;
  font-weight:700;
  text-shadow: 0 0 6px rgba(255,255,255,0.45), 0 0 14px rgba(255,210,160,0.25);
}
details.why summary{
  color:#ffffff !important;
  font-weight:600;
  text-shadow: 0 0 4px rgba(255,255,255,0.35);
}
details.why ul li{
  color:#ffffff !important;
  opacity:1 !important;
  text-shadow: 0 0 3px rgba(255,255,255,0.25);
}


.ing-match{
  font-weight:700;
  color:#fff;
  text-shadow:0 0 6px rgba(255,255,255,.5),0 0 14px rgba(255,215,150,.25);
}
</style>
"""


def _require_user(request: Request):
    return current_user(request)


def _top_drinks_for_user(username: str, limit: int = 3):
    # IMPORTANT: use shared orders file (same one /checkout writes)
    orders = _load_orders_shared()
    c = Counter()
    for o in orders:
        if str(o.get("username")) == str(username):
            c[str(o.get("drinkName", ""))] += int(o.get("quantity", 1) or 1)
    return [name for name, _ in c.most_common(limit) if name]


def _find_drink(drink_id: str):
    ensure_drinks_file()
    for d in load_drinks():
        if d.get("id") == drink_id:
            return d
    return None




@router.get('/guest')
def guest_login(request: Request):
    # Guest session: recommendations remain default (non-personalized)
    request.session['user'] = 'guest'
    request.session['is_guest'] = True
    return RedirectResponse(url='/', status_code=302)


@router.get('/logout')
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url='/login', status_code=302)

@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    return RedirectResponse("/builder" if current_user(request) else "/login", status_code=302)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    user = _require_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    return HTMLResponse(f"""
    <html><head><title>Dashboard</title>{STYLE}</head>
    <body><div class='page'>
      <h1>DASHBOARD</h1>
      <div style='text-align:center; margin-bottom:14px;'>
        <span class='pill'>Welcome, {user}</span>
      </div>

      <div class='grid cards'>
        <div class='card'>
          <h2>HISTORY</h2>
          <div class='small'>See what you ordered before.</div>
          <div class='btnrow'>
            <button class='secondary' onclick="window.location.href='/history'">View History</button>
          </div>
        </div>

        <div class='card'>
          <h2>RECOMMEND</h2>
          <div class='small'>New drink suggestions.</div>
          <div class='btnrow'>
            <button class='secondary' onclick="window.location.href='/recommendations'">See Recommendations</button>
          </div>
        </div>


      </div>

      <div class='btnrow' style='margin-top:14px'>
        <button class='secondary' onclick="window.location.href='/logout'">Logout</button>
      </div>
    </div></body></html>
    """)


@router.get("/menu", response_class=HTMLResponse)
def menu_alias(request: Request):
    return RedirectResponse("/builder", status_code=302)


@router.get("/builder", response_class=HTMLResponse)
def builder(request: Request):
    user = _require_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    ensure_drinks_file()

    tpl = Template(r"""
<html><head><title>Builder</title>$STYLE</head>
<body><div class='page'>
  <h1>SMART BARTENDER</h1>
  <div class='card'>
    <h2>RECOMMENDED FOR YOU</h2>
    <div class='small'>What are you in the mood for?</div>
    <div class='btnrow' style='margin-top:10px'>
      <button class='secondary mood-btn' data-mood='chill' onclick="pickMood('chill')">Chill</button>
      <button class='secondary mood-btn' data-mood='energized' onclick="pickMood('energized')">Energized</button>
      <button class='secondary mood-btn' data-mood='sweet' onclick="pickMood('sweet')">Sweet</button>
      <button class='secondary mood-btn' data-mood='adventurous' onclick="pickMood('adventurous')">Adventurous</button>
      <button class='secondary mood-btn' data-mood='none' onclick="pickMood('none')">None</button>
      <span id='moodLabel' class='pill' style='margin-left:10px; opacity:.9'>Mood: none</span>
    </div>

    <div id='recBanner' class='card' style='display:none; margin-top:12px; padding:12px'></div>
    <div id='recs' class='grid cards' style='margin-top:14px'></div>
    <hr/>
    <h2>MENU</h2>
    <div class='small'>Pick drinks and quantities. Then checkout to save history (and optionally send to ESP).</div>
    
      <div class="drink-search-wrap">
        <input id="drinkSearch" type="text" placeholder="Search drinks (name or ingredient)..." autocomplete="off" />
        <button id="drinkSearchClear" type="button" aria-label="Clear search">✕</button>
      </div>
<div id='menu' class='grid cards' style='margin-top:14px'></div>

    <hr/>
    <h2>CART</h2>
    <div id='cart' class='small'>No items yet.</div>
    <div id='status' class='small' style='margin-top:10px'></div>
    <div id='etaBox' class='etaBox' style='display:none;'>
      <div class='etaTop'>
        <div class='etaLabel'>ETA</div>
        <div id='etaText' class='etaText'>--</div>
      </div>
      <div class='etaBarBg'>
        <div id='etaBarFill' class='etaBarFill' style='width:0%'></div>
      </div>
    
    <div id='myQueueBox' class='etaBox' style='margin-top:16px;'>
      <div class='etaTop'>
        <div class='etaLabel'>Your Active Orders</div>
        <div class='etaText small' style='opacity:.8'>Live queue + ETAs (first-come, first-serve)</div>
      </div>
      <div id='myQueue' class='small' style='margin-top:10px;'>Loading…</div>
    </div>

</div>

  </div>

  <div class='corner-actions'>
    <a class='secondary corner left' href='/history'>History</a>
    <a class='secondary corner left2' href='/logout'>Logout</a>
    <button id='checkoutBtn' class='primary corner right checkout-btn' type='button'>Checkout</button>
  </div>


<script>

function prettyStatus(s){
  if(!s) return s;
  return String(s).split('_').map(w=>w? w[0].toUpperCase()+w.slice(1):w).join(' ');
}


if(window.__sbCartEtaInit){
  // already initialized
} else {
  window.__sbCartEtaInit = true;


// -------------------------
// Multi-order ETA (per account)
// -------------------------

function setMainEtaFromOrders(orders){
  const box = document.getElementById('etaBox');
  const bar = document.getElementById('etaFill');
  const txt = document.getElementById('etaText');
  if(!box || !bar || !txt) return;

  box.style.display = 'block';
  const list = (orders || []);
  if(!list.length){
    bar.style.width = '0%';
    txt.textContent = '0s';
    return;
  }

  const etas = list.map(o => (o.etaSeconds==null ? 0 : __adjSec(o.etaSeconds)));
  const aheads = list.map(o => (o.etaAheadSeconds==null ? 0 : __adjSec(o.etaAheadSeconds)));

  const totalRemain = Math.max(...etas);
  const startsIn = list.some(o => o.status === 'In Progress') ? 0 : Math.max(0, Math.min(...aheads));

  // stable denominator per snapshot
  if(!window.__topDenom || window.__topDenomTs !== __mySnapshotTs){
    window.__topDenom = Math.max(1, totalRemain);
    window.__topDenomTs = __mySnapshotTs;
  }
  const denom = window.__topDenom;
  const pct = Math.max(0, Math.min(100, Math.round(((denom - totalRemain)/denom)*100)));
  bar.style.width = pct + '%';

  const suffix = (startsIn > 0) ? ` (starts in ~${formatETA(startsIn)})` : ' (starts now)';
  txt.textContent = `${formatETA(totalRemain)}${suffix}`;
}




function __renderMyQueue(box){
  const orders = __myOrdersSnapshot || [];
  if(!box) return;
  if(!orders.length){
    box.innerHTML = '<div class="small">No active orders.</div>';
    return;
  }

  box.innerHTML = orders.map(o => {
    const drink = escapeHtml(o.drinkName || o.drink || 'Drink');
    const qty   = o.quantity || 1;
    const status = escapeHtml(o.status || 'Pending');
    const pos = o.position || 1;

    const aheadRaw = (o.etaAheadSeconds ?? null);
    const etaRaw   = (o.etaSeconds ?? null);
    const ahead = aheadRaw===null ? null : __adjSec(aheadRaw);
    const eta   = etaRaw===null   ? null : __adjSec(etaRaw);

    const startsTxt = ahead===null ? '' : ` (starts in ${formatETA(ahead)})`;
    const rightTxt = (eta===null) ? '' : `${formatETA(eta)}${startsTxt}`;

    let bar = '';
    if((o.status === 'In Progress') && etaRaw!==null && eta!==null){
      const total = Math.max(1, (o.stepSeconds || etaRaw));
      const done = Math.min(1, Math.max(0, (total - eta) / total));
      const pct = Math.round(done * 100);
      bar = `<div class="progress"><div class="fill" style="width:${pct}%"></div></div>`;
    } else {
      bar = `<div class="progress"><div class="fill" style="width:0%"></div></div>`;
    }

    return `
      <div class="orderRow">
        <div>
          <div class="orderTitle">${drink} × ${qty}</div>
          <div class="small">Position: #${pos} (ahead: ${Math.max(0,(pos-1))}) • Status: ${status}</div>
          <div class="small"></div>
        </div>
        <div class="orderEta">${rightTxt}</div>
      </div>
      ${bar}
    `;
  }).join('');
}

async function loadMyQueue(){
  const box = document.getElementById('myQueue');
  if(!box) return;

  try{
    const res = await fetch('/api/my/queue', {credentials:'include'});
    const data = await res.json();
    if(!data.ok){
      box.innerHTML = '<div class="small">Queue unavailable.</div>';
      return;
    }
    const orders = data.orders || [];
    __myOrdersSnapshot = orders;
    __mySnapshotTs = Date.now();
    try{ setMainEtaFromOrders(orders); }catch(e){}
    if(!orders.length){
      box.innerHTML = '<div class="small">No active orders.</div>';
      __myOrdersSnapshot = [];
      __mySnapshotTs = Date.now();
      return;
    }

    __renderMyQueue(box);
  }catch(e){
    box.innerHTML = '<div class="small">Could not load queue.</div>';
  }
}

let myQueueTimer = null;
let __myOrdersSnapshot = [];
let __mySnapshotTs = 0;
let __localTickTimer = null;

function __elapsedSec(){
  if(!__mySnapshotTs) return 0;
  return Math.floor((Date.now() - __mySnapshotTs)/1000);
}

function __adjSec(s){
  const e = __elapsedSec();
  return Math.max(0, Math.round(s - e));
}

function startMyQueueAutoRefresh(){
  if(myQueueTimer) clearInterval(myQueueTimer);
  loadMyQueue();
  myQueueTimer = setInterval(loadMyQueue, 10000);
  if(!__localTickTimer){
    __localTickTimer = setInterval(() => {
      if(document.hidden) return;
      const box = document.getElementById('myQueue');
      if(!box) return;
      __renderMyQueue(box);
      try{ setMainEtaFromOrders(__myOrdersSnapshot); }catch(_e){}
    }, 1000);
  }
  document.addEventListener('visibilitychange', () => {
    if(document.hidden){
      if(myQueueTimer) clearInterval(myQueueTimer);
      myQueueTimer = null;
    }else{
      startMyQueueAutoRefresh();
    }
  }, {once:true});
}



// lightweight HTML escape for safe rendering
function escapeHtml(s){
  return String(s).replace(/[&<>"']/g, m => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[m]));
}


function prettyIngredientName(s){
  if(!s) return s;
  return String(s).split('_').map(w => w ? (w[0].toUpperCase() + w.slice(1)) : w).join(' ');
}


// -----------------------------
// Menu search (client-side)
// -----------------------------
// Keep the latest query so Add/Remove doesn't reset the filter.
let menuQuery = '';


function formatSeconds(s){ s=Math.max(0,Math.floor(s||0)); const m=Math.floor(s/60), r=s%60; return m>0?`${m}m ${r}s`:`${r}s`; }

function formatETA(sec){
  try{ sec = Math.max(0, parseInt(sec)); }catch(e){ return String(sec); }
  const m = Math.floor(sec/60);
  const s = sec%60;
  return m>0 ? `${m}m ${s.toString().padStart(2,'0')}s` : `${s}s`;
}

async function loadQueue(){
  const el = document.getElementById('queue');
  try{
    const res = await fetch('/api/my/queue', {credentials:'include'});
    const data = await res.json();
    if(!res.ok || !data.ok){
      el.innerText = "Active queue: unavailable.";
      return;
    }
    const orders = data.orders || [];
    __myOrdersSnapshot = orders;
    __mySnapshotTs = Date.now();
    try{ setMainEtaFromOrders(orders); }catch(e){}
    if(!orders.length){
      el.innerHTML = "<b>Active queue:</b> <span class='small'>No active orders in queue.</span>";
      return;
    }
    let html = "<b>Active queue (live):</b>";
    html += '<table class="table" style="margin-top:10px"><tr><th>Order</th><th>Position</th><th>Status</th><th>Starts In</th><th>ETA</th></tr>';
    orders.forEach(o=>{
      const oid = (o.orderId||'').slice(0,8);
      const pos = o.position ?? '';
      const st  = o.status ?? '';
      const ahead = (o.etaAheadSeconds !== undefined) ? formatETA(o.etaAheadSeconds) : '...';
      const eta   = (o.etaSeconds !== undefined) ? formatETA(o.etaSeconds) : '...';
      html += `<tr><td>${oid}</td><td>${pos}</td><td>${st}</td><td>${ahead}</td><td>${eta}</td></tr>`;
    });
    html += "</table>";
    el.innerHTML = html;
  }catch(e){
    el.innerText = "Active queue error.";
  }
}


let drinks = [];
let cart = {};
let lastOrderItems = null; // persists last checkout summary

let recs = [];
let pollTimer = null;

// Bind checkout button click
const checkoutBtn = document.getElementById('checkoutBtn');
if (checkoutBtn) {
  checkoutBtn.addEventListener('click', async (e) => {
    // pressed feedback even if request fails
    checkoutBtn.classList.add('clicked');
    setTimeout(() => checkoutBtn.classList.remove('clicked'), 160);
    await checkout(checkoutBtn);
  });
}


function formatETA(sec){
  try{ sec = Math.max(0, parseInt(sec)); }catch(e){ return String(sec); }
  const m = Math.floor(sec/60);
  const s = sec%60;
  return m>0 ? `${m}m ${s.toString().padStart(2,'0')}s` : `${s}s`;
}

function parseEtaSeconds(v){
  if(v === null || v === undefined) return null;
  if(typeof v === 'number') return isFinite(v) ? Math.max(0, Math.floor(v)) : null;
  // try plain int string
  const n = parseInt(v);
  if(!isNaN(n) && String(v).trim().match(/^\d+$/)) return Math.max(0, n);
  // try formats like "10m 06s" or "10m06s" or "1m" or "45s"
  const s = String(v);
  const mm = s.match(/(\d+)\s*m/i);
  const ss = s.match(/(\d+)\s*s/i);
  if(mm || ss){
    const m = mm ? parseInt(mm[1]) : 0;
    const sec = ss ? parseInt(ss[1]) : 0;
    return Math.max(0, m*60 + sec);
  }
  return null;
}

function setEtaFromServer(etaSeconds, etaAheadSeconds){
  const serverEtaRaw = parseEtaSeconds(etaSeconds);
  if(serverEtaRaw === null) return; // don't overwrite with invalid

  const serverEta = Math.max(0, serverEtaRaw);

  const currentOrderId = localStorage.getItem('lastOrderId');
  const etaOrderId = localStorage.getItem('etaOrderId');

  // If this is a new order (or first time we ever stored one), reset ETA state cleanly.
  if(currentOrderId && currentOrderId !== etaOrderId){
    localStorage.setItem('etaOrderId', currentOrderId);
    localStorage.removeItem('etaInitial');
    localStorage.removeItem('etaRemaining');
    localStorage.removeItem('etaUpdatedTs');
    localStorage.removeItem('etaAheadSeconds');
  }
const hasPrev = !!localStorage.getItem('etaUpdatedTs');

  // Current live remaining (based on our last tick)
  const live = getLiveEta();
  const liveRemaining = (live && live.remaining !== undefined) ? Math.max(0, live.remaining) : null;

  // Make ETA monotonic (never jump upward due to server jitter) ONLY after we have a previous sample.
  // (First sample should always be accepted; otherwise we can get stuck at 0.)
  let nextRemaining = serverEta;
  if(hasPrev && liveRemaining !== null){
    // Allow tiny upward corrections (<=2s).
    if(serverEta > liveRemaining + 2){
      nextRemaining = Math.ceil(liveRemaining);
    } else {
      nextRemaining = serverEta;
    }
  }

  // Initial baseline: set once per order.
  const prevInitial = parseInt(localStorage.getItem('etaInitial') || '0');
  if(!prevInitial){
    localStorage.setItem('etaInitial', String(Math.max(1, nextRemaining)));
  } else {
    localStorage.setItem('etaInitial', String(Math.max(1, prevInitial)));
  }

  localStorage.setItem('etaRemaining', String(Math.max(0, nextRemaining)));
  localStorage.setItem('etaUpdatedTs', String(Date.now()));

  // Smooth "starts in" (ahead) if provided
  const serverAheadRaw = parseEtaSeconds(etaAheadSeconds);
  if(serverAheadRaw !== null){
    const serverAhead = Math.max(0, serverAheadRaw);
    const prevAhead = parseInt(localStorage.getItem('etaAheadSeconds') || '0');
    // never jump upward (allow +2s) once we have a previous sample
    const nextAhead = (prevAhead && serverAhead > prevAhead + 2) ? prevAhead : serverAhead;
    localStorage.setItem('etaAheadSeconds', String(nextAhead));
  }

  const box = document.getElementById('etaBox');
  if(box) box.style.display = 'block';
}

function getLiveEta(){
  const remaining0 = parseFloat(localStorage.getItem('etaRemaining') || '0');
  const ts = parseFloat(localStorage.getItem('etaUpdatedTs') || '0');
  if(!ts) return {remaining: remaining0, initial: parseFloat(localStorage.getItem('etaInitial')||'0')};
  const elapsed = (Date.now() - ts) / 1000.0;
  const remaining = Math.max(0, remaining0 - elapsed);
  const initial = parseFloat(localStorage.getItem('etaInitial') || String(Math.max(1, remaining0)));
  return {remaining, initial};
}

function renderEtaBar(){
  const box = document.getElementById('etaBox');
  if(!box) return;

  const lastOrderId = localStorage.getItem('lastOrderId');
  if(!lastOrderId){
    box.style.display = 'none';
    return;
  }

  const {remaining, initial} = getLiveEta();
  const aheadStored = parseEtaSeconds(localStorage.getItem('etaAheadSeconds'));
  if((!initial || initial<=0) && aheadStored && aheadStored>0){
    box.style.display = 'block';
    const etaText = document.getElementById('etaText');
    if(etaText) etaText.innerText = `Waiting for ETA... (starts in ~${formatETA(aheadStored)})`;
    const fill = document.getElementById('etaBarFill');
    if(fill) fill.style.width = '0%';
    return;
  }

  if(!initial){
    box.style.display = 'none';
    return;
  }

  box.style.display = 'block';

  const pct = Math.max(0, Math.min(100, (1 - (remaining/initial)) * 100));
  const fill = document.getElementById('etaBarFill');
  if(fill) fill.style.width = pct.toFixed(1) + '%';

  const startsIn = localStorage.getItem('etaAheadSeconds');
  const startsTxt = (startsIn !== null && startsIn !== undefined && startsIn !== '') 
    ? ` (starts in ~${formatETA(parseInt(startsIn))})` 
    : '';

  const etaText = document.getElementById('etaText');
  if(etaText) etaText.innerText = `${formatETA(Math.ceil(remaining))}${startsTxt}`;
}

function startEtaTicker(){
  // One global ticker tied to page
  if(window.__etaTicker) clearInterval(window.__etaTicker);
  window.__etaTicker = setInterval(renderEtaBar, 500);
  renderEtaBar();
}



function ingredientsHtml(d, enableHighlight=true){
  const arr = d && d.ingredients;
  if(!arr || !Array.isArray(arr) || arr.length===0) return "";
  const hi = (enableHighlight && window.basedOnIngredients && window.basedOnIngredients.size) ? window.basedOnIngredients : new Set();
  const items = arr.map(x => {
    const key = String(x);
    const matched = enableHighlight && hi.has(key);
    // Use inline styles so it's impossible to miss in demo
    const style = matched ? "font-weight:900;color:#fff;background:rgba(255,255,255,.08);border-radius:6px;padding:2px 6px;display:inline-block;text-shadow:0 0 10px rgba(255,255,255,.7),0 0 20px rgba(255,215,150,.35);" : "";
    return `<li style="${style}">${escapeHtml(prettyIngredientName(key))}</li>`;
  }).join("");
  return `<div class='ing'><div class='small'>Ingredients:</div><ul>${items}</ul></div>`;
}


function renderRecs(){
  const el = document.getElementById('recs');
  if(!el) return;
  el.innerHTML='';
  if(!recs || recs.length===0){ el.innerHTML = "<div class='small'>No recommendations yet. Place a few orders first 🙂</div>"; return; }
  recs.forEach(d => {
    const card = document.createElement('div');
    const qty = (cart[d.id] && cart[d.id].quantity) ? cart[d.id].quantity : 0;
    card.className = qty > 0 ? 'card selected' : 'card';
    const cal = (d.calories || 0);
    card.innerHTML = `
      <h2>${d.name}</h2>
      <div class='small'>Calories: <span class='pill'>${cal} cal</span></div>
      <div class='small' style='margin-top:10px'>In cart: <span class='pill qty-pill'>${qty}</span></div>
      ${ingredientsHtml(d)}
      
      <div class='btnrow' style='margin-top:12px'>
        <button class='secondary ${qty>0 ? 'btn-active' : ''}' onclick="addToCart('${d.id}','${d.name.replace(/'/g, "\\'")}',${cal})">Add</button>
        <button class='secondary' ${qty===0 ? 'disabled' : ''} onclick="removeFromCart('${d.id}')">Remove</button>
        
      </div>
    `;
    el.appendChild(card);
  })
}

function renderMenu(query = '') {
  // Normalize query and remember it globally so the filter persists
  // across Add/Remove updates.
  menuQuery = String(query || '').trim();
  const q = menuQuery.toLowerCase();

  const el = document.getElementById('menu');
  el.innerHTML = '';
  drinks.forEach(d => {
    // Filter by drink name (and optionally ingredient keys)
    if (q) {
      const nameMatch = String(d.name || '').toLowerCase().includes(q);
      const ing = Array.isArray(d.ingredients) ? d.ingredients : [];
      const ingMatch = ing.some(x => String(x).toLowerCase().includes(q));
      if (!nameMatch && !ingMatch) return;
    }
    const card = document.createElement('div');
    const qty = (cart[d.id] && cart[d.id].quantity) ? cart[d.id].quantity : 0;
    card.className = qty > 0 ? 'card selected' : 'card';
    const cal = (d.calories || 0);
    card.innerHTML = `
      <h2>${d.name}</h2>
      <div class='small'>Calories: <span class='pill'>${cal} cal</span></div>
      <div class='small' style='margin-top:10px'>In cart: <span class='pill qty-pill'>${qty}</span></div>
      ${ingredientsHtml(d, false)}
      <div class='btnrow' style='margin-top:12px'>
        
        <button class='secondary ${qty>0 ? 'btn-active' : ''}' onclick="addToCart('${d.id}','${d.name.replace(/'/g, "\\'")}',${cal})">Add</button>
        <button class='secondary' ${qty===0 ? 'disabled' : ''} onclick="removeFromCart('${d.id}')">Remove</button>
      </div>
    `;
    el.appendChild(card);
  })
}

function renderCart(){
  const el = document.getElementById('cart');
  const keys = Object.keys(cart);

  // If cart is empty but we just checked out, show the last order summary
  if(keys.length===0){
    if(Array.isArray(lastOrderItems) && lastOrderItems.length){
      let html = "<div class='small' style='margin-bottom:8px'>Last order:</div>";
      html += '<table class="table"><tr><th>Drink</th><th>Qty</th><th>Calories</th></tr>';
      lastOrderItems.forEach(it=>{
        const nm = it.drinkName || '';
        const q  = parseInt(it.quantity || 1);
        const c  = parseInt(it.calories || 0);
        html += `<tr><td>${nm}</td><td>${q}</td><td>${c}</td></tr>`;
      });
      html += '</table>';
      el.innerHTML = html;
      return;
    }
    el.innerHTML='No items yet.';
    return;
  }
  let html = '<table class="table"><tr><th>Drink</th><th>Qty</th><th>Calories</th></tr>';
  keys.forEach(k=>{
    const it = cart[k];
    html += `<tr><td>${it.drinkName}</td><td>${it.quantity}</td><td>${it.calories}</td></tr>`;
  })
  html += '</table>';
  el.innerHTML = html;
}

function addToCart(id,name,cal){
  if(!cart[id]) cart[id] = {drinkId:id, drinkName:name, quantity:0, calories:cal};
  cart[id].quantity += 1;
  renderCart();
	  renderMenu(menuQuery);
  renderRecs();
}

function removeFromCart(id){
  if(!cart[id]) return;
  cart[id].quantity -= 1;
  if(cart[id].quantity <= 0) delete cart[id];
  renderCart();
	  renderMenu(menuQuery);
  renderRecs();
}

async function checkout(btnEl) {
  console.log('[checkout] clicked');
  const btn = btnEl || document.getElementById('checkoutBtn') || document.querySelector('.checkout-btn');
  const status = document.getElementById('status');

  // Only send items with quantity > 0 (guards against stale UI state)
  const items = Object.values(cart).filter(it => it && parseInt(it.quantity || 0) > 0);

  if (items.length === 0) {
    if (status) status.innerText = 'Cart is empty.';
    // Safety: clear any stuck loading state
    if (btn) {
      btn.classList.remove('loading');
      btn.disabled = false;
      btn.innerText = btn.dataset.orig || 'Checkout';
    }
    return;
  }

// UI feedback
  let timer = null;
  if (btn) {
    btn.dataset.orig = btn.dataset.orig || btn.innerText;
    btn.classList.add('loading');
    btn.disabled = true;
    btn.innerText = 'Processing...';
    timer = setTimeout(() => {
      btn.classList.remove('loading');
      btn.disabled = false;
      btn.innerText = btn.dataset.orig || 'Checkout';
      if (status) status.innerText = 'Checkout timed out. Please try again.';
    }, 10000);
  }

  try {
    if (status) status.innerText = 'Checking out...';
    if(status) status.innerText = 'Checking out...';

    let res = await fetch('/checkout', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({items, mood: (window.currentMood && window.currentMood !== 'none') ? window.currentMood : null})
    });
    if(res && res.status===404){ res = await fetch('/api/checkout', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({items, mood: (window.currentMood && window.currentMood !== 'none') ? window.currentMood : null}) }); }


    const ct = res.headers.get("content-type") || "";
    if (!ct.includes("application/json")) {
      await res.text();
      if(status) status.innerText = "Checkout failed. Please login again.";
      return;
    }

    const data = await res.json();
    if(data && data.ok){
      const orderId = data.orderId || data.orderID || data.id;
      if(status) status.innerText = 'Order placed!' + (orderId ? ` ` : '');
      lastOrderItems = items;
      cart = {};
      renderCart();
      try{ localStorage.setItem('lastOrderId', orderId || ''); localStorage.setItem('lastOrderTs', String(Date.now())); }catch(e){}
      if(orderId){ try{ startQueuePoll(orderId); }catch(e){} try{ startEtaTicker(); }catch(e){} }
      // refresh ETA box if present
      try{ renderEtaBar(); }catch(e){}}else{
      const errMsg = (data && (data.error || data.detail || data.msg)) ? (data.error || data.detail || data.msg) : 'Checkout failed.';
      if(status) status.innerText = errMsg;
    }
  }catch(err){
    if(status) status.innerText = 'Checkout error. Please try again.';
  }finally{
    if (btn){
      if (timer) clearTimeout(timer);
      btn.classList.remove('loading');
      btn.disabled = false;
      btn.innerText = btn.dataset.orig || 'Checkout';
    }
  }
}

// expose for inline onclick
window.checkout = checkout;


function startQueuePoll(orderId){
  if(pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async ()=>{
    try{
      const r = await fetch(`/api/queue/status?orderId=${encodeURIComponent(orderId)}`);
      const data = await r.json();
      if(data && data.ok){
        const eta = (data.etaSeconds!==undefined) ? formatETA(data.etaSeconds) : '...';
        const etaStart = (data.etaAheadSeconds!==undefined) ? formatETA(data.etaAheadSeconds) : '...';
        document.getElementById('status').innerText = `Queued! Orders ahead: ${ (typeof data.ahead==='number') ? data.ahead : (typeof data.position==='number' ? Math.max(0, data.position-1) : 0) }`;
        setEtaFromServer(data.etaSeconds, data.etaAheadSeconds);
      } else {
        document.getElementById('status').innerText = `Order completed (or removed from queue). `;
        clearInterval(pollTimer);
        localStorage.removeItem('lastOrderId');
        localStorage.removeItem('lastOrderTs');
        localStorage.removeItem('etaInitial');
        localStorage.removeItem('etaRemaining');
        localStorage.removeItem('etaUpdatedTs');
        localStorage.removeItem('etaAheadSeconds');
      }
    }catch(e){ /* ignore */ }
  }, 3000);
}

(async function init(){
  // Load drinks once
  const r = await fetch('/api/drinks');
  drinks = await r.json();

  // Resume queue polling if an order is still in localStorage
  const lastOrderId = localStorage.getItem('lastOrderId');
  if(lastOrderId){
    document.getElementById('status').innerText = `Resuming status for ...`;
    startQueuePoll(lastOrderId);
    startEtaTicker();
  }

  // Mood-based recommendations state
  window.currentMood = window.currentMood || 'none';
  let moodTimer = null;

  function setMoodLabel(){
    const el = document.getElementById('moodLabel');
    if(!el) return;
    el.textContent = `Mood: ${window.currentMood || 'none'}`;
  }

  function setMoodButtons(){
    document.querySelectorAll('.mood-btn').forEach(btn=>{
      const m = btn.dataset.mood;
      const cur = window.currentMood || 'none';
    btn.classList.toggle('active', m === cur);
    });
  }

  async function loadRecs(){
    try{
      const curMood = window.currentMood || 'none';
  const url = (curMood && curMood !== 'none')
    ? `/api/recommendations?k=3&mood=${encodeURIComponent(curMood)}`
    : '/api/recommendations?k=3';
      const rr = await fetch(url);
      const rdata = await rr.json();
      if(rdata && rdata.ok){
        recs = rdata.recommendations || [];
        // save ingredients from last ordered drink for highlighting
        try{
          const arr = rdata.based_on_ingredients || [];
          window.basedOnIngredients = new Set((Array.isArray(arr)?arr:[]).map(x=>String(x)));
        }catch(e){ window.basedOnIngredients = new Set(); }
        const banner = document.getElementById('recBanner');
        if(banner){
          const based = rdata.based_on || null;
          if(based){
            banner.style.display = 'block';
            const dbg = (rdata.based_on_ingredients||[]).map(x=>prettyIngredientName(String(x))).join(', ');
            banner.innerHTML = `Because you ordered: <strong>${escapeHtml(based)}</strong> <span class="buildtag"></span><div class="debugline">Matched ingredient keys: ${escapeHtml(dbg)}</div>`;
          }else{
            banner.style.display = 'none';
            banner.innerHTML = '';
          }
        }
      }else{
        recs = [];
      }
    }catch(e){
      recs = [];
    }
  }

  async function refreshRecsWithFade(){
    const el = document.getElementById('recs');
    if(el){
      // one-time transition setup
      if(!el.dataset.fadeInit){
        el.style.transition = 'opacity 180ms ease, transform 180ms ease';
        el.dataset.fadeInit = '1';
      }
      el.style.opacity = '0';
      el.style.transform = 'translateY(6px)';
      await new Promise(r => setTimeout(r, 180));
    }

    await loadRecs();
    renderRecs();

    if(el){
      // fade back in
      requestAnimationFrame(()=>{
        el.style.opacity = '1';
        el.style.transform = 'translateY(0)';
      });
    }
  }

  function startMoodAutoRefresh(){
    if(moodTimer){ clearInterval(moodTimer); moodTimer = null; }
    if(!window.currentMood) return;

    moodTimer = setInterval(async ()=>{
      if(document.hidden) return;         // pause while tab is hidden
      if(!window.currentMood) return;     // mood cleared
      await refreshRecsWithFade();
    }, 10000);
  }

  document.addEventListener('visibilitychange', async ()=>{
    if(!document.hidden && window.currentMood){
      // refresh once when user comes back
      await refreshRecsWithFade();
    }
  });

  // Expose the click handler used by the mood buttons
  window.pickMood = async function(m){
    window.currentMood = (m && m !== 'none') ? m : 'none';
    setMoodLabel();
    setMoodButtons();
    await refreshRecsWithFade();
    startMoodAutoRefresh();
  };
// Initial render
  setMoodLabel();
  await loadRecs();
  renderRecs();
  const _search = document.getElementById('drinkSearch');
  const _clear = document.getElementById('drinkSearchClear');
  if (_search) {
    _search.addEventListener('input', () => renderMenu(_search.value));
  }
  if (_clear && _search) {
    _clear.addEventListener('click', () => { _search.value=''; renderMenu(''); _search.focus(); });
  }
  renderMenu(_search ? _search.value : '');
  renderCart();
})();

// start per-account multi-order queue polling
try { startMyQueueAutoRefresh(); } catch (e) { console.log("myQueue init failed", e); }

}
</script>

</div></body></html>
""")

    return HTMLResponse(tpl.safe_substitute(STYLE=STYLE))


@router.get("/drink/{drink_id}", response_class=HTMLResponse)
def drink_page(request: Request, drink_id: str):
    user = _require_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    d = _find_drink(drink_id)
    if not d:
        return HTMLResponse(
            f"<html><head><title>Not Found</title>{STYLE}</head>"
            f"<body><div class='page'><h1>NOT FOUND</h1>"
            f"<div class='card'><p class='small'>Unknown drink id: <b>{drink_id}</b></p>"
            f"<div class='btnrow'><button class='secondary' onclick=\"window.location.href='/builder'\">Back</button></div>"
            f"</div></div></body></html>",
            status_code=404
        )

    name = d.get("name", drink_id)
    cal = int(d.get("calories", 0) or 0)

    ingredients = d.get("ingredients")
    if isinstance(ingredients, list) and ingredients:
        lis = "".join([f"<li>{str(x)}</li>" for x in ingredients])
        ingredients_block = f"<div class='ing' style='margin-top:12px'><div class='small'>Ingredients:</div><ul>{lis}</ul></div>"
    else:
        ingredients_block = ""

    tpl = Template(r"""
<html><head><title>$name</title>$STYLE</head>
<body><div class='page'>
  <h1>$name_upper</h1>
  <div class='grid cards'>
    <div class='card'>
      <h2>ORDER THIS DRINK</h2>
      <div class='small'>Calories: <span class='pill'>$cal cal</span></div>
      $ingredients_block
      <hr/>
      <div class='small'>Quantity</div>
      <div class='btnrow'>
        <button class='secondary' onclick='decQty()'>-</button>
        <span id='qty' class='pill qty-pill'>1</span>
        <button class='secondary' onclick='incQty()'>+</button>
      </div>
      <div class='btnrow' style='margin-top:14px'>
        <button class='primary checkout-btn' type='button' onclick="this.classList.add('clicked'); setTimeout(()=>this.classList.remove('clicked'),160); checkout(this);">Checkout</button>
        <button class='secondary' onclick="window.location.href='/builder'">Menu</button>
      </div>
      <div id='status' class='small' style='margin-top:10px'></div>
    </div>
  </div>

<script>
let quantity = 1;
function setQty(){ document.getElementById('qty').innerText = quantity; }
function incQty(){ quantity += 1; setQty(); }
function decQty(){ quantity = Math.max(1, quantity - 1); setQty(); }

async function checkout(btnEl) {
  const status = document.getElementById('status');
  status.innerText = 'Checking out...';
  const items = [{drinkId: "$drink_id", drinkName: "$name_js", quantity: quantity, calories: $cal}];

  const res = await fetch('/checkout', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({items, mood: (window.currentMood && window.currentMood !== 'none') ? window.currentMood : null})
  });

  const ct = res.headers.get("content-type") || "";
  if (!ct.includes("application/json")) {
    await res.text();
    status.innerText = "Checkout failed (server returned non-JSON). Please login again.";
    return;
  }

  const data = await res.json();
  if (!res.ok || !data.ok) {
    status.innerText = "Error: " + (data.error || ("HTTP " + res.status));
    return;
  }

  const q = (data.queue || {});
  if (q.position) {
    status.innerText = `Queued! Orders ahead: ${ (typeof q.ahead==='number') ? q.ahead : (typeof q.position==='number' ? Math.max(0, q.position-1) : 0) }`;
    startQueuePoll(data.orderId);
  } else {
    status.innerText = `Order saved. `;
  }
}

setQty();
</script>

</div></body></html>
""")

    return HTMLResponse(tpl.safe_substitute(
        STYLE=STYLE,
        name=name,
        name_upper=name.upper(),
        name_js=name.replace('"', '\\"'),
        drink_id=drink_id,
        cal=str(cal),
        ingredients_block=ingredients_block,
    ))


@router.get("/history", response_class=HTMLResponse)
def history(request: Request):
    user = _require_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    tpl = Template(r"""
<html><head><title>History</title>$STYLE</head>
<body><div class='page'>
  <h1>ORDER HISTORY</h1>

  <div class='card'>
    <div class='small'>Logged in as: <span class='pill' id='who'>$user</span></div>
    <div id='queue' class='small' style='margin-top:12px'>Loading queue...</div>
    <div id='content' class='small' style='margin-top:16px'>Loading history...</div>

    <div class='btnrow' style='margin-top:14px'>
      <button class='secondary' onclick="window.location.href='/builder'">Back to Menu</button>
    </div>
  </div>

<script>

async function loadQueue(){
  const el = document.getElementById('queue');
  try{
    const res = await fetch('/api/my/queue', {credentials:'include'});
    const ct = res.headers.get("content-type") || "";
    if(!ct.includes("application/json")){
      el.innerText = "Queue failed (non-JSON). Please login again.";
      return;
    }
    const data = await res.json();
    if(!res.ok || !data.ok){
      el.innerText = "Queue error: " + (data.error || ("HTTP " + res.status));
      return;
    }

    const orders = data.orders || [];
    try{ setMainEtaFromOrders(orders); }catch(e){}
    if(orders.length === 0){
      el.innerHTML = "<span class='small'>No active queued orders.</span>";
      return;
    }

    let html = "<div class='small' style='margin-bottom:6px'>Active queue (live):</div>";
    html += "<table class='table'><tr><th>#</th><th>Status</th><th>Starts in</th><th>Complete in</th><th>Order</th></tr>";
    orders.forEach(o=>{
      const pos = o.position || "-";
      const ahead = (typeof o.etaAheadSeconds === "number") ? o.etaAheadSeconds : null;
      const eta = (typeof o.etaSeconds === "number") ? o.etaSeconds : null;

      const fmt = (s)=>{
        if(s==null) return "--";
        s = Math.max(0, Math.floor(s));
        const m = Math.floor(s/60);
        const r = s%60;
        return m>0 ? `${m}m ${r}s` : `${r}s`;
      };

      html += `<tr>
        <td>${pos}</td>
        <td>${o.status || ''}</td>
        <td>${fmt(ahead)}</td>
        <td>${fmt(eta)}</td>
        <td class='small'>${(o.orderId||'').slice(0,8)}…</td>
      </tr>`;
    });
    html += "</table>";
    el.innerHTML = html;

  }catch(e){
    el.innerText = "Queue error: " + e;
  }
}

async function loadHistory(){
  const el = document.getElementById('content');
  try{
    const res = await fetch('/api/history', {credentials:'include'});
    const ct = res.headers.get("content-type") || "";
    if(!ct.includes("application/json")){
      el.innerText = "History failed (server returned non-JSON). Please login again.";
      return;
    }
    const data = await res.json();
    if(!res.ok || !data.ok){
      el.innerText = "Error: " + (data.error || ("HTTP " + res.status));
      return;
    }

    const orders = data.orders || [];
    try{ setMainEtaFromOrders(orders); }catch(e){}
    if(orders.length === 0){
      el.innerHTML = "<p class='small'>No orders yet.</p>";
      return;
    }

    let html = '<table class="table"><tr><th>Drink</th><th>Qty</th><th>Calories</th><th>Time</th></tr>';
    orders.slice().reverse().forEach(o=>{
      html += `<tr>
        <td>${o.drinkName || ''}</td>
        <td>${o.quantity || 1}</td>
        <td>${o.calories || 0}</td>
        <td>${o.ts || ''}</td>
      </tr>`;
    });
    html += '</table>';
    el.innerHTML = html;
  }catch(e){
    el.innerText = "History error: " + e;
  }
}
loadQueue();
loadHistory();
setInterval(loadQueue, 3000);
</script>

</div></body></html>
""")

    return HTMLResponse(tpl.safe_substitute(STYLE=STYLE, user=user))


@router.get("/drink-links", response_class=HTMLResponse)
def drink_links_page(request: Request):
    user = _require_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    ensure_drinks_file()
    drinks = load_drinks()

    rows = "".join([
        f"<tr><td>{d.get('name','')}</td>"
        f"<td><span class='pill'>{d.get('calories',0)} cal</span></td>"
        f"<td><a href='/drink/{d.get('id')}'><b>/drink/{d.get('id')}</b></a></td></tr>"
        for d in drinks
    ])

    return HTMLResponse(f"""
    <html><head><title>Drink Links</title>{STYLE}</head>
    <body><div class='page'>
      <h1>DRINK LINKS</h1>
      <div class='card'>
        <div class='small'>Copy these links into Canva using your deployed domain.</div>
        <table class='table'>
          <tr><th>Drink</th><th>Calories</th><th>Link</th></tr>
          {rows}
        </table>
        <div class='btnrow' style='margin-top:14px'>
          <button class='secondary' onclick="window.location.href='/builder'">Back to Menu</button>
        </div>
      </div>
    </div></body></html>
    """)


@router.get("/recommendations", response_class=HTMLResponse)
def recommendations_page(request: Request):
    user = _require_user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    top = _top_drinks_for_user(user, limit=3)
    top_html = "<p class='small'>No orders yet.</p>" if not top else "<ul>" + "".join(
        [f"<li style='color:#f5e6d3'>{n}</li>" for n in top]
    ) + "</ul>"

    recs = recommend_for_user(user, k=3)
    if not recs:
        rec_html = "<p class='small'>No recommendations yet.</p>"
    else:
        rec_html = "<ul>" + "".join([
            f"<li style='color:#f5e6d3'><b>{d.get('name')}</b> "
            f"<span class='pill' style='margin-left:8px'>{d.get('calories',0)} cal</span></li>"
            for d in recs
        ]) + "</ul>"

    return HTMLResponse(f"""
    <html><head><title>Recommendations</title>{STYLE}</head>
    <body><div class='page'>
      <h1>RECOMMENDATIONS</h1>
      <div class='card' style='margin-top:14px'>
        <h2>MOOD-BASED SUGGESTIONS</h2>
        <div class='small'>Pick a mood and we’ll re-rank drinks using ingredient clusters + your past orders.</div>
        <div class='btnrow' style='margin-top:10px'>
          <button class='secondary mood-btn' data-mood='chill' onclick="pickMood('chill')">Chill</button>
          <button class='secondary mood-btn' data-mood='energized' onclick="pickMood('energized')">Energized</button>
          <button class='secondary mood-btn' data-mood='sweet' onclick="pickMood('sweet')">Sweet</button>
          <button class='secondary mood-btn' data-mood='adventurous' onclick="pickMood('adventurous')">Adventurous</button>
          <button class='secondary' onclick="pickMood('')">Clear</button>
        </div>
        <div id="moodStatus" class='small' style='margin-top:10px; color:rgba(245,230,211,.9)'></div>
        <div id="moodRecs" style='margin-top:10px'></div>
      </div>

      <script>
        function esc(s){{ return (''+s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;'); }}

        async function pickMood(mood){{
          const status = document.getElementById('moodStatus');
          const box = document.getElementById('moodRecs');
          box.innerHTML = "<p class='small'>Loading…</p>";
          status.textContent = (mood && mood !== 'none') ? ("Mood: " + mood) : "Mood: none";

          const url = (mood && mood !== 'none') ? ("/api/recommendations?mood=" + encodeURIComponent(mood) + "&k=3") : "/api/recommendations?k=3";
          try{{
            const res = await fetch(url);
            const data = await res.json();
            if(!data.ok){{ box.innerHTML = "<p class='small'>Could not load recommendations.</p>"; return; }}

            const recs = data.recommendations || [];
            if(!recs.length){{ box.innerHTML = "<p class='small'>No recommendations yet.</p>"; return; }}

            const lis = recs.map(function(d){{
              const name = esc(d.name || d.id || "Drink");
              const cal = esc((d.calories === undefined || d.calories === null) ? 0 : d.calories);
              const ings = Array.isArray(d.ingredients) ? d.ingredients.map(function(x){{ return esc((''+x).replaceAll('_',' ')); }}).join(', ') : "";
              const ingHtml = ings ? ("<div class='small' style='margin-top:6px'>Ingredients: " + ings + "</div>") : "";
              return "<li style='color:#f5e6d3; margin:10px 0'>" +
                       "<b>" + name + "</b>" +
                       "<span class='pill' style='margin-left:8px'>" + cal + " cal</span>" +
                       ingHtml +
                     "</li>";
            }}).join("");

            box.innerHTML = "<ul style='margin:10px 0 0 18px; padding:0'>" + lis + "</ul>";
          }}catch(e){{
            box.innerHTML = "<p class='small'>Error loading recommendations.</p>";
          }}
        }}
</script>

      <div class='grid cards'>
        <div class='card'>
          <h2>NEW DRINKS FOR YOU</h2>
          <div class='small'>Based on similar users + popularity.</div>
          {rec_html}
        </div>
        <div class='card'>
          <h2>YOUR TOP DRINKS</h2>
          <div class='small'>What you order the most.</div>
          {top_html}
        </div>
      </div>
      <div class='btnrow' style='margin-top:14px'>
        <button class='secondary' onclick="window.location.href='/builder'">Back to Menu</button>
      </div>
    </div></body></html>
    """)