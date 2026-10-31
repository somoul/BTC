"""
telegram_alert.py — ផ្ញើសារ Telegram ពេលមានសញ្ញា Futures ដែលអាចចូលលេងបាន (🟢 LONG / 🔴 SHORT · 4h)

ប្រើច្បាប់ដូចគ្នានឹង dashboard (index.html):
  • ពិន្ទុ 4h ≥ +30 → Long · ≤ -30 → Short
  • សញ្ញាត្រូវតែ "ខ្លាំង": តម្លៃឆ្ងាយពី EMA20 > 2 ATR ហើយភាពរំញ័រមិននៅ 80–95%
  • ទិសនោះត្រូវចំណេញក្នុងការសាកល្បង 5 ឆ្នាំ (ទាំងទិន្នន័យទាំងអស់ និងទិន្នន័យថ្មី 1/3) ហើយមាន ≥ 15 ដង
  • Stop = 3 × ATR(4h) · គោលដៅ = 3R · កាន់យូរបំផុត 42 candle (7 ថ្ងៃ) · ថ្លៃសេវា Futures 0.05%/ដង

ដំណើរការ (GitHub Actions ធ្វើដោយស្វ័យប្រវត្តិ រៀងរាល់ពេល candle 4h បិទ):
    TELEGRAM_TOKEN=... TELEGRAM_CHAT_ID=... python telegram_alert.py           # ផ្ញើតែពេលមាន setup ថ្មី
    TELEGRAM_TOKEN=... TELEGRAM_CHAT_ID=... python telegram_alert.py --test    # ផ្ញើស្ថានភាពគ្រប់កាក់ឥឡូវ (សាក)
    TELEGRAM_TOKEN=... python telegram_alert.py --chatid                       # រក chat id របស់អ្នក
"""

import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

API = "https://data-api.binance.vision/api/v3/klines"
COINS = (os.environ.get("COINS") or "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,DOGEUSDT,PAXGUSDT").split(",")
LABEL = {"PAXGUSDT": "មាស (PAXG)"}
TF, STEP = "4h", 14400
STOP_ATR, TP_R, HOLD, FEE, YEARS = 3, 3, 42, 0.0005, 5
DASHBOARD = os.environ.get("DASHBOARD_URL", "")


# ------------------------------------------------------------------ data
def get_json(url, tries=3):
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "btc-scan/1.0"}), timeout=20) as r:
                return json.loads(r.read())
        except Exception:
            if k == tries - 1:
                raise
            time.sleep(2 + 3 * k)


def _rows(raw):
    return [{"time": k[0] // 1000, "open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
             "close": float(k[4]), "volume": float(k[5])} for k in raw]


def klines(sym, limit=500):
    return _rows(get_json(f"{API}?symbol={sym}&interval={TF}&limit={limit}"))


def klines_range(sym, start_ms):
    out, frm = [], start_ms
    for _ in range(40):
        raw = get_json(f"{API}?symbol={sym}&interval={TF}&startTime={frm}&limit=1000")
        if not raw:
            break
        out += _rows(raw)
        if len(raw) < 1000:
            break
        frm = raw[-1][0] + 1
    return out


# ------------------------------------------------------------------ indicators (same maths as index.html)
def ema(a, n):
    k, o = 2 / (n + 1), []
    for i, x in enumerate(a):
        o.append(k * x + (1 - k) * o[-1] if i else x)
    return o


def wilder(a, n):
    k, o = 1 / n, []
    for i, x in enumerate(a):
        o.append(k * x + (1 - k) * o[-1] if i else x)
    return o


