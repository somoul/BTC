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

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

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

app = Flask(__name__, static_folder=None)

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
    return send_from_directory(HERE, "index.html")


# ---------------------------------------------------------------- 🤖 AI chat
CHAT_MODEL = os.environ.get("BTC_BOT_MODEL", "claude-sonnet-5-5")
CHAT_SYSTEM = """អ្នកជាជំនួយការជួញដូរ crypto ក្នុង dashboard "ស្កេន"។ ឆ្លើយជាភាសាខ្មែរ ខ្លី ច្បាស់ ងាយយល់ (ប្រើពាក្យអង់គ្លេសសម្រាប់ពាក្យបច្ចេកទេស ដូចជា RSI, Stop-loss)។
ប្រើទិន្នន័យ dashboard ដែលផ្តល់ឱ្យ (តម្លៃ សញ្ញា កម្រិតតម្លៃ) ពេលឆ្លើយ ហើយនិយាយលេខឱ្យច្បាស់។
ការពិតដែលបានសាកល្បង: សញ្ញា 🎯 4 ម៉ោង (ពិន្ទុ ≥ +30 ទិញ, Stop 3×ATR, គោលដៅ 3R, កាន់ ≤ 7 ថ្ងៃ) ចំណេញបន្តិចក្រោយថ្លៃសេវាលើទិន្នន័យ 5 ឆ្នាំ (ត្រូវប្រហែល 47%, ធ្លាប់ធ្លាក់ -48%)។ សញ្ញា 5 នាទី 15 នាទី 1 ម៉ោង ខាតក្រោយថ្លៃសេវាក្នុងការសាកល្បង។ Fear & Greed, Order book, RSI, MACD គ្រាន់តែជាព័ត៌មានបរិបទ។
ច្បាប់: កុំសន្យាចំណេញ ឬនិយាយថាតម្លៃប្រាកដជាឡើង/ចុះ។ ណែនាំឱ្យកំណត់ Stop-loss និងកុំប្រើលុយលើសពីអាចបាត់បង់។ បើគេសួរថាគួរទិញ/លក់ ប្រាប់ពីអ្វីដែលសញ្ញាបង្ហាញ ហេតុផល និងហានិភ័យ ហើយរំលឹកថាអ្នកមិនមែនជាអ្នកប្រឹក្សាហិរញ្ញវត្ថុ។ បើមិនដឹង និយាយថាមិនដឹង។"""


@app.route("/api/chat/status")
def api_chat_status():
    return jsonify({"server": bool(os.environ.get("ANTHROPIC_API_KEY")), "model": CHAT_MODEL})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return jsonify({"error": "no_key"}), 400
    body = request.get_json(silent=True) or {}
    msgs = []
    for m in (body.get("messages") or [])[-20:]:
        if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str) and m["content"].strip():
            msgs.append({"role": m["role"], "content": m["content"][:4000]})
    if not msgs or msgs[-1]["role"] != "user":
        return jsonify({"error": "bad_request"}), 400
    context = str(body.get("context") or "")[:12000]
    try:
        import anthropic

        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=CHAT_MODEL, max_tokens=1200,
            system=CHAT_SYSTEM + "\n\nទិន្នន័យ dashboard ឥឡូវ:\n" + context,
            messages=msgs,
        )
        return jsonify({"reply": "".join(b.text for b in resp.content if b.type == "text")})
    except Exception as e:  # show a short reason in the chat
        return jsonify({"error": str(e)[:300]}), 502


APP_FILES = {"manifest.json", "sw.js", "icon-180.png", "icon-192.png", "icon-512.png", "icon-maskable-512.png"}


# ---------------------------------------------------------------- 📰 news + economic calendar (fetched here: no CORS)
NEWS_FEEDS = [
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
    ("Decrypt", "https://decrypt.co/feed"),
    ("The Block", "https://www.theblock.co/rss.xml"),
    ("Bitcoin Magazine", "https://bitcoinmagazine.com/.rss/full/"),
]
CAL_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
_cache = {}
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"}


