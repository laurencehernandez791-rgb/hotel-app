import sqlite3, os, random, string, hashlib
from datetime import date, datetime
from functools import wraps
from flask import Flask, render_template_string, request, redirect, url_for, session, flash

app = Flask(__name__)
app.secret_key = "grandvista-2024"
DB_FILE = os.path.join(os.path.dirname(__file__), "hotel.db")

# Rooms will be loaded from DB, but we keep these as defaults for first-time setup
DEFAULT_ROOMS = [
    {"type": "Deluxe Room",   "price": 4500,  "capacity": 30, "features": "King Bed, WiFi, AC, Smart TV"},
    {"type": "Junior Suite",  "price": 7800,  "capacity": 30, "features": "City View, WiFi, AC, Mini Bar"},
    {"type": "Premier Ocean", "price": 9500,  "capacity": 30, "features": "Ocean View, Balcony, WiFi, AC"},
    {"type": "Family Suite",  "price": 11200, "capacity": 30, "features": "2 Bedrooms, Kitchenette, WiFi, AC"},
]
AMENITIES = [
    {"id": "sp",   "name": "Spa Access",       "price": 1500},
    {"id": "late", "name": "Late Check-out",   "price": 500},
]

# ──────────────────────────────────────────────
#  DATABASE
# ──────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def hash_pw(password):
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            username   TEXT UNIQUE NOT NULL,
            full_name  TEXT NOT NULL,
            email      TEXT UNIQUE NOT NULL,
            password   TEXT NOT NULL,
            role       TEXT DEFAULT 'Staff',
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ref TEXT UNIQUE NOT NULL,
            fname TEXT, lname TEXT, email TEXT, phone TEXT,
            checkin TEXT, checkout TEXT, nights INTEGER,
            adults INTEGER DEFAULT 1, children INTEGER DEFAULT 0,
            room_id INTEGER, room_type TEXT,
            amenities TEXT DEFAULT '',
            room_total INTEGER, amen_total INTEGER DEFAULT 0,
            total INTEGER, status TEXT DEFAULT 'Pending',
            discount_type TEXT DEFAULT 'None',
            payment_method TEXT DEFAULT 'Cash',
            booking_type TEXT DEFAULT 'Walk-in',
            requests TEXT DEFAULT '', created_at TEXT
        )
    """)
    try:
        conn.execute("ALTER TABLE bookings ADD COLUMN discount_type TEXT DEFAULT 'None'")
    except sqlite3.OperationalError: pass
    try:
        conn.execute("ALTER TABLE bookings ADD COLUMN payment_method TEXT DEFAULT 'Cash'")
    except sqlite3.OperationalError: pass
    try:
        conn.execute("ALTER TABLE bookings ADD COLUMN booking_type TEXT DEFAULT 'Walk-in'")
    except sqlite3.OperationalError: pass
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rooms (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            type       TEXT NOT NULL,
            price      INTEGER NOT NULL,
            capacity   INTEGER NOT NULL,
            status     TEXT DEFAULT 'Clean', -- Clean, Dirty, Maintenance
            features   TEXT DEFAULT ''
        )
    """)
    try:
        conn.execute("ALTER TABLE rooms ADD COLUMN features TEXT DEFAULT ''")
    except sqlite3.OperationalError: pass
    conn.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user       TEXT NOT NULL,
            action     TEXT NOT NULL,
            timestamp  TEXT NOT NULL
        )
    """)
    conn.commit()
    
    # Seed default rooms if empty
    if conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0] == 0:
        for r in DEFAULT_ROOMS:
            conn.execute("INSERT INTO rooms (type, price, capacity, features) VALUES (?,?,?,?)", (r['type'], r['price'], r['capacity'], r['features']))
        conn.commit()

    # Seed default admin account if no users exist
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        conn.execute("""
            INSERT INTO users (username, full_name, email, password, role, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("admin", "Admin User", "admin@grandvista.com", hash_pw("admin123"), "Admin", datetime.now().isoformat()))
        conn.commit()
    conn.close()

