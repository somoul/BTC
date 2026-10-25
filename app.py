"""
app.py - Crypto & Gold Dashboard (web)

ដំណើរការ:
    pip install -r requirements.txt
    python app.py
បន្ទាប់មកបើក  http://localhost:8000  នៅក្នុង browser

Server ទាញទិន្នន័យពី Binance ដោយខ្លួនឯងរៀងរាល់ REFRESH_SECONDS វិនាទី
សម្រាប់កាក់ដែលអ្នកកំពុងមើល ហើយកត់សញ្ញាចូល signals_log_<កាក់>.csv។
"""

import csv
import os
import re
import threading
import time
from datetime import datetime

from flask import Flask, jsonify, request, send_from_directory

from analysis import analyze_all

DEFAULT_SYMBOL = os.environ.get("BTC_SYMBOL", "BTCUSDT").upper()
REFRESH_SECONDS = int(os.environ.get("REFRESH_SECONDS", "15"))
HERE = os.path.dirname(os.path.abspath(__file__))
LOG_EVERY_SECONDS = 300          # កត់តម្លៃរៀងរាល់ 5 នាទី (ដើម្បីវាស់ថាសញ្ញាត្រូវឬខុស)
CHECK_AFTER_MINUTES = 60         # ពិនិត្យលទ្ធផលសញ្ញា 1 ម៉ោងក្រោយ
ACTIVE_SECONDS = 180             # បន្តធ្វើបច្ចុប្បន្នភាពកាក់មួយ 3 នាទីក្រោយគេឈប់មើល

# កាក់ដែលបង្ហាញជាប៊ូតុង (អាចវាយបញ្ចូលកាក់ផ្សេងទៀតបាននៅលើទំព័រ)
PRESETS = [
    {"symbol": "BTCUSDT", "name": "Bitcoin", "label": "BTC", "icon": "₿", "color": "#f7931a"},
    {"symbol": "PAXGUSDT", "name": "មាស (PAX Gold · 1 អោន)", "label": "មាស", "icon": "Au", "color": "#e6c35c"},
    {"symbol": "ETHUSDT", "name": "Ethereum", "label": "ETH", "icon": "Ξ", "color": "#8c8cf7"},
    {"symbol": "BNBUSDT", "name": "BNB", "label": "BNB", "icon": "B", "color": "#f3ba2f"},
    {"symbol": "SOLUSDT", "name": "Solana", "label": "SOL", "icon": "S", "color": "#9b6bff"},
    {"symbol": "XRPUSDT", "name": "XRP", "label": "XRP", "icon": "X", "color": "#9aa4b2"},
    {"symbol": "DOGEUSDT", "name": "Dogecoin", "label": "DOGE", "icon": "Ð", "color": "#c2a633"},
]
SYMBOL_RE = re.compile(r"^[A-Z0-9]{2,15}(USDT|USDC|FDUSD|BTC|ETH)$")

LOG_HEADER = ["time", "price", "verdict", "confidence", "overall", "score", "5m", "15m", "1h", "4h", "1d"]

app = Flask(__name__, static_folder=os.path.join(HERE, "static"))

# ស្ថានភាពរបស់កាក់នីមួយៗ
coins = {}
lock = threading.Lock()


def entry(symbol):
    with lock:
        if symbol not in coins:
            coins[symbol] = {"data": None, "error": None, "last_try": 0, "last_log": 0,
                             "last_seen": time.time(), "busy": threading.Lock()}
        return coins[symbol]


def log_path(symbol):
    return os.path.join(HERE, f"signals_log_{symbol}.csv")


def current_price(data):
    frames = data["frames"]
    return (frames.get("5m") or frames.get("1h") or next(iter(frames.values())))["price"]


def log_signal(symbol, data):
    path = log_path(symbol)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            header = f.readline().strip().split(",")
        if header != LOG_HEADER:
            os.replace(path, path.replace(".csv", f"_old_{datetime.now():%Y%m%d_%H%M%S}.csv"))
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(LOG_HEADER)
        m = data["mtf"]
        w.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            f"{current_price(data):.8g}",
            data["verdict"]["action"], data["verdict"]["confidence"],
            data["overall"]["signal"], data["overall"]["score"],
            *[m.get(tf, {}).get("signal", "") for tf in LOG_HEADER[6:]],
        ])


def refresh(symbol):
    st = entry(symbol)
    if not st["busy"].acquire(blocking=False):   # កំពុងធ្វើរួចហើយ
        return
    try:
        prev = st["data"]
        data = analyze_all(symbol, previous=prev)
        partial = data.get("partial_errors") or {}
        st.update(data=data, last_try=time.time(),
                  error=("ខ្លះបរាជ័យ: " + ", ".join(partial)) if partial else None)
        now = time.time()
        if (prev is None or prev.get("verdict", {}).get("action") != data["verdict"]["action"]
                or now - st["last_log"] >= LOG_EVERY_SECONDS):
            log_signal(symbol, data)
            st["last_log"] = now
        print(f"[{datetime.now():%H:%M:%S}] ✅ {symbol:9} {data['verdict']['action']:4} "
              f"5m:{(data.get('scalp') or {}).get('action', '-'):4}  {current_price(data):,.6g}")
    except Exception as e:
        msg = str(e)
        if "400" in msg or "Invalid symbol" in msg:
            msg = f"រកមិនឃើញកាក់ {symbol} នៅលើ Binance"
        elif "មិនអាចភ្ជាប់" in msg or "Connection" in msg or "timed out" in msg:
            msg = "មិនអាចភ្ជាប់ទៅ Binance — សូមពិនិត្យ internet"
        st.update(error=msg, last_try=time.time())
        print(f"[{datetime.now():%H:%M:%S}] ❌ {symbol}: {msg}")
    finally:
        st["busy"].release()


