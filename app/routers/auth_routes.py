from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.auth import hash_password
from app.core.storage import load_users, save_users

router = APIRouter()

STYLE = """
<style>
*{box-sizing:border-box}
body{margin:0;font-family:ui-serif,Georgia,Times New Roman,serif;background:#000;background-image:url('/static/background-1.png');background-size:cover;background-position:center;background-attachment:fixed;color:#f5e6d3}
.page{max-width:760px;margin:0 auto;padding:60px 20px}
.card{background:rgba(0,0,0,.55);border:1px solid rgba(245,230,211,.25);border-radius:18px;padding:24px}
h1{text-align:center;margin:0 0 18px;letter-spacing:3px}
label{display:block;margin:10px 0 6px;color:rgba(245,230,211,.9)}
input{width:100%;padding:12px 14px;border-radius:12px;border:1px solid rgba(245,230,211,.25);background:rgba(0,0,0,.35);color:#f5e6d3;outline:none}
button{margin-top:14px;width:100%;padding:12px 14px;border-radius:12px;border:0;background:#f5e6d3;color:#1f130d;font-weight:700;cursor:pointer}
.small{margin-top:12px;text-align:center;color:rgba(245,230,211,.85)}
a{color:#f5e6d3}
.error{margin-top:12px;color:#ffcfb0}
</style>
"""


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


@router.get("/register", response_class=HTMLResponse)
def register_page():
    return HTMLResponse(f"""
    <html><head><title>Register</title>{STYLE}</head>
    <body><div class='page'>
      <h1>REGISTER</h1>
      <div class='card'>
        <form method='post' action='/register'>
          <label>Username</label>
          <input name='username' required />
          <label>Password</label>
          <input name='password' type='password' required />
          <button type='submit'>Create account</button>
        </form>
        <div class='small'>Already have an account? <a href='/login'>Login</a></div>
      </div>
    </div></body></html>
    """)


@router.post("/register")
def register(username: str = Form(...), password: str = Form(...)):
    username = username.strip()
    if not username:
        return RedirectResponse("/register", status_code=302)

    users = load_users()
    if username in users:
        return HTMLResponse(f"<html><head>{STYLE}</head><body><div class='page'><div class='card'><h1>REGISTER</h1><p class='error'>Username already exists.</p><p class='small'><a href='/register'>Try again</a></p></div></div></body></html>")

    users[username] = hash_password(password)
    save_users(users)
    return RedirectResponse("/login", status_code=302)



@router.get("/guest")
def guest_login(request: Request):
    # Guest session: recommendations remain default (non-personalized)
    request.session["user"] = "guest"
    request.session["is_guest"] = True
    return RedirectResponse(url="/", status_code=302)


@router.get("/login", response_class=HTMLResponse)
def login_page():
    return HTMLResponse(f"""
    <html><head><title>Login</title>{STYLE}</head>
    <body><div class='page'>
      <h1>LOGIN</h1>
      <div class='card'>
        <form method='post' action='/login'>
          <label>Username</label>
          <input name='username' required />
          <label>Password</label>
          <input name='password' type='password' required />
          <button type='submit'>Login</button>
          <a href='/guest' class='guestBtn' style='display:block;text-align:center;margin-top:12px;'>Login as Guest</a>
        </form>
        <div class='small'>New here? <a href='/register'>Create an account</a></div>
      </div>
    </div></body></html>
    """)


@router.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    users = load_users()
    if users.get(username) != hash_password(password):
        return HTMLResponse(f"<html><head>{STYLE}</head><body><div class='page'><div class='card'><h1>LOGIN</h1><p class='error'>Invalid username or password.</p><p class='small'><a href='/login'>Try again</a></p></div></div></body></html>")

    request.session["user"] = username
    # After successful login, start users on the main Smart Bartender builder page.
    return RedirectResponse("/builder", status_code=302)