def log_action(action):
    user = session.get("username", "System")
    conn = get_db()
    conn.execute("INSERT INTO logs (user, action, timestamp) VALUES (?,?,?)", (user, action, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_rooms():
    conn = get_db()
    rooms = conn.execute("SELECT * FROM rooms").fetchall()
    conn.close()
    return rooms

def rand_ref():
    return "GVH-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please sign in to continue.", "danger")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        if session.get("role") != "Admin":
            flash("Admin access required.", "danger")
            return redirect(url_for("bookings"))
        return f(*args, **kwargs)
    return wrapper

# ──────────────────────────────────────────────
#  SHARED CSS + BASE TEMPLATE
# ──────────────────────────────────────────────

BASE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>GrandVista Hotel</title>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@500;600&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet"/>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{--gold:#B8974A;--gold-d:#A3843D;--gold-l:#FAF7F0;--cream:#FAF8F4;--border:#e8e4dc;
      --text:#1C1A17;--muted:#6B6459;--light:#f4f1eb;--white:#fff;
      --danger:#E24B4A;--success:#1D9E75;--info:#185FA5;--r:8px}
body{font-family:'DM Sans',sans-serif;background:var(--cream);color:var(--text);min-height:100vh}
a{color:var(--gold);text-decoration:none}
a:hover{text-decoration:underline}

/* ── NAV ── */
nav{background:var(--white);border-bottom:1px solid var(--border);padding:0 2rem;
    display:flex;align-items:center;justify-content:space-between;height:56px;
    position:sticky;top:0;z-index:99}
.logo{font-family:'Playfair Display',serif;font-size:20px;font-weight:600}
.logo span{color:var(--gold)}
.nav-links{display:flex;gap:4px}
.nav-links a{padding:6px 14px;border-radius:var(--r);font-size:13px;color:var(--muted);
  border:1px solid transparent;display:inline-flex;align-items:center;gap:5px}
.nav-links a:hover{background:var(--light);color:var(--text);text-decoration:none}
.nav-links a.active{background:var(--light);color:var(--text);font-weight:500;border-color:var(--border)}
.nav-right{display:flex;align-items:center;gap:10px}
.user-chip{display:flex;align-items:center;gap:8px}
.avatar{width:30px;height:30px;border-radius:50%;background:#F0EAD8;display:flex;
  align-items:center;justify-content:center;font-size:12px;font-weight:600;color:var(--gold)}
.user-info{font-size:13px}
.user-info .uname{font-weight:500;color:var(--text)}
.user-info .urole{font-size:11px;color:var(--muted)}
.badge-role{font-size:10px;padding:2px 8px;border-radius:10px;font-weight:500}
.role-Admin{background:#FAF0DC;color:#854F0B}
.role-Staff{background:#E6F1FB;color:#185FA5}
.btn-logout{background:none;border:1px solid var(--border);cursor:pointer;
  font-family:'DM Sans',sans-serif;font-size:12px;color:var(--muted);border-radius:var(--r);padding:5px 12px}
.btn-logout:hover{border-color:var(--danger);color:var(--danger)}

/* ── LAYOUT ── */
.page{max-width:900px;margin:0 auto;padding:2rem 1.5rem}
.page-title{font-family:'Playfair Display',serif;font-size:22px;font-weight:500;margin-bottom:1.5rem}
.card{background:var(--white);border:1px solid var(--border);border-radius:12px;padding:1.5rem;margin-bottom:1rem}

/* ── FORM ── */
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.form-grid.single{grid-template-columns:1fr}
.form-group{margin-bottom:0}
.form-group label{display:block;font-size:11px;color:var(--muted);letter-spacing:1px;
  text-transform:uppercase;margin-bottom:5px}
.form-group input,.form-group select,.form-group textarea{
  width:100%;padding:9px 13px;font-family:'DM Sans',sans-serif;font-size:14px;
  border:1px solid var(--border);border-radius:var(--r);background:var(--cream);
  color:var(--text);outline:none;transition:border-color .15s}
.form-group input:focus,.form-group select:focus,.form-group textarea:focus{
  border-color:var(--gold);background:var(--white)}
.form-group textarea{resize:vertical;min-height:70px}
.form-section{font-family:'Playfair Display',serif;font-size:16px;margin:1.25rem 0 .75rem}
.field-hint{font-size:11px;color:var(--muted);margin-top:4px}

/* ── BUTTONS ── */
.btn{display:inline-flex;align-items:center;gap:6px;padding:9px 22px;border-radius:var(--r);
  font-family:'DM Sans',sans-serif;font-size:13px;font-weight:500;cursor:pointer;
  border:none;transition:all .15s;text-decoration:none}
.btn-primary{background:var(--gold);color:#fff}
.btn-primary:hover{background:var(--gold-d);text-decoration:none;color:#fff}
.btn-secondary{background:transparent;border:1px solid var(--border);color:var(--muted)}
.btn-secondary:hover{border-color:#aaa;color:var(--text);text-decoration:none}
.btn-danger{background:transparent;border:1px solid var(--border);color:var(--muted)}
.btn-danger:hover{border-color:var(--danger);color:var(--danger);text-decoration:none}
.btn-full{width:100%;justify-content:center}
.btn-row{display:flex;gap:10px;justify-content:flex-end;margin-top:1.25rem}

/* ── ROOMS ── */
.rooms-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:1rem}
.room-card{border:2px solid var(--border);border-radius:var(--r);padding:1rem;cursor:pointer;transition:all .15s}
.room-card:hover{border-color:var(--gold)}
.room-card input[type=radio]{display:none}
.room-card.checked{border-color:var(--gold);background:var(--gold-l)}
.room-name{font-family:'Playfair Display',serif;font-size:14px;font-weight:500;margin-bottom:3px}
.room-price{font-size:16px;font-weight:500;color:var(--gold)}
.room-feat{font-size:11px;color:var(--muted);margin-top:3px}

/* ── AMENITIES ── */
.amenities{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:1rem}
.amenity{display:flex;align-items:center;gap:5px;padding:6px 14px;border:1px solid var(--border);
  border-radius:20px;font-size:12px;color:var(--muted);cursor:pointer;transition:all .15s}
.amenity input{display:none}
.amenity:hover{border-color:var(--gold);color:var(--gold)}
.amenity.checked{background:var(--gold-l);border-color:var(--gold);color:var(--gold)}

/* ── TABLE ── */
.tbl-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;font-size:11px;color:var(--muted);letter-spacing:1px;text-transform:uppercase;
  padding:8px 10px;border-bottom:1px solid var(--border);font-weight:400}
td{padding:9px 10px;border-bottom:1px solid var(--border);vertical-align:middle}
tr:last-child td{border-bottom:none}
tr:hover td{background:var(--cream)}

/* ── BADGES ── */
.badge{font-size:11px;padding:3px 10px;border-radius:20px;font-weight:500;white-space:nowrap}
.badge-Pending{background:#FAEEDA;color:#854F0B}
.badge-Confirmed{background:#EAF3DE;color:#3B6D11}
.badge-Cancelled{background:#FCEBEB;color:#A32D2D}
.badge-Checked{background:#E6F1FB;color:#185FA5}
.badge-room-Clean{background:#EAF3DE;color:#3B6D11}
.badge-room-Dirty{background:#FCEBEB;color:#A32D2D}
.badge-room-Maintenance{background:#FFF5E6;color:#B8974A}

/* ── STATS ── */
.stats-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:1.5rem}
.stat-card{background:var(--white);border:1px solid var(--border);border-radius:var(--r);padding:14px 16px}
.stat-label{font-size:11px;color:var(--muted);margin-bottom:4px;text-transform:uppercase;letter-spacing:.5px}
.stat-val{font-size:22px;font-weight:500}
.stat-val.gold{color:var(--gold)}

/* ── ALERTS ── */
.alert{padding:10px 14px;border-radius:var(--r);font-size:13px;margin-bottom:1rem}
.alert-success{background:#EAF3DE;color:#3B6D11;border:1px solid #c3dda1}
.alert-danger{background:#FCEBEB;color:#A32D2D;border:1px solid #F7C1C1}
.alert-info{background:#E6F1FB;color:#185FA5;border:1px solid #b3d0f0}

/* ── SUMMARY ── */
.summary{background:var(--cream);border:1px solid var(--border);border-radius:var(--r);padding:1.25rem;margin-bottom:1rem}
.sum-row{display:flex;justify-content:space-between;font-size:13px;padding:5px 0;color:var(--muted);border-bottom:1px solid var(--border)}
.sum-row:last-child{border-bottom:none}
.sum-row.total{color:var(--text);font-weight:500;font-size:14px}
.sum-row.total span:last-child{color:var(--gold)}

/* ── INFO ROWS ── */
.info-row{display:flex;justify-content:space-between;font-size:13px;padding:6px 0;border-bottom:1px solid var(--border)}
.info-row:last-child{border-bottom:none}
.info-row span:first-child{color:var(--muted)}

/* ── EMPTY ── */
.empty{text-align:center;padding:3rem 0;color:var(--muted)}

/* ── AUTH PAGES ── */
.auth-wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:1rem}
.auth-box{width:460px;background:var(--white);border:1px solid var(--border);border-radius:12px;overflow:hidden}
.auth-top{background:#1C1A17;padding:2.5rem;color:var(--white)}
.auth-logo{font-family:'Playfair Display',serif;font-size:26px}
.auth-logo span{color:var(--gold)}
.auth-tagline{font-size:11px;color:rgba(255,255,255,.4);letter-spacing:3px;text-transform:uppercase;margin-top:5px}
.auth-body{padding:2rem}
.auth-body .form-group{margin-bottom:14px}
.auth-switch{text-align:center;font-size:13px;color:var(--muted);margin-top:1.25rem}
.divider{display:flex;align-items:center;gap:10px;margin:1.25rem 0;color:var(--muted);font-size:12px}
.divider::before,.divider::after{content:'';flex:1;height:1px;background:var(--border)}

/* ── USERS TABLE ── */
.pw-wrap{position:relative}
.pw-wrap input{padding-right:42px}
.toggle-pw{position:absolute;right:12px;top:50%;transform:translateY(-50%);background:none;border:none;
  cursor:pointer;color:var(--muted);font-size:14px;padding:0}
.toggle-pw:hover{color:var(--text)}

@media(max-width:640px){
  .stats-grid{grid-template-columns:1fr 1fr}
  .rooms-grid{grid-template-columns:1fr}
  .form-grid{grid-template-columns:1fr}
  .user-info{display:none}
}

/* ── ROOM SUMMARY ── */
.room-summary-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:1.5rem}
.room-summary-card{background:var(--white);border:1px solid var(--border);border-radius:var(--r);padding:14px;display:flex;flex-direction:column;transition:all .2s}
.room-summary-card:hover{border-color:var(--gold);transform:translateY(-2px);box-shadow:0 4px 12px rgba(0,0,0,0.05)}
.room-sum-type{font-family:'Playfair Display',serif;font-size:15px;font-weight:600;margin-bottom:2px}
.room-sum-price{font-size:13px;color:var(--gold);font-weight:500}
.room-sum-meta{margin-top:12px;display:flex;justify-content:space-between;align-items:center;font-size:11px;color:var(--muted);padding-top:10px;border-top:1px solid var(--border)}
.room-sum-avail{color:var(--success);font-weight:600}
</style>
</head>
<body>
{% if session.user_id and not is_public %}
<nav>
  <div class="logo">Grand<span>Vista</span></div>
  <div class="nav-links">
    {% if session.role == 'Admin' %}
    <a href="{{ url_for('dashboard') }}" class="{{ 'active' if active=='dashboard' }}">Dashboard</a>
    {% endif %}
    <a href="{{ url_for('new_booking') }}" class="{{ 'active' if active=='new' }}">New Booking</a>
    {% if session.role == 'Admin' %}
    <a href="{{ url_for('users') }}" class="{{ 'active' if active=='users' }}">Users</a>
    <a href="{{ url_for('admin_rooms') }}" class="{{ 'active' if active=='rooms' }}">Rooms</a>
    <a href="{{ url_for('admin_logs') }}" class="{{ 'active' if active=='logs' }}">Logs</a>
    {% endif %}
  </div>
  <div class="nav-right">
    <div class="user-chip">
      <div class="avatar">{{ session.full_name[0]|upper }}</div>
      <div class="user-info">
        <div class="uname">{{ session.full_name }}</div>
        <div class="urole"><span class="badge-role role-{{ session.role }}">{{ session.role }}</span></div>
      </div>
    </div>
    <form method="post" action="{{ url_for('logout') }}" style="margin:0">
      <button class="btn-logout" type="submit">Sign Out</button>
    </form>
  </div>
</nav>
{% elif is_public %}
<nav style="justify-content:center">
  <div class="logo">Grand<span>Vista</span> Hotel</div>
</nav>
{% endif %}

{% with msgs = get_flashed_messages(with_categories=true) %}
{% if msgs %}
<div style="max-width:900px;margin:1rem auto;padding:0 1.5rem">
{% for cat, msg in msgs %}
<div class="alert alert-{{ cat }}">{{ msg }}</div>
{% endfor %}
</div>
{% endif %}
{% endwith %}

{% block body %}{% endblock %}
</body>
<script>
document.querySelectorAll('.room-card').forEach(card => {
  const radio = card.querySelector('input[type=radio]');
  if (!radio) return;
  if (radio.checked) card.classList.add('checked');
  card.addEventListener('click', () => {
    document.querySelectorAll('.room-card').forEach(c => c.classList.remove('checked'));
    card.classList.add('checked'); radio.checked = true; calcTotal();
  });
});
document.querySelectorAll('.amenity').forEach(chip => {
  const cb = chip.querySelector('input[type=checkbox]');
  if (!cb) return;
  if (cb.checked) chip.classList.add('checked');
  chip.addEventListener('click', () => {
    cb.checked = !cb.checked;
    chip.classList.toggle('checked', cb.checked); calcTotal();
  });
});
function calcTotal() {
  const ci = new Date(document.getElementById('checkin')?.value);
  const co = new Date(document.getElementById('checkout')?.value);
  if (isNaN(ci)||isNaN(co)||co<=ci) return;
  const nights = Math.round((co-ci)/86400000);
  const sel = document.querySelector('.room-card.checked input[type=radio]');
  const rp = sel ? parseInt(sel.dataset.price) : 0;
  let ap = 0;
  document.querySelectorAll('.amenity input:checked').forEach(cb => ap += parseInt(cb.dataset.price));
  const subtotal = (rp+ap)*nights;

  // Group Discount Logic
  const ad = parseInt(document.querySelector('select[name=adults]')?.value || 0);
  const ch = parseInt(document.querySelector('select[name=children]')?.value || 0);
  const guests = ad + ch;
  let disc = 0;
  if (guests >= 26) disc = 0.20;
  else if (guests >= 20) disc = 0.15;
  else if (guests >= 16) disc = 0.10;
  else if (guests >= 10) disc = 0.05;

  // Special Discount Logic
  const specType = document.querySelector('select[name=discount_type]')?.value;
  let specDisc = 0;
  if (['Senior Citizen', 'PWD', 'Pregnant'].includes(specType)) specDisc = 0.20;

  const totalDisc = Math.min(0.40, disc + specDisc);
  const total = Math.floor(subtotal * (1 - totalDisc));

  const el = document.getElementById('total-preview');
  if (el) {
    let txt = '₱'+total.toLocaleString('en-PH',{minimumFractionDigits:2});
    if (totalDisc > 0) txt += ' (' + (totalDisc*100) + '% Discount Applied)';
    el.textContent = txt;
  }
  const nEl = document.getElementById('nights-preview');
  if (nEl) nEl.textContent = nights+' night'+(nights!==1?'s':'');
}
['checkin','checkout'].forEach(id => { const el=document.getElementById(id); if(el) el.addEventListener('change',calcTotal); });
document.querySelectorAll('select[name=adults], select[name=children], select[name=discount_type]').forEach(s => s.addEventListener('change', calcTotal));
// Toggle password visibility
document.querySelectorAll('.toggle-pw').forEach(btn => {
  btn.addEventListener('click', () => {
    const inp = btn.previousElementSibling;
    inp.type = inp.type === 'password' ? 'text' : 'password';
    btn.textContent = inp.type === 'password' ? '👁' : '🙈';
  });
});
</script>
</html>"""


# ──────────────────────────────────────────────
#  SIGN IN
# ──────────────────────────────────────────────

LOGIN_TPL = BASE.replace("{% block body %}{% endblock %}", """
<div class="auth-wrap">
  <div class="auth-box">
    <div class="auth-top">
      <div class="auth-logo">Grand<span>Vista</span></div>
      <div class="auth-tagline">Hotel Reservation System</div>
    </div>
    <div class="auth-body">
      <p style="font-family:'Playfair Display',serif;font-size:20px;margin-bottom:1.25rem">Sign In</p>
      <form method="post">
        <div class="form-group">
          <label>Username</label>
          <input name="username" value="{{ form.username }}" autofocus autocomplete="username"/>
        </div>
        <div class="form-group">
          <label>Password</label>
          <div class="pw-wrap">
            <input name="password" type="password" autocomplete="current-password"/>
            <button type="button" class="toggle-pw">👁</button>
          </div>
        </div>
        <button class="btn btn-primary btn-full" type="submit" style="margin-top:.75rem">Sign In</button>
      </form>
      <div class="divider">or</div>
      <div style="text-align:center">
        <span style="font-size:13px;color:var(--muted)">Don't have an account?</span>
        <a href="{{ url_for('register') }}" style="font-size:13px;font-weight:500;margin-left:5px">Create account</a>
      </div>
    </div>
  </div>
</div>
""")

@app.route("/", methods=["GET","POST"])
def login():
    if session.get("user_id"):
        if session.get("role") == "Admin":
            return redirect(url_for("dashboard"))
        return redirect(url_for("bookings"))
    form = {"username": ""}
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        form["username"] = username
        if not username or not password:
            flash("Please enter your username and password.", "danger")
        else:
            conn = get_db()
            user = conn.execute(
                "SELECT * FROM users WHERE username=? AND password=?",
                (username, hash_pw(password))
            ).fetchone()
            conn.close()
            if user:
                session["user_id"]   = user["id"]
                session["username"]  = user["username"]
                session["full_name"] = user["full_name"]
                session["role"]      = user["role"]
                if user["role"] == "Admin":
                    log_action("Admin Logged In")
                    return redirect(url_for("dashboard"))
                log_action("Staff Logged In")
                return redirect(url_for("new_booking"))
            flash("Incorrect username or password.", "danger")
    return render_template_string(LOGIN_TPL, form=form, active=None)


# ──────────────────────────────────────────────
#  SIGN UP / REGISTER
# ──────────────────────────────────────────────

REGISTER_TPL = BASE.replace("{% block body %}{% endblock %}", """
<div class="auth-wrap">
  <div class="auth-box">
    <div class="auth-top">
      <div class="auth-logo">Grand<span>Vista</span></div>
      <div class="auth-tagline">Create Your Account</div>
    </div>
    <div class="auth-body">
      <p style="font-family:'Playfair Display',serif;font-size:20px;margin-bottom:1.25rem">Create Account</p>
      <form method="post">
        <div class="form-group">
          <label>Full Name</label>
          <input name="full_name" value="{{ form.full_name }}" placeholder="e.g. Maria Santos" autofocus/>
        </div>
        <div class="form-group">
          <label>Email Address</label>
          <input name="email" type="email" value="{{ form.email }}" placeholder="you@email.com"/>
        </div>
        <div class="form-group">
          <label>Username</label>
          <input name="username" value="{{ form.username }}" placeholder="Choose a username"/>
          <div class="field-hint">Letters and numbers only, no spaces</div>
        </div>
        <div class="form-group">
          <label>Password</label>
          <div class="pw-wrap">
            <input name="password" type="password" placeholder="At least 6 characters" autocomplete="new-password"/>
            <button type="button" class="toggle-pw">👁</button>
          </div>
        </div>
        <div class="form-group">
          <label>Confirm Password</label>
          <div class="pw-wrap">
            <input name="password2" type="password" placeholder="Re-enter password" autocomplete="new-password"/>
            <button type="button" class="toggle-pw">👁</button>
          </div>
        </div>
        <button class="btn btn-primary btn-full" type="submit" style="margin-top:.75rem">Create Account</button>
      </form>
      <div class="divider">or</div>
      <div style="text-align:center">
        <span style="font-size:13px;color:var(--muted)">Already have an account?</span>
        <a href="{{ url_for('login') }}" style="font-size:13px;font-weight:500;margin-left:5px">Sign in</a>
      </div>
    </div>
  </div>
</div>
""")

@app.route("/register", methods=["GET","POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    form = {"full_name":"","email":"","username":""}
    if request.method == "POST":
        full_name = request.form.get("full_name","").strip()
        email     = request.form.get("email","").strip()
        username  = request.form.get("username","").strip()
        password  = request.form.get("password","")
        password2 = request.form.get("password2","")
        form = {"full_name":full_name, "email":email, "username":username}

        errors = []
        if not full_name:                errors.append("Full name is required.")
        if not email or "@" not in email: errors.append("Valid email is required.")
        if not username:                  errors.append("Username is required.")
        if len(password) < 6:             errors.append("Password must be at least 6 characters.")
        if password != password2:         errors.append("Passwords do not match.")

        if not errors:
            conn = get_db()
            exists_u = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
            exists_e = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
            if exists_u: errors.append("Username already taken.")
            if exists_e: errors.append("Email already registered.")
            if not errors:
                conn.execute("""
                    INSERT INTO users (username, full_name, email, password, role, created_at)
                    VALUES (?,?,?,?,?,?)
                """, (username, full_name, email, hash_pw(password), "Staff", datetime.now().isoformat()))
                conn.commit()
                conn.close()
                flash(f"Account created! Welcome, {full_name}. Please sign in.", "success")
                return redirect(url_for("login"))
            conn.close()

        for e in errors:
            flash(e, "danger")

    return render_template_string(REGISTER_TPL, form=form, active=None)


# ──────────────────────────────────────────────
#  LOGOUT
# ──────────────────────────────────────────────

@app.post("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("login"))


# ──────────────────────────────────────────────
#  DASHBOARD
# ──────────────────────────────────────────────

DASHBOARD_TPL = BASE.replace("{% block body %}{% endblock %}", """
<div class="page">
  <p class="page-title">Dashboard</p>
  <div class="stats-grid">
    <div class="stat-card"><div class="stat-label">Total Revenue</div><div class="stat-val gold" style="font-size:22px">₱{{ stats.revenue }}</div></div>
  </div>

  
  <p style="font-family:'Playfair Display',serif;font-size:16px;margin-bottom:1rem">Housekeeping (Room Status)</p>
  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-label">Clean</div>
      <div class="stat-val" style="color:var(--success)">{{ stats.room_status.get('Clean', 0) }}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Dirty</div>
      <div class="stat-val" style="color:var(--danger)">{{ stats.room_status.get('Dirty', 0) }}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Under Maintenance</div>
      <div class="stat-val" style="color:var(--gold)">{{ stats.room_status.get('Maintenance', 0) }}</div>
    </div>
  </div>
  
  <p style="font-family:'Playfair Display',serif;font-size:16px;margin-bottom:1rem">Revenue Breakdown</p>
  <div class="stats-grid">
    <a href="{{ url_for('bookings', pay='Cash') }}" class="stat-card" style="text-decoration:none;display:block">
      <div class="stat-label">Cash Total</div>
      <div class="stat-val" style="font-size:18px">₱{{ stats.rev_cash }}</div>
    </a>
    <a href="{{ url_for('bookings', pay='Card') }}" class="stat-card" style="text-decoration:none;display:block">
      <div class="stat-label">Card Total</div>
      <div class="stat-val" style="font-size:18px">₱{{ stats.rev_card }}</div>
    </a>
  </div>
  </div>
</div>

""")

@app.get("/test")
def test_route():
    return "<h1>GrandVista Server is Online!</h1><p>If you see this, the server is working correctly.</p>"

@app.get("/dashboard")
@admin_required
def dashboard():
    conn    = get_db()
    total   = conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
    checkin = conn.execute("SELECT COUNT(*) FROM bookings WHERE status='Checked In'").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM bookings WHERE status='Pending'").fetchone()[0]
    rev     = conn.execute("SELECT SUM(total) FROM bookings WHERE status!='Cancelled'").fetchone()[0] or 0
    
    # Revenue Breakdown
    rev_cash  = conn.execute("SELECT SUM(total) FROM bookings WHERE status!='Cancelled' AND payment_method='Cash'").fetchone()[0] or 0
    rev_card  = conn.execute("SELECT SUM(total) FROM bookings WHERE status!='Cancelled' AND payment_method='Card'").fetchone()[0] or 0
    
    # Booking Types Breakdown
    online  = conn.execute("SELECT COUNT(*) FROM bookings WHERE booking_type='Online'").fetchone()[0]
    walkin  = conn.execute("SELECT COUNT(*) FROM bookings WHERE booking_type='Walk-in'").fetchone()[0]
    
    recent  = conn.execute("SELECT * FROM bookings ORDER BY created_at DESC LIMIT 10").fetchall()
    
    # Room Status for Dashboard
    room_stats = conn.execute("SELECT status, COUNT(*) as count FROM rooms GROUP BY status").fetchall()
    
    conn.close()
    stats = {
        "total":total, "checkin":checkin, "pending":pending, "revenue":f"{rev:,.2f}",
        "rev_cash": f"{rev_cash:,.2f}", "rev_card": f"{rev_card:,.2f}",
        "online": online, "walkin": walkin,
        "room_status": {r['status']: r['count'] for r in room_stats}
    }
    return render_template_string(DASHBOARD_TPL, stats=stats, bookings=recent, active="dashboard")

@app.route("/bookings")
@login_required
def bookings():
    return redirect(url_for("new_booking"))





# ──────────────────────────────────────────────
#  VIEW / UPDATE BOOKING
# ──────────────────────────────────────────────

VIEW_TPL = BASE.replace("{% block body %}{% endblock %}", """
<div class="page">
  <div style="margin-bottom:1rem; display:flex; justify-content:space-between; align-items:center;">
    <a href="{{ url_for('dashboard') if session.role == 'Admin' else url_for('new_booking') }}" class="btn btn-secondary" style="padding:5px 14px;font-size:12px">← Back</a>
    <a href="{{ url_for('booking_receipt', ref=b['ref']) }}" target="_blank" class="btn btn-secondary" style="font-size:12px">📄 Print Receipt</a>
  </div>
  <p class="page-title">Booking: {{ b['ref'] }}</p>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem">
    <div class="card">
      <p style="font-family:'Playfair Display',serif;font-size:15px;margin-bottom:.75rem">Guest Details</p>
      <div class="info-row"><span>Name</span><span>{{ b['fname'] }} {{ b['lname'] }}</span></div>
      <div class="info-row"><span>Email</span><span>{{ b['email'] }}</span></div>
      <div class="info-row"><span>Phone</span><span>{{ b['phone'] }}</span></div>
      <div class="info-row"><span>Adults</span><span>{{ b['adults'] }}</span></div>
      <div class="info-row"><span>Children</span><span>{{ b['children'] }}</span></div>
      <div class="info-row"><span>Special Disc.</span><span>{{ b['discount_type'] }}</span></div>
      <div class="info-row"><span>Pay Method</span><span>{{ b['payment_method'] }}</span></div>
      <div class="info-row"><span>Booking Type</span><span style="font-weight:500;color:{{ 'var(--gold)' if b['booking_type']=='Online' else 'inherit' }}">{{ b['booking_type'] }}</span></div>
    </div>
    <div class="card">
      <p style="font-family:'Playfair Display',serif;font-size:15px;margin-bottom:.75rem">Stay Details</p>
      <div class="info-row"><span>Room</span><span>{{ b['room_type'] }}</span></div>
      <div class="info-row"><span>Check-in</span><span>{{ b['checkin'] }}</span></div>
      <div class="info-row"><span>Check-out</span><span>{{ b['checkout'] }}</span></div>
      <div class="info-row"><span>Nights</span><span>{{ b['nights'] }}</span></div>
      <div class="info-row"><span>Amenities</span><span>{{ b['amenities'] or 'None' }}</span></div>
    </div>
  </div>
  <div class="card">
    <p style="font-family:'Playfair Display',serif;font-size:15px;margin-bottom:.75rem">Payment Summary</p>
    <div class="summary">
      <div class="sum-row"><span>Room ({{ b['nights'] }} nights)</span><span>₱{{ "{:,.2f}".format(b['room_total']) }}</span></div>
      <div class="sum-row"><span>Amenities</span><span>₱{{ "{:,.2f}".format(b['amen_total']) }}</span></div>
      <div class="sum-row total"><span>Total</span><span>₱{{ "{:,.2f}".format(b['total']) }}</span></div>
    </div>
    {% if b['requests'] %}<p style="font-size:13px;color:var(--muted)">Requests: {{ b['requests'] }}</p>{% endif %}
  </div>

  {% if b['status'] != 'Checked In' and b['status'] != 'Cancelled' %}
  <div class="card" style="border-left:4px solid var(--gold);background:var(--gold-l)">
    <div style="display:flex;justify-content:space-between;align-items:center">
      <div>
        <p style="font-family:'Playfair Display',serif;font-size:16px;color:var(--gold-d)">Ready for Check-In?</p>
        <p style="font-size:12px;color:var(--muted)">Click the button to confirm guest arrival.</p>
      </div>
      <form method="post" style="margin:0">
        <button class="btn btn-primary" name="status" value="Checked In" type="submit" style="padding:10px 30px">Check In Now</button>
      </form>
    </div>
  </div>
  {% endif %}
  <div class="card">
    <p style="font-family:'Playfair Display',serif;font-size:15px;margin-bottom:.75rem">Update Status</p>
    <p style="font-size:13px;color:var(--muted);margin-bottom:.75rem">Current: <span class="badge badge-{{ b['status'].split()[0] }}">{{ b['status'] }}</span></p>
    <form method="post" style="display:flex;gap:8px;flex-wrap:wrap">
      {% for s in ['Pending','Confirmed','Checked In','Cancelled'] %}
      <button class="btn {{ 'btn-primary' if b['status']==s else 'btn-secondary' }}" name="status" value="{{ s }}" type="submit">{{ s }}</button>
      {% endfor %}
    </form>
  </div>
</div>
""")

@app.route("/bookings/<ref>", methods=["GET","POST"])
@login_required
def view_booking(ref):
    conn = get_db()
    if request.method == "POST":
        new_status = request.form.get("status")
        if new_status in ["Pending","Confirmed","Checked In","Cancelled"]:
            conn.execute("UPDATE bookings SET status=? WHERE ref=?", (new_status, ref))
            conn.commit()
            log_action(f"Updated booking {ref} status to {new_status}")
            flash(f"Status updated to '{new_status}'.", "success")
    b = conn.execute("SELECT * FROM bookings WHERE ref=?", (ref,)).fetchone()
    conn.close()
    if not b:
        flash("Booking not found.", "danger")
        return redirect(url_for("bookings"))
    return render_template_string(VIEW_TPL, b=b, active="bookings")


# ──────────────────────────────────────────────
#  RECEIPT / INVOICE
# ──────────────────────────────────────────────

RECEIPT_TPL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><title>Receipt - {{ b.ref }}</title>
<style>
    body { font-family: 'Courier New', Courier, monospace; color: #333; line-height: 1.4; padding: 40px; }
    .receipt { max-width: 500px; margin: 0 auto; border: 1px solid #eee; padding: 30px; box-shadow: 0 0 10px rgba(0,0,0,0.05); }
    .header { text-align: center; margin-bottom: 30px; border-bottom: 2px dashed #eee; padding-bottom: 20px; }
    .logo { font-size: 24px; font-weight: bold; }
    .item { display: flex; justify-content: space-between; margin-bottom: 8px; }
    .total { border-top: 2px dashed #eee; margin-top: 20px; padding-top: 15px; font-size: 18px; font-weight: bold; }
    .footer { text-align: center; margin-top: 40px; font-size: 12px; color: #888; }
    @media print { .no-print { display: none; } }
</style>
</head>
<body>
<div class="no-print" style="text-align:center; margin-bottom: 20px;">
    <button onclick="window.print()" style="padding:10px 20px; cursor:pointer;">Print Receipt</button>
</div>
<div class="receipt">
    <div class="header">
        <div class="logo">GRANDVISTA HOTEL</div>
        <p>123 Luxury Lane, Seaside City<br>Tel: (02) 888-Vista</p>
        <p style="margin-top:15px;"><strong>OFFICIAL RECEIPT</strong></p>
    </div>
    <div class="item"><span>Date:</span> <span>{{ b.created_at[:10] }}</span></div>
    <div class="item"><span>Ref:</span> <span>{{ b.ref }}</span></div>
    <div class="item"><span>Guest:</span> <span>{{ b.fname }} {{ b.lname }}</span></div>
    <hr style="border:0; border-top:1px solid #eee; margin:15px 0;">
    <div class="item"><span>Room ({{ b.nights }} nights):</span> <span>₱{{ "{:,.2f}".format(b.room_total) }}</span></div>
    <div class="item"><span>Amenities:</span> <span>₱{{ "{:,.2f}".format(b.amen_total) }}</span></div>
    <div class="item"><span>Discount ({{ b.discount_type }}):</span> <span>-₱{{ "{:,.2f}".format((b.room_total + b.amen_total) - b.total) }}</span></div>
    <div class="total"><span>TOTAL:</span> <span>₱{{ "{:,.2f}".format(b.total) }}</span></div>
    <div class="item" style="margin-top:10px; font-size:12px;"><span>Payment Method:</span> <span>{{ b.payment_method }}</span></div>
    <div class="footer">
        <p>Thank you for staying with us!</p>
        <p>Please come again.</p>
    </div>
</div>
</body>
</html>"""

@app.route("/bookings/<ref>/receipt")
@login_required
def booking_receipt(ref):
    conn = get_db()
    b = conn.execute("SELECT * FROM bookings WHERE ref=?", (ref,)).fetchone()
    conn.close()
    if not b: return "Booking not found", 404
    return render_template_string(RECEIPT_TPL, b=b)


# ──────────────────────────────────────────────
#  NEW BOOKING
# ──────────────────────────────────────────────

NEW_TPL = BASE.replace("{% block body %}{% endblock %}", """
<div class="page">
  <p class="page-title">New Booking</p>
  
  <p style="font-family:'Playfair Display',serif;font-size:16px;margin-bottom:1rem">Room Types & Availability</p>
  <div class="room-summary-grid">
    {% for rs in room_summary %}
    <div class="room-summary-card">
      <div class="room-sum-type">{{ rs['type'] }}</div>
      <div class="room-sum-price">₱{{ "{:,.2f}".format(rs['price']) }} <span style="font-size:10px;font-weight:400;color:var(--muted)">/ night</span></div>
      <div style="font-size:11px; color:var(--muted); margin-top:8px; line-height:1.4">
        {{ rs['features'] }}
      </div>
      <div class="room-sum-meta">
        <span>Max: {{ rs['capacity'] }} pax</span>
        <span class="room-sum-avail">{{ rs['clean_units'] }} Available</span>
      </div>
    </div>
    {% endfor %}
  </div>

  <form method="post">
    <div class="card">
      <p class="form-section">Guest Information</p>
      <div class="form-grid">
        <div class="form-group"><label>First Name</label><input name="fname" value="{{ form.fname }}" required/></div>
        <div class="form-group"><label>Last Name</label><input name="lname" value="{{ form.lname }}" required/></div>
        <div class="form-group"><label>Email</label><input name="email" type="email" value="{{ form.email }}" required/></div>
        <div class="form-group"><label>Phone</label><input name="phone" value="{{ form.phone }}" required/></div>
        <div class="form-group"><label>Adults</label>
          <select name="adults">{% for i in range(1,31) %}<option {{ 'selected' if form.adults==i|string }}>{{ i }}</option>{% endfor %}</select>
        </div>
        <div class="form-group"><label>Children</label>
          <select name="children">{% for i in range(0,31) %}<option {{ 'selected' if form.children==i|string }}>{{ i }}</option>{% endfor %}</select>
        </div>
        <div class="form-group"><label>Special Discount</label>
          <select name="discount_type">
            <option value="None" {{ 'selected' if form.discount_type=='None' }}>None</option>
            <option value="Senior Citizen" {{ 'selected' if form.discount_type=='Senior Citizen' }}>Senior Citizen (20%)</option>
            <option value="PWD" {{ 'selected' if form.discount_type=='PWD' }}>PWD (20%)</option>
            <option value="Pregnant" {{ 'selected' if form.discount_type=='Pregnant' }}>Pregnant (20%)</option>
          </select>
        </div>
        <div class="form-group"><label>Payment Method</label>
          <select name="payment_method">
            <option value="Cash" {{ 'selected' if form.payment_method=='Cash' }}>Cash</option>
            <option value="Card" {{ 'selected' if form.payment_method=='Card' }}>Card / Bank Transfer (PayPal/BDO)</option>
          </select>
        </div>
        <div class="form-group"><label>Booking Type</label>
          <select name="booking_type">
            <option value="Walk-in" {{ 'selected' if form.booking_type=='Walk-in' }}>Walk-in (Staff)</option>
            <option value="Online" {{ 'selected' if form.booking_type=='Online' }}>Online Registration</option>
          </select>
        </div>
      </div>
    </div>
    <div class="card">
      <p class="form-section">Stay Dates</p>
      <div class="form-grid">
        <div class="form-group"><label>Check-in</label><input id="checkin" name="checkin" type="date" value="{{ form.checkin }}" required/></div>
        <div class="form-group"><label>Check-out</label><input id="checkout" name="checkout" type="date" value="{{ form.checkout }}" required/></div>
      </div>
    </div>
    <div class="card">
      <p class="form-section">Select Room</p>
      <div class="rooms-grid">
      {% for r in rooms %}
        <label class="room-card {{ 'checked' if form.room==r.id|string }}">
          <input type="radio" name="room" value="{{ r.id }}" data-price="{{ r.price }}" {{ 'checked' if form.room==r.id|string }} required/>
          <div class="room-name">{{ r.type }}</div>
          <div class="room-price">₱{{ "{:,}".format(r.price) }}<span style="font-size:11px;color:var(--muted)">/night</span></div>
          <div class="room-feat">Max {{ r.capacity }} guests</div>
        </label>
      {% endfor %}
      </div>
    </div>
    <div class="card">
      <p class="form-section">Add-on Amenities <span style="font-size:12px;font-family:'DM Sans',sans-serif;color:var(--muted)">(per night)</span></p>
      <div class="amenities">
      {% for a in amenities %}
        <label class="amenity {{ 'checked' if a.id in form.amenities }}">
          <input type="checkbox" name="amenities" value="{{ a.id }}" data-price="{{ a.price }}" {{ 'checked' if a.id in form.amenities }}/>
          {{ a.name }} +₱{{ "{:,}".format(a.price) }}
        </label>
      {% endfor %}
      </div>
    </div>
    <div class="card">
      <p class="form-section">Special Requests</p>
      <div class="form-grid single">
        <div class="form-group"><textarea name="requests" placeholder="Any special requests…">{{ form.requests }}</textarea></div>
      </div>
      <div style="background:var(--cream);border:1px solid var(--border);border-radius:var(--r);padding:12px 16px;margin-top:.5rem;display:flex;justify-content:space-between;align-items:center">
        <span style="font-size:13px;color:var(--muted)" id="nights-preview"></span>
        <span style="font-size:15px;font-weight:500">Estimated Total: <span id="total-preview" style="color:var(--gold)">—</span></span>
      </div>
    </div>
    <div class="btn-row">
      <a href="{{ url_for('dashboard') if session.role == 'Admin' else url_for('new_booking') }}" class="btn btn-secondary">Cancel</a>
      <button class="btn btn-primary" type="submit">Confirm Booking</button>
    </div>
  </form>
</div>
""")

@app.route("/new", methods=["GET","POST"])
@login_required
def new_booking():
    form = {"fname":"","lname":"","email":"","phone":"","adults":"1","children":"0",
            "checkin":"","checkout":"","room":"","amenities":[],"requests":"","discount_type":"None","payment_method":"Cash"}
    if request.method == "POST":
        form = {k: request.form.get(k,"").strip() for k in ["fname","lname","email","phone","checkin","checkout","room","requests","discount_type","payment_method","booking_type"]}
        form["adults"]    = request.form.get("adults","1")
        form["children"]  = request.form.get("children","0")
        form["amenities"] = request.form.getlist("amenities")
        errors = []
        if not form["fname"]: errors.append("First name is required.")
        if not form["lname"]: errors.append("Last name is required.")
        if not form["email"] or "@" not in form["email"]: errors.append("Valid email is required.")
        if not form["phone"]: errors.append("Phone is required.")
        if not form["checkin"] or not form["checkout"]: errors.append("Dates are required.")
        if not form["room"]: errors.append("Please select a room.")
        if not errors:
            ci = date.fromisoformat(form["checkin"])
            co = date.fromisoformat(form["checkout"])
            if co <= ci: errors.append("Check-out must be after check-in.")
        if not errors:
            nights   = (co - ci).days
            room     = next(r for r in ROOMS if str(r["id"]) == form["room"])
            room_tot = room["price"] * nights
            am_tot   = sum(a["price"] for a in AMENITIES if a["id"] in form["amenities"]) * nights
            
            # Group Discount Logic
            guests = int(form["adults"]) + int(form["children"])
            disc_pct = 0
            if 10 <= guests <= 15: disc_pct = 0.05
            elif 16 <= guests <= 19: disc_pct = 0.10
            elif 20 <= guests <= 25: disc_pct = 0.15
            elif guests >= 26: disc_pct = 0.20
            
            # Special Discount Logic (20% for Senior/PWD/Pregnant)
            spec_disc = 0
            if form["discount_type"] in ["Senior Citizen", "PWD", "Pregnant"]:
                spec_disc = 0.20
            
            # Combine Discounts (Sequential or Additive? Usually additive or higher-of.
            # I'll use additive but cap at 40% for simplicity)
            total_disc = disc_pct + spec_disc
            if total_disc > 0.40: total_disc = 0.40
            
            subtotal = room_tot + am_tot
            total = int(subtotal * (1 - total_disc))
            
            ref      = rand_ref()
            conn = get_db()
            conn.execute("""
                INSERT INTO bookings (ref,fname,lname,email,phone,checkin,checkout,nights,
                adults,children,room_id,room_type,amenities,room_total,amen_total,total,
                status,discount_type,payment_method,booking_type,requests,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (ref, form["fname"], form["lname"], form["email"], form["phone"],
                  form["checkin"], form["checkout"], nights,
                  int(form["adults"]), int(form["children"]),
                  room["id"], room["type"], ",".join(form["amenities"]),
                  room_tot, am_tot, total,
                  "Checked In", form["discount_type"], form["payment_method"], form["booking_type"], form["requests"], datetime.now().isoformat()))
            conn.commit()
            conn.close()
            msg = f"Booking created! Reference: {ref}"
            if total_disc > 0: msg += f" ({int(total_disc*100)}% total discount applied!)"
            log_action(f"Created booking {ref} for {form['fname']} {form['lname']}")
            flash(msg, "success")
            return redirect(url_for("view_booking", ref=ref))
        for e in errors:
            flash(e, "danger")
    
    conn = get_db()
    room_summary = conn.execute("""
        SELECT type, price, capacity, features,
               COUNT(*) as total_units,
               SUM(CASE WHEN status='Clean' THEN 1 ELSE 0 END) as clean_units
        FROM rooms
        GROUP BY type
    """).fetchall()
    all_rooms = conn.execute("SELECT * FROM rooms").fetchall()
    conn.close()
    
    return render_template_string(NEW_TPL, rooms=all_rooms, room_summary=room_summary, amenities=AMENITIES, form=form, active="new")


# ──────────────────────────────────────────────
#  USER MANAGEMENT  (Admin only)
# ──────────────────────────────────────────────

USERS_TPL = BASE.replace("{% block body %}{% endblock %}", """
<div class="page">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1.5rem">
    <p class="page-title" style="margin:0">User Management</p>
    <a href="{{ url_for('register') }}" class="btn btn-primary">+ Add User</a>
  </div>
  <div class="card">
    <div class="tbl-wrap"><table>
      <thead><tr><th>Name</th><th>Username</th><th>Email</th><th>Role</th><th>Created</th><th></th></tr></thead>
      <tbody>
      {% for u in users %}
      <tr>
        <td>{{ u['full_name'] }}</td>
        <td><code style="font-size:12px">{{ u['username'] }}</code></td>
        <td>{{ u['email'] }}</td>
        <td><span class="badge-role role-{{ u['role'] }}">{{ u['role'] }}</span></td>
        <td style="font-size:12px;color:var(--muted)">{{ u['created_at'][:10] }}</td>
        <td>
          {% if u['username'] != session.username %}
          <form method="post" action="{{ url_for('delete_user', uid=u['id']) }}"
            onsubmit="return confirm('Delete {{ u['full_name'] }}?')" style="display:inline">
            <button class="btn btn-danger" style="padding:3px 10px;font-size:11px" type="submit">Delete</button>
          </form>
          {% else %}
          <span style="font-size:11px;color:var(--muted)">(you)</span>
          {% endif %}
        </td>
      </tr>
      {% endfor %}
      </tbody>
    </table></div>
    <p style="font-size:12px;color:var(--muted);margin-top:.75rem">{{ users|length }} user(s)</p>
  </div>
</div>
""")

@app.get("/users")
@admin_required
def users():
    conn = get_db()
    all_users = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    conn.close()
    return render_template_string(USERS_TPL, users=all_users, active="users")

@app.post("/users/<int:uid>/delete")
@admin_required
def delete_user(uid):
    conn = get_db()
    u = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if u and u["username"] != session["username"]:
        conn.execute("DELETE FROM users WHERE id=?", (uid,))
        conn.commit()
        flash(f"User '{u['full_name']}' deleted.", "success")
    conn.close()
    return redirect(url_for("users"))


# ──────────────────────────────────────────────
#  PUBLIC RESERVATION (ONLINE BOOKING)
# ──────────────────────────────────────────────

PUBLIC_BOOKING_TPL = BASE.replace("{% block body %}{% endblock %}", """
<div class="page">
  <div style="text-align:center;margin-bottom:2rem">
    <p style="font-family:'Playfair Display',serif;font-size:28px;color:var(--gold-d);margin-bottom:.5rem">GrandVista Online Reservation</p>
    <p style="font-size:14px;color:var(--muted)">Book your stay with us in just a few clicks.</p>
  </div>
  
  <form method="post">
    <div class="card">
      <p class="form-section">Guest Information</p>
      <div class="form-grid">
        <div class="form-group"><label>First Name</label><input name="fname" required/></div>
        <div class="form-group"><label>Last Name</label><input name="lname" required/></div>
        <div class="form-group"><label>Email</label><input name="email" type="email" required/></div>
        <div class="form-group"><label>Phone</label><input name="phone" required/></div>
        <div class="form-group"><label>Adults</label>
          <select name="adults">{% for i in range(1,31) %}<option>{{ i }}</option>{% endfor %}</select>
        </div>
        <div class="form-group"><label>Children</label>
          <select name="children">{% for i in range(0,31) %}<option>{{ i }}</option>{% endfor %}</select>
        </div>
        <div class="form-group"><label>Special Discount</label>
          <select name="discount_type">
            <option value="None">None</option>
            <option value="Senior Citizen">Senior Citizen (20%)</option>
            <option value="PWD">PWD (20%)</option>
            <option value="Pregnant">Pregnant (20%)</option>
          </select>
        </div>
        <div class="form-group"><label>Payment Method</label>
          <select name="payment_method" id="pay_method_select">
            <option value="Card">Card / Bank Transfer</option>
            <option value="Cash">Cash (Upon Arrival)</option>
          </select>
          <div id="card-details" style="display:block; margin-top:12px; padding:12px; background:var(--light); border:1px solid var(--border); border-radius:var(--r); font-size:12px; color:var(--text)">
            <p style="font-weight:600; margin-bottom:5px; color:var(--gold-d)">Payment Instructions:</p>
            <div style="display:grid; gap:4px">
              <div><strong>PayPal:</strong> payments@grandvistahotel.com</div>
              <div><strong>BDO:</strong> 00123 456 7890 (GrandVista Hotel)</div>
              <div><strong>GCash/Maya:</strong> 0912 345 6789</div>
            </div>
            <p style="margin-top:8px; font-size:11px; color:var(--muted)">* Please send a screenshot of your receipt to our email after payment.</p>
          </div>
        </div>
      </div>
    </div>
    
    <div class="card">
      <p class="form-section">Stay Details</p>
      <div class="form-grid">
        <div class="form-group"><label>Check-in</label><input id="checkin" name="checkin" type="date" required/></div>
        <div class="form-group"><label>Check-out</label><input id="checkout" name="checkout" type="date" required/></div>
      </div>
      <p class="form-section" style="margin-top:1rem">Select Room</p>
      <div class="rooms-grid">
      {% for r in rooms %}
        <label class="room-card">
          <input type="radio" name="room" value="{{ r.id }}" data-price="{{ r.price }}" required/>
          <div class="room-name">{{ r.type }}</div>
          <div class="room-price">₱{{ "{:,.0f}".format(r.price) }}/night</div>
        </label>
      {% endfor %}
      </div>
    </div>

    <div class="card">
      <div style="background:var(--gold-l);padding:15px;border-radius:var(--r);text-align:center">
        <p style="font-size:12px;color:var(--muted);margin-bottom:.5rem" id="nights-preview">Pick dates to see total</p>
        <p style="font-size:18px;font-weight:600">Total: <span id="total-preview" style="color:var(--gold-d)">—</span></p>
      </div>
      <button class="btn btn-primary btn-full" type="submit" style="margin-top:1rem;padding:15px">Confirm Online Reservation</button>
    </div>
  </form>
</div>
<script>
function calcTotal() {
  const ci = new Date(document.getElementById('checkin')?.value);
  const co = new Date(document.getElementById('checkout')?.value);
  if (isNaN(ci)||isNaN(co)||co<=ci) return;
  const nights = Math.round((co-ci)/86400000);
  const sel = document.querySelector('.room-card input[type=radio]:checked');
  const rp = sel ? parseInt(sel.dataset.price) : 0;
  const subtotal = rp * nights;

  const ad = parseInt(document.querySelector('select[name=adults]')?.value || 0);
  const ch = parseInt(document.querySelector('select[name=children]')?.value || 0);
  const guests = ad + ch;
  let disc = 0;
  if (guests >= 26) disc = 0.20;
  else if (guests >= 20) disc = 0.15;
  else if (guests >= 16) disc = 0.10;
  else if (guests >= 10) disc = 0.05;

  const specType = document.querySelector('select[name=discount_type]')?.value;
  let specDisc = 0;
  if (['Senior Citizen', 'PWD', 'Pregnant'].includes(specType)) specDisc = 0.20;

  const totalDisc = Math.min(0.40, disc + specDisc);
  const total = Math.floor(subtotal * (1 - totalDisc));

  document.getElementById('total-preview').textContent = '₱' + total.toLocaleString();
  document.getElementById('nights-preview').textContent = nights + ' night(s)';
}
document.querySelectorAll('input, select').forEach(el => el.addEventListener('change', calcTotal));
const paySelect = document.getElementById('pay_method_select');
const cardBox = document.getElementById('card-details');
if (paySelect && cardBox) {
  paySelect.addEventListener('change', () => {
    cardBox.style.display = paySelect.value === 'Card' ? 'block' : 'none';
  });
}
document.querySelectorAll('.room-card').forEach(card => {
  card.addEventListener('click', () => {
    document.querySelectorAll('.room-card').forEach(c => c.classList.remove('checked'));
    card.classList.add('checked');
  });
});
</script>
""")

@app.route("/reserve", methods=["GET","POST"])
def reserve():
    if request.method == "POST":
        fname   = request.form.get("fname")
        lname   = request.form.get("lname")
        email   = request.form.get("email")
        phone   = request.form.get("phone")
        adults  = int(request.form.get("adults", 1))
        children = int(request.form.get("children", 0))
        checkin = request.form.get("checkin")
        checkout = request.form.get("checkout")
        room_id  = int(request.form.get("room"))
        disc_type = request.form.get("discount_type", "None")
        pay_method = request.form.get("payment_method", "Cash")
        
        # Simple Logic
        room = next((r for r in ROOMS if r["id"] == room_id), ROOMS[0])
        d1, d2 = datetime.strptime(checkin, "%Y-%m-%d"), datetime.strptime(checkout, "%Y-%m-%d")
        nights = (d2 - d1).days
        room_tot = room["price"] * nights
        
        # Discounts
        guests = adults + children
        disc_pct = 0
        if guests >= 26: disc_pct = 0.20
        elif guests >= 20: disc_pct = 0.15
        elif guests >= 16: disc_pct = 0.10
        elif guests >= 10: disc_pct = 0.05
        
        spec_disc = 0.20 if disc_type in ["Senior Citizen", "PWD", "Pregnant"] else 0
        total_disc = min(0.40, disc_pct + spec_disc)
        total = int(room_tot * (1 - total_disc))
        
        ref = rand_ref()
        conn = get_db()
        conn.execute("""
            INSERT INTO bookings (ref,fname,lname,email,phone,checkin,checkout,nights,
            adults,children,room_id,room_type,amenities,room_total,amen_total,total,
            status,discount_type,payment_method,booking_type,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (ref, fname, lname, email, phone, checkin, checkout, nights,
              adults, children, room["id"], room["type"], "", room_tot, 0, total,
              "Checked In", disc_type, pay_method, "Online", datetime.now().isoformat()))
        conn.commit()
        conn.close()
        
        payment_info = ""
        if pay_method == "Card":
            payment_info = """
            <div style="background:#f9f7f2; border:1px solid #e8e4dc; padding:15px; border-radius:8px; margin:20px 0; display:inline-block; text-align:left; font-size:14px;">
                <p style="font-weight:600; color:#B8974A; margin-bottom:10px;">Payment Instructions (Card/Bank Transfer):</p>
                <p><strong>PayPal:</strong> payments@grandvistahotel.com</p>
                <p><strong>BDO:</strong> 00123 456 7890 (GrandVista Hotel)</p>
                <p><strong>GCash/Maya:</strong> 0912 345 6789</p>
                <p style="font-size:12px; color:#6B6459; margin-top:10px;">* Please email your proof of payment to booking@grandvistahotel.com</p>
            </div>
            """

        return f"""
        <div style="font-family:sans-serif; text-align:center; padding:50px; background:#FAF8F4; min-height:100vh;">
            <div style="max-width:600px; margin:0 auto; background:white; padding:40px; border-radius:12px; border:1px solid #e8e4dc; box-shadow:0 4px 20px rgba(0,0,0,0.05);">
                <h1 style="color:#B8974A; font-family:'Playfair Display',serif; margin-bottom:10px;">Reservation Successful!</h1>
                <p style="color:#6B6459;">Thank you for choosing GrandVista Hotel.</p>
                <div style="margin:30px 0; padding:20px; border:2px dashed #B8974A; display:inline-block;">
                    <p style="font-size:12px; color:#6B6459; text-transform:uppercase; letter-spacing:2px; margin-bottom:5px;">Your Reference Code</p>
                    <strong style="font-size:32px; color:#1C1A17; letter-spacing:2px;">{ref}</strong>
                </div>
                {payment_info}
                <p style="color:#6B6459; margin-bottom:30px;">Please save this code for your arrival.</p>
                <a href="/reserve" style="display:inline-block; padding:12px 30px; background:#B8974A; color:white; text-decoration:none; border-radius:8px; font-weight:500;">Make another reservation</a>
            </div>
        </div>
        """
        
    return render_template_string(PUBLIC_BOOKING_TPL, rooms=get_rooms(), is_public=True)


# ──────────────────────────────────────────────
#  ADMIN: ROOM MANAGEMENT
# ──────────────────────────────────────────────

ADMIN_ROOMS_TPL = BASE.replace("{% block body %}{% endblock %}", """
<div class="page">
  <p class="page-title">Room Management</p>
  <div class="card">
    <p class="form-section">Add New Room</p>
    <form method="post" action="{{ url_for('admin_add_room') }}" class="form-grid">
      <div class="form-group"><label>Room Type</label><input name="type" placeholder="e.g. Presidential Suite" required/></div>
      <div class="form-group"><label>Price/Night</label><input name="price" type="number" required/></div>
      <div class="form-group"><label>Capacity</label><input name="capacity" type="number" required/></div>
      <div class="form-group" style="display:flex;align-items:flex-end">
        <button class="btn btn-primary" type="submit">+ Add Room</button>
      </div>
    </form>
  </div>
  <div class="card">
    <div class="tbl-wrap"><table>
      <thead><tr><th>ID</th><th>Type</th><th>Price</th><th>Cap</th><th>Status</th><th>Action</th></tr></thead>
      <tbody>
      {% for r in rooms %}
      <tr>
        <td>{{ r.id }}</td>
        <td><strong>{{ r.type }}</strong></td>
        <td>₱{{ "{:,}".format(r.price) }}</td>
        <td>{{ r.capacity }}</td>
        <td>
            <form method="post" action="{{ url_for('admin_update_room_status', rid=r.id) }}" style="margin:0">
                <select name="status" onchange="this.form.submit()" style="font-size:11px; padding:2px 5px; border-radius:4px;">
                    <option value="Clean" {{ 'selected' if r.status=='Clean' }}>Clean</option>
                    <option value="Dirty" {{ 'selected' if r.status=='Dirty' }}>Dirty</option>
                    <option value="Maintenance" {{ 'selected' if r.status=='Maintenance' }}>Repair</option>
                </select>
            </form>
        </td>
        <td>
          <form method="post" action="{{ url_for('admin_delete_room', rid=r.id) }}" onsubmit="return confirm('Delete this room?')">
            <button class="btn btn-danger" style="padding:3px 10px; font-size:11px;">Delete</button>
          </form>
        </td>
      </tr>
      {% endfor %}
      </tbody>
    </table></div>
  </div>
</div>
""")

@app.get("/admin/rooms")
@admin_required
def admin_rooms():
    return render_template_string(ADMIN_ROOMS_TPL, rooms=get_rooms(), active="rooms")

@app.post("/admin/rooms/add")
@admin_required
def admin_add_room():
    t, p, c = request.form.get("type"), request.form.get("price"), request.form.get("capacity")
    conn = get_db()
    conn.execute("INSERT INTO rooms (type, price, capacity) VALUES (?,?,?)", (t, p, c))
    conn.commit()
    conn.close()
    log_action(f"Added new room type: {t}")
    flash("Room added successfully.", "success")
    return redirect(url_for("admin_rooms"))

@app.post("/admin/rooms/<int:rid>/status")
@login_required
def admin_update_room_status(rid):
    new_status = request.form.get("status")
    conn = get_db()
    conn.execute("UPDATE rooms SET status=? WHERE id=?", (new_status, rid))
    conn.commit()
    conn.close()
    log_action(f"Updated room #{rid} status to {new_status}")
    flash("Room status updated.", "success")
    return redirect(request.referrer or url_for("admin_rooms"))

@app.post("/admin/rooms/<int:rid>/delete")
@admin_required
def admin_delete_room(rid):
    conn = get_db()
    conn.execute("DELETE FROM rooms WHERE id=?", (rid,))
    conn.commit()
    conn.close()
    log_action(f"Deleted room #{rid}")
    flash("Room deleted.", "info")
    return redirect(url_for("admin_rooms"))


# ──────────────────────────────────────────────
#  ADMIN: LOGS
# ──────────────────────────────────────────────

LOGS_TPL = BASE.replace("{% block body %}{% endblock %}", """
<div class="page">
  <p class="page-title">Activity Logs</p>
  <div class="card">
    <div class="tbl-wrap"><table>
      <thead><tr><th>User</th><th>Action</th><th>Time</th></tr></thead>
      <tbody>
      {% for l in logs %}
      <tr>
        <td style="font-weight:500">{{ l.user }}</td>
        <td>{{ l.action }}</td>
        <td style="color:var(--muted); font-size:12px;">{{ l.timestamp.replace('T', ' ')[:19] }}</td>
      </tr>
      {% endfor %}
      </tbody>
    </table></div>
  </div>
</div>
""")

@app.get("/admin/logs")
@admin_required
def admin_logs():
    conn = get_db()
    logs = conn.execute("SELECT * FROM logs ORDER BY timestamp DESC LIMIT 200").fetchall()
    conn.close()
    return render_template_string(LOGS_TPL, logs=logs, active="logs")

# ──────────────────────────────────────────────
#  ENTRY POINT
# ──────────────────────────────────────────────

# ──────────────────────────────────────────────
#  EXPORT TO CSV
# ──────────────────────────────────────────────

@app.route("/export")
@login_required
def export_bookings():
    import csv
    from io import StringIO
    from flask import make_response

    conn = get_db()
    bookings = conn.execute("SELECT * FROM bookings ORDER BY created_at DESC").fetchall()
    conn.close()

    si = StringIO()
    cw = csv.writer(si)
    
    # Headers
    cw.writerow(['Reference', 'First Name', 'Last Name', 'Email', 'Phone', 'Check-in', 'Check-out', 'Nights', 'Room Type', 'Total Price', 'Status', 'Discount', 'Payment', 'Booking Type', 'Date Created'])
    
    for b in bookings:
        cw.writerow([
            b['ref'], b['fname'], b['lname'], b['email'], b['phone'],
            b['checkin'], b['checkout'], b['nights'], b['room_type'],
            b['total'], b['status'], b['discount_type'], b['payment_method'],
            b['booking_type'], b['created_at']
        ])

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename=grandvista_bookings_{date.today()}.csv"
    output.headers["Content-type"] = "text/csv"
    return output


# Initialize DB for production
init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    print(f"\n  GrandVista Hotel -> http://localhost:{port}")
    print("  Default login: admin / admin123\n")
    app.run(host="0.0.0.0", port=port, debug=True)