def cached(key, ttl, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    try:
        val = fn()
    except Exception:
        if hit:
            return hit[1]
        raise
    _cache[key] = (time.time(), val)
    return val


def _feed(name, url):
    import requests
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime

    r = requests.get(url, headers=UA, timeout=12)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    out = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        when = it.findtext("pubDate") or ""
        try:
            ts = int(parsedate_to_datetime(when).timestamp())
        except Exception:
            continue
        desc = re.sub(r"<[^>]+>", " ", it.findtext("description") or "")
        desc = re.sub(r"\s+", " ", desc).strip()[:240]
        if title and link:
            out.append({"t": ts, "title": title, "link": link, "src": name, "desc": desc})
    return out


def load_news():
    from concurrent.futures import ThreadPoolExecutor

    items, ok = [], []
    with ThreadPoolExecutor(len(NEWS_FEEDS)) as ex:
        futs = {ex.submit(_feed, n, u): n for n, u in NEWS_FEEDS}
        for f, n in futs.items():
            try:
                items += f.result()
                ok.append(n)
            except Exception:
                pass
    if not items:
        raise RuntimeError("no feed reachable")
    seen, uniq = set(), []
    for x in sorted(items, key=lambda x: -x["t"]):
        k = re.sub(r"\W+", "", x["title"].lower())[:60]
        if k not in seen:
            seen.add(k)
            uniq.append(x)
    return {"items": uniq[:80], "sources": ok, "at": int(time.time())}


# 🇰🇭 headlines in Khmer: free Google translate endpoint, done in the background and cached per title
_km = {}
_km_busy = threading.Lock()


_tr_down = {"gtx": 0, "mm": 0}          # time until which a translator is resting (rate limit / daily quota)


def _to_km(text):
    import requests

    now = time.time()
    if now > _tr_down["gtx"]:
        try:
            r = requests.get("https://translate.googleapis.com/translate_a/single",
                             params={"client": "gtx", "sl": "en", "tl": "km", "dt": "t", "q": text}, headers=UA, timeout=10)
            r.raise_for_status()
            return "".join(seg[0] for seg in r.json()[0] if seg and seg[0]).strip()
        except Exception:
            _tr_down["gtx"] = now + 1800
    if now > _tr_down["mm"]:
        r = requests.get("https://api.mymemory.translated.net/get", params={"q": text, "langpair": "en|km"}, headers=UA, timeout=10).json()
        if r.get("quotaFinished") or r.get("responseStatus") not in (200, "200"):
            _tr_down["mm"] = now + 3 * 3600
            return None
        out = (r.get("responseData") or {}).get("translatedText") or ""
        return out if out and out.upper() != text.upper() else None
    return None


def _translate_missing(titles):
    if not _km_busy.acquire(blocking=False):
        return
    try:
        from concurrent.futures import ThreadPoolExecutor

        todo = [t for t in titles if t not in _km][:25]          # newest first; free translators are rate-limited
        with ThreadPoolExecutor(2) as ex:
            for t, km in zip(todo, ex.map(lambda t: _safe(_to_km, t), todo)):
                if km:
                    _km[t] = km
        if len(_km) > 2000:
            for k in list(_km)[:1000]:
                _km.pop(k, None)
    finally:
        _km_busy.release()


def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception:
        return None


@app.route("/api/news")
def api_news():
    try:
        d = cached("news", 180, load_news)
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    titles = [x["title"] for x in d["items"]]
    if any(t not in _km for t in titles):
        threading.Thread(target=_translate_missing, args=(titles,), daemon=True).start()
    items = [dict(x, km=_km.get(x["title"], "")) for x in d["items"]]
    return jsonify(dict(d, items=items))


# ---------------------------------------------------------------- ⚡ funding rate / open interest / long-short
def _fut_binance(sym):
    import requests

    p = requests.get("https://fapi.binance.com/fapi/v1/premiumIndex", params={"symbol": sym}, headers=UA, timeout=8).json()
    oi = requests.get("https://fapi.binance.com/fapi/v1/openInterest", params={"symbol": sym}, headers=UA, timeout=8).json()
    ls = requests.get("https://fapi.binance.com/futures/data/globalLongShortAccountRatio",
                      params={"symbol": sym, "period": "1h", "limit": 1}, headers=UA, timeout=8).json()
    mark = float(p["markPrice"])
    return {"src": "Binance", "funding": float(p["lastFundingRate"]), "next": int(p["nextFundingTime"]) // 1000,
            "oi": float(oi["openInterest"]) * mark, "long": float(ls[0]["longAccount"]) if ls else None}


def _fut_bybit(sym):
    import requests

    t = requests.get("https://api.bybit.com/v5/market/tickers", params={"category": "linear", "symbol": sym}, headers=UA, timeout=8).json()
    x = t["result"]["list"][0]
    out = {"src": "Bybit", "funding": float(x["fundingRate"]), "next": int(x["nextFundingTime"]) // 1000,
           "oi": float(x["openInterestValue"]), "long": None}
    try:
        r = requests.get("https://api.bybit.com/v5/market/account-ratio",
                         params={"category": "linear", "symbol": sym, "period": "1h", "limit": 1}, headers=UA, timeout=8).json()
        out["long"] = float(r["result"]["list"][0]["buyRatio"])
    except Exception:
        pass
    return out


def _fut_okx(sym):
    import requests

    inst = sym.replace("USDT", "-USDT-SWAP")
    f = requests.get("https://www.okx.com/api/v5/public/funding-rate", params={"instId": inst}, headers=UA, timeout=8).json()["data"][0]
    return {"src": "OKX", "funding": float(f["fundingRate"]), "next": int(f["fundingTime"]) // 1000, "oi": None, "long": None}


def _fut_gate(sym):
    import requests

    c = sym[:-4] + "_USDT" if sym.endswith("USDT") else sym
    k = requests.get(f"https://api.gateio.ws/api/v4/futures/usdt/contracts/{c}", headers=UA, timeout=8).json()
    st = requests.get("https://api.gateio.ws/api/v4/futures/usdt/contract_stats",
                      params={"contract": c, "interval": "1h", "limit": 25}, headers=UA, timeout=8).json()
    st = sorted(st, key=lambda x: x["time"]) if isinstance(st, list) else []
    last = st[-1] if st else {}
    r = last.get("lsr_account"), last.get("top_lsr_account")
    return {"src": "Gate.io", "funding": float(k["funding_rate"]), "next": int(k["funding_next_apply"]),
            "every": int(k.get("funding_interval") or 28800) // 3600,
            "oi": last.get("open_interest_usd"),
            "oi24": (last["open_interest_usd"] / st[0]["open_interest_usd"] - 1) * 100 if len(st) > 20 and st[0].get("open_interest_usd") else None,
            "long": r[0] / (1 + r[0]) if r[0] else None,
            "top_long": r[1] / (1 + r[1]) if r[1] else None,
            "liq_long": sum(x.get("long_liq_usd") or 0 for x in st[-24:]),
            "liq_short": sum(x.get("short_liq_usd") or 0 for x in st[-24:])}


_fut_down = {}                        # source → time until which we skip it (blocked in some countries)


def load_futures(sym):
    for fn in (_fut_binance, _fut_gate, _fut_bybit, _fut_okx):
        if time.time() < _fut_down.get(fn.__name__, 0):
            continue
        try:
            return fn(sym)
        except Exception as e:
            if "Timeout" in type(e).__name__ or "Connection" in type(e).__name__:
                _fut_down[fn.__name__] = time.time() + 1800
            continue
    raise RuntimeError("no futures source reachable")


@app.route("/api/futures")
def api_futures():
    sym = re.sub(r"[^A-Z0-9]", "", request.args.get("symbol", DEFAULT_SYMBOL).upper())[:20]
    try:
        return jsonify(cached("fut:" + sym, 60, lambda: load_futures(sym)))
    except Exception as e:
        return jsonify({"error": str(e)}), 502


def load_calendar():
    import requests
    from datetime import datetime as dt

    r = requests.get(CAL_URL, headers=UA, timeout=12)
    r.raise_for_status()
    out = []
    for x in r.json():
        if x.get("country") != "USD" or x.get("impact") not in ("High", "Medium"):
            continue
        try:
            ts = int(dt.fromisoformat(x["date"]).timestamp())
        except Exception:
            continue
        out.append({"t": ts, "title": x.get("title", ""), "impact": x.get("impact"),
                    "forecast": x.get("forecast", ""), "previous": x.get("previous", "")})
    return {"items": out, "at": int(time.time())}


CAL_FILE = os.path.join(HERE, "calendar_cache.json")     # kept on disk: the source allows only a few requests per hour
_cal_try = [0]


@app.route("/api/calendar")
def api_calendar():
    import json

    old = None
    try:
        with open(CAL_FILE, encoding="utf-8") as f:
            old = json.load(f)
    except Exception:
        pass
    fresh = old and time.time() - old.get("at", 0) < 3600
    if not fresh and time.time() - _cal_try[0] > 900:          # at most one try every 15 min
        _cal_try[0] = time.time()
        try:
            old = load_calendar()
            with open(CAL_FILE + ".tmp", "w", encoding="utf-8") as f:
                json.dump(old, f)
            os.replace(CAL_FILE + ".tmp", CAL_FILE)
        except Exception:
            pass
    if old:
        return jsonify(old)
    return jsonify({"error": "calendar not reachable yet"}), 502


@app.route("/<name>")
def app_file(name):
    """files that make the dashboard installable as a phone app"""
    if name not in APP_FILES:
        return ("Not found", 404)
    resp = send_from_directory(HERE, name)
    if name == "sw.js":
        resp.headers["Cache-Control"] = "no-cache"
    return resp


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
    files.append(os.path.join(HERE, "index.html"))
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