def scores_of(c):
    cl = [x["close"] for x in c]
    n = len(cl)
    e20, e50, e200, e26 = ema(cl, 20), ema(cl, 50), ema(cl, 200), ema(cl, 26)
    d = [cl[i] - cl[i - 1] if i else 0 for i in range(n)]
    g = wilder([max(x, 0) if i else 0 for i, x in enumerate(d)], 14)
    l = wilder([max(-x, 0) if i else 0 for i, x in enumerate(d)], 14)
    macd = [a - b for a, b in zip(ema(cl, 12), e26)]
    sig = ema(macd, 9)
    tr = [max(x["high"] - x["low"], abs(x["high"] - cl[i - 1]), abs(x["low"] - cl[i - 1])) if i else x["high"] - x["low"]
          for i, x in enumerate(c)]
    atr = wilder(tr, 14)
    s, a = [None] * n, [None] * n
    for i in range(200, n):
        w = cl[i - 19:i + 1]
        m = sum(w) / 20
        sd = math.sqrt(sum((y - m) ** 2 for y in w) / 19)
        rsi = 100 - 100 / (1 + g[i] / l[i]) if l[i] else 100
        r = {"close": cl[i], "ema20": e20[i], "ema50": e50[i], "ema200": e200[i], "rsi": rsi,
             "hist": macd[i] - sig[i], "bb_pos": (cl[i] - (m - 2 * sd)) / (4 * sd) if sd else 0.5,
             "mom10": (cl[i] / cl[i - 10] - 1) * 100, "atr": atr[i]}
        p = 0

        def vote(up, dn, wt):
            return wt if up else -wt if dn else 0

        p += vote(r["close"] > r["ema200"], r["close"] < r["ema200"], 20)
        p += vote(r["ema20"] > r["ema50"], r["ema20"] < r["ema50"], 20)
        p += vote(r["hist"] > 0, r["hist"] < 0, 15)
        p += vote(r["mom10"] > 0, r["mom10"] < 0, 15)
        if rsi < 30:
            p += 15
        elif rsi > 70:
            p -= 15
        else:
            p += vote(rsi > 50, rsi < 50, 10)
        if r["bb_pos"] < 0.05:
            p += 10
        elif r["bb_pos"] > 0.95:
            p -= 10
        s[i] = max(-100, min(100, round(p)))
        a[i] = r
    return s, a


def strength(a, i, side):
    r = a[i]
    ext = side * (r["close"] - r["ema20"]) / r["atr"]
    cur = r["atr"] / r["close"]
    vals = [a[j]["atr"] / a[j]["close"] for j in range(max(200, i - 500), i) if a[j]]
    vol = sum(v < cur for v in vals) / len(vals) if vals else 0.5
    hot = 0.8 < vol <= 0.95
    return {"ext": ext, "vol": vol, "hot": hot, "strong": ext > 2 and not hot, "need": r["ema20"] + side * 2 * r["atr"]}


def side_of(score):
    return 1 if score is not None and score >= 30 else -1 if score is not None and score <= -30 else 0