def worker():
    entry(DEFAULT_SYMBOL)
    while True:
        now = time.time()
        with lock:
            active = [s for s, st in coins.items()
                      if (s == DEFAULT_SYMBOL or now - st["last_seen"] < ACTIVE_SECONDS)
                      and not (st["data"] is None and (st["error"] or "").startswith("រកមិនឃើញ"))]
            # បំភ្លេចកាក់ដែលរកមិនឃើញ / លែងមើលយូរ
            for s in [s for s, st in coins.items()
                      if s != DEFAULT_SYMBOL and now - st["last_seen"] > 3600]:
                coins.pop(s, None)
        for s in active:
            threading.Thread(target=refresh, args=(s,), daemon=True).start()
        time.sleep(REFRESH_SECONDS)


def get_symbol():
    s = (request.args.get("symbol") or DEFAULT_SYMBOL).upper().strip()
    return s if SYMBOL_RE.match(s) else None


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/symbols")
def api_symbols():
    return jsonify({"presets": PRESETS, "default": DEFAULT_SYMBOL})


@app.route("/api/analysis")
def api_analysis():
    symbol = get_symbol()
    if not symbol:
        return jsonify({"data": None, "error": "ឈ្មោះកាក់មិនត្រឹមត្រូវ (ឧ. ETHUSDT)", "symbol": None,
                        "refresh_seconds": REFRESH_SECONDS})
    st = entry(symbol)
    st["last_seen"] = time.time()
    if st["data"] is None and time.time() - st["last_try"] > 5:
        refresh(symbol)          # កាក់ថ្មី → ទាញភ្លាម
    return jsonify({
        "data": st["data"],
        "error": st["error"],
        "refresh_seconds": REFRESH_SECONDS,
        "symbol": symbol,
    })


def read_log(symbol):
    path = log_path(symbol)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        try:
            out.append({"t": datetime.strptime(r["time"], "%Y-%m-%d %H:%M:%S"),
                        "price": float(r["price"]), "signal": r["verdict"], "score": int(r["score"])})
        except (KeyError, ValueError):
            continue
    return out


def signal_history(symbol, limit=30):
    """រាល់ពេលសេចក្តីសម្រេច (BUY/SELL/WAIT) ប្តូរ = ការទាយមួយ។ ពិនិត្យតម្លៃ 1 ម៉ោងក្រោយ ថាទាយត្រូវ ឬខុស។"""
    rows = read_log(symbol)
    calls = [r for i, r in enumerate(rows) if i == 0 or r["signal"] != rows[i - 1]["signal"]]
    horizon = CHECK_AFTER_MINUTES * 60
    items, wins, total = [], 0, 0
    for c in calls:
        later = next((r for r in rows if (r["t"] - c["t"]).total_seconds() >= horizon), None)
        item = {"time": c["t"].strftime("%m-%d %H:%M"), "signal": c["signal"],
                "score": c["score"], "price": c["price"],
                "price_after": None, "change_pct": None, "result": "-"}
        if later:
            chg = (later["price"] - c["price"]) / c["price"] * 100
            item.update(price_after=later["price"], change_pct=round(chg, 2))
            if c["signal"] in ("BUY", "SELL"):
                ok = chg > 0 if c["signal"] == "BUY" else chg < 0
                item["result"] = "win" if ok else "loss"
                wins += ok
                total += 1
        elif c["signal"] in ("BUY", "SELL"):
            item["result"] = "pending"
        items.append(item)
    return {
        "items": items[::-1][:limit],
        "wins": wins, "total": total,
        "accuracy": round(wins / total * 100, 1) if total else None,
        "horizon_minutes": CHECK_AFTER_MINUTES,
        "since": rows[0]["t"].strftime("%Y-%m-%d %H:%M") if rows else None,
    }


@app.route("/api/history")
def api_history():
    symbol = get_symbol()
    if not symbol:
        return jsonify({"items": [], "wins": 0, "total": 0, "accuracy": None,
                        "horizon_minutes": CHECK_AFTER_MINUTES, "since": None})
    return jsonify(signal_history(symbol))


def page_version():
    """ពេលកូដ ឬទំព័រត្រូវបានកែ → ទំព័រក្នុង browser reload ដោយខ្លួនឯង"""
    files = [os.path.join(HERE, f) for f in ("app.py", "analysis.py", "btc_monitor.py")]
    files.append(os.path.join(HERE, "static", "index.html"))
    return str(int(max(os.path.getmtime(f) for f in files if os.path.exists(f))))


@app.route("/api/version")
def api_version():
    return jsonify({"version": page_version()})


if __name__ == "__main__":
    # use_reloader: នៅពេលឯកសារ .py ត្រូវបានកែ server restart ដោយខ្លួនឯង (មិនចាំបាច់បិទ/បើកវិញ)
    # worker រត់តែក្នុង process ពិត (មិនមែន process ដែលមើលការផ្លាស់ប្តូរ)
    port = int(os.environ.get("PORT", "8000"))
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        threading.Thread(target=worker, daemon=True).start()
    else:
        print(f"🚀 បើក http://localhost:{port}  (Ctrl+C ដើម្បីបញ្ឈប់)")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True, use_reloader=True)