# ------------------------------------------------------------------ 5-year test of the "strong signal" rule
def backtest(c):
    s, a = scores_of(c)
    trades, busy = [], -1
    for i in range(210, len(c) - 2):
        if i <= busy or s[i] is None:
            continue
        side = side_of(s[i])
        if not side or not strength(a, i, side)["strong"]:
            continue
        e, risk = c[i + 1]["open"], STOP_ATR * a[i]["atr"]
        if not risk > 0:
            continue
        stop, tp = e - side * risk, e + side * TP_R * risk
        last = min(i + HOLD, len(c) - 1)
        R, k = None, i + 1
        while k <= last:
            x = c[k]
            if (x["low"] <= stop) if side > 0 else (x["high"] >= stop):
                R = -1
                break
            if (x["high"] >= tp) if side > 0 else (x["low"] <= tp):
                R = TP_R
                break
            k += 1
        if R is None:
            if last < i + HOLD:
                break
            k = last
            R = side * (c[k]["close"] - e) / risk
        trades.append({"t": c[i + 1]["time"], "side": side, "r": R, "net": R * risk / e * 100 - 2 * FEE * 100})
        busy = k
    cut = c[len(c) * 2 // 3]["time"]

    def st(xs):
        n = len(xs)
        run = worst = 0
        for t in xs:
            run = 0 if t["r"] > 0 else run + 1
            worst = max(worst, run)
        return {"n": n, "win": sum(t["r"] > 0 for t in xs) / n if n else 0,
                "avg": sum(t["net"] for t in xs) / n if n else 0, "streak": worst}

    out = {}
    for side in (1, -1):
        xs = [t for t in trades if t["side"] == side]
        out[side] = {"all": st(xs), "oos": st([t for t in xs if t["t"] >= cut])}
    return out


def tested_ok(stats):
    return stats["all"]["n"] >= 15 and stats["all"]["avg"] > 0 and stats["oos"]["avg"] > 0


# ------------------------------------------------------------------ live check
def check(sym, tests):
    c = klines(sym, 500)
    s, a = scores_of(c)
    last = len(c) - 2                              # last CLOSED 4h candle

    def setup_at(i):
        side = side_of(s[i])
        if not side:
            return None, None
        st = strength(a, i, side)
        return (side if st["strong"] and tested_ok(tests[side]) else None), st

    now_side, st = setup_at(last)
    prev_side, _ = setup_at(last - 1)
    side = side_of(s[last])
    price, atr = c[-1]["close"], a[last]["atr"]
    fresh_close = time.time() - (c[last]["time"] + STEP) < 3.5 * 3600      # one alert per candle, even if the run is late
    return {"sym": sym, "score": s[last], "side": side, "go": now_side, "new": bool(now_side) and prev_side != now_side and fresh_close,
            "st": st, "price": price, "atr": atr, "close_at": c[last]["time"] + STEP, "tests": tests}


def fmt(x):
    if x >= 1000:
        return f"{x:,.1f}"
    if x >= 10:
        return f"{x:,.2f}"
    if x >= 1:
        return f"{x:.4f}"
    return f"{x:.5f}"


def label(sym):
    return LABEL.get(sym, sym.replace("USDT", ""))


def setup_message(r):
    side, p, risk = r["go"], r["price"], STOP_ATR * r["atr"]
    stop, tp = p - side * risk, p + side * TP_R * risk
    t = r["tests"][side]["all"]
    head = "🟢 <b>LONG ⬆</b>" if side > 0 else "🔴 <b>SHORT ⬇</b>"
    when = time.strftime("%d/%m %H:%M", time.gmtime(r["close_at"] + 7 * 3600))
    lines = [
        f"{head}  <b>{label(r['sym'])}</b> · 4h",
        "",
        f"ចូល ~<code>{fmt(p)}</code>",
        f"Stop-loss <code>{fmt(stop)}</code>",
        f"គោលដៅ (TP) <code>{fmt(tp)}</code>",
        "",
        f"💪 កម្លាំង {r['st']['ext']:.1f} ATR · ពិន្ទុ {r['score']:+d}",
        f"📊 សាកល្បង 5 ឆ្នាំ: ត្រូវ {t['win'] * 100:.0f}% · {t['avg']:+.2f}%/ដង · {t['n']} ដង",
        f"📉 ធ្លាប់ខាតជាប់គ្នា {t['streak']} ដង — ហ៊ានខាតត្រឹម 1%",
        f"⏳ កាន់យូរបំផុត 7 ថ្ងៃ · candle បិទ {when} (ម៉ោងកម្ពុជា)",
    ]
    if DASHBOARD:
        lines += ["", f"🔗 {DASHBOARD}?s={r['sym']}"]
    return "\n".join(lines)


def status_line(r):
    if r["go"]:
        return f"{'🟢 LONG' if r['go'] > 0 else '🔴 SHORT'}  {label(r['sym'])} ({r['score']:+d})"
    if r["side"]:
        why = "កម្លាំងខ្សោយ" if not r["st"]["strong"] else "សាកល្បងមិនល្អ"
        return f"🟠 {'Long' if r['side'] > 0 else 'Short'} {label(r['sym'])} — {why} ({r['score']:+d})"
    return f"⏸ {label(r['sym'])} — រង់ចាំ ({r['score']:+d})"


# ------------------------------------------------------------------ telegram
def tg(method, **params):
    token = os.environ["TELEGRAM_TOKEN"].strip()
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/{method}", data=data, timeout=20) as r:
        return json.loads(r.read())


def send(text):
    for chat in os.environ["TELEGRAM_CHAT_ID"].split(","):
        tg("sendMessage", chat_id=chat.strip(), text=text, parse_mode="HTML", disable_web_page_preview="true")


def main():
    if "--chatid" in sys.argv:
        ups = tg("getUpdates").get("result", [])
        ids = {(u.get("message") or u.get("channel_post") or {}).get("chat", {}).get("id") for u in ups} - {None}
        print("chat id:", ", ".join(map(str, ids)) if ids else "មិនទាន់ឃើញ — សូមផ្ញើសារណាមួយទៅ bot របស់អ្នកសិន ហើយដំណើរការម្តងទៀត")
        return
    test_mode = "--test" in sys.argv
    results, errors = [], []
    for sym in COINS:
        sym = sym.strip().upper()
        try:
            hist = klines_range(sym, int((time.time() - YEARS * 365 * 86400 - 210 * STEP) * 1000))
            if len(hist) < 600:
                raise RuntimeError("ទិន្នន័យតិចពេក")
            results.append(check(sym, backtest(hist)))
        except Exception as e:
            errors.append(f"{sym}: {e}")
    for r in results:
        print(status_line(r))
    for e in errors:
        print("ERR", e)
    new = [r for r in results if r["new"]]
    for r in new:
        send(setup_message(r))
    if test_mode:
        body = "\n".join(status_line(r) for r in results) or "—"
        send("🧪 <b>សាកល្បង Telegram</b> — ស្ថានភាព 4h ឥឡូវ\n\n" + body +
             ("\n\n⚠️ " + "; ".join(errors) if errors else "") +
             "\n\nអ្នកនឹងទទួលសារ ពេលមាន 🟢 LONG ឬ 🔴 SHORT ថ្មី (ពិនិត្យរៀងរាល់ 4 ម៉ោង)")
    print(f"sent {len(new)} setup message(s)" + (" + test" if test_mode else ""))
    if errors and not results:
        sys.exit(1)


if __name__ == "__main__":
    main()
