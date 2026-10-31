"""
telegram_alert.py — ផ្ញើសារ Telegram ពេលមានសញ្ញា Futures ដែលអាចចូលលេងបាន (🟢 LONG / 🔴 SHORT · 4h)

ប្រើច្បាប់ដូចគ្នានឹង dashboard (index.html):
  • ពិន្ទុ 4h ≥ +30 → Long · ≤ -30 → Short
  • សញ្ញាត្រូវតែ "ខ្លាំង": តម្លៃឆ្ងាយពី EMA20 > 2 ATR ហើយភាពរំញ័រមិននៅ 80–95%
  • ទិសនោះត្រូវចំណេញក្នុងការសាកល្បង 5 ឆ្នាំ (ទាំងទិន្នន័យទាំងអស់ និងទិន្នន័យថ្មី 1/3) ហើយមាន ≥ 15 ដង
  • Stop = 3 × ATR(4h) · គោលដៅ = 3R · កាន់យូរបំផុត 42 candle (7 ថ្ងៃ) · ថ្លៃសេវា Futures 0.05%/ដង

ដំណើរការ (GitHub Actions ធ្វើដោយស្វ័យប្រវត្តិ រៀងរាល់ 15 នាទី · សារម្តងក្នុង 1 setup):
    TELEGRAM_TOKEN=... TELEGRAM_CHAT_ID=... python telegram_alert.py           # ផ្ញើពេលកាក់ណាមួយអាចចូលលេងបាន
    TELEGRAM_TOKEN=... TELEGRAM_CHAT_ID=... python telegram_alert.py --test    # ផ្ញើស្ថានភាពគ្រប់កាក់ឥឡូវ (សាក)
    TELEGRAM_TOKEN=... python telegram_alert.py --chatid                       # រក chat id របស់អ្នក
"""

import json
import math
import os
import sys
import time
import urllib.parse
import urllib.error
import urllib.request

API = "https://data-api.binance.vision/api/v3/klines"
COINS = (os.environ.get("COINS") or "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,DOGEUSDT,PAXGUSDT").split(",")
LABEL = {"PAXGUSDT": "មាស (PAXG)"}
TF, STEP = "4h", 14400
STOP_ATR, TP_R, HOLD, FEE, YEARS = 3, 3, 42, 0.0005, 5
DASHBOARD = os.environ.get("DASHBOARD_URL", "")
CAPITAL = float(os.environ.get("CAPITAL") or 500)        # Futures account size in USDT (GitHub Variable CAPITAL)
RISK_PCT = float(os.environ.get("RISK_PCT") or 1)        # % of the account you accept to lose per trade
LEVERAGE = int(float(os.environ.get("LEVERAGE") or 3))
HOLD_SEC = HOLD * STEP


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
    age = 0
    while side and age < 200 and side_of(s[last - age - 1]) == side:
        age += 1
    return {"sym": sym, "score": s[last], "side": side, "go": now_side, "age_h": (age + 1) * 4,
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


def plan(r):
    side, p, risk = r["go"], r["price"], STOP_ATR * r["atr"]
    stop, tp = p - side * risk, p + side * TP_R * risk
    sd = risk / p
    notional = min(CAPITAL * RISK_PCT / 100 / (sd + 2 * FEE), CAPITAL * LEVERAGE)
    mmr = 0.004 if r["sym"].startswith(("BTC", "ETH")) else 0.005
    liq = p * (1 - 1 / LEVERAGE) / (1 - mmr) if side > 0 else p * (1 + 1 / LEVERAGE) / (1 + mmr)
    loss = notional * sd + notional * FEE + notional / p * stop * FEE
    gain = notional * sd * TP_R - notional * FEE - notional / p * tp * FEE
    return {"side": side, "entry": p, "stop": stop, "tp": tp, "sd": sd, "notional": notional,
            "margin": notional / LEVERAGE, "liq": liq if liq > 0 else 0, "loss": loss, "gain": gain}


def setup_message(r):
    P, side = plan(r), r["go"]
    t = r["tests"][side]["all"]
    head = "🟢 <b>LONG ⬆</b>" if side > 0 else "🔴 <b>SHORT ⬇</b>"
    until = time.strftime("%d/%m %H:%M", time.gmtime(time.time() + HOLD_SEC + 7 * 3600))
    liq_ok = P["liq"] == 0 or (P["liq"] < P["stop"] if side > 0 else P["liq"] > P["stop"])
    lines = [
        f"{head}  <b>{label(r['sym'])}</b> · 4h",
        "",
        f"▶️ ចូល (Market) ~<code>{fmt(P['entry'])}</code>",
        f"🛑 Stop-loss <code>{fmt(P['stop'])}</code>  ({-side * P['sd'] * 100:+.2f}%)",
        f"🎯 Take-profit <code>{fmt(P['tp'])}</code>  ({side * P['sd'] * TP_R * 100:+.2f}%)",
        "",
        f"💼 ទុន ${CAPITAL:,.0f} · ហ៊ានខាត {RISK_PCT:g}% · {LEVERAGE}x Isolated",
        f"   ទំហំ <code>{P['notional']:,.2f}</code> USDT · margin ${P['margin']:,.2f}",
        f"   ដល់ SL ខាត <b>-${P['loss']:,.2f}</b> · ដល់ TP ចំណេញ <b>+${P['gain']:,.2f}</b>",
        f"   Liquidation ~{fmt(P['liq'])} " + ("✅ ឆ្ងាយជាង SL" if liq_ok else "⚠️ ជិតជាង SL — បន្ថយ leverage"),
        "",
        f"💪 កម្លាំង {r['st']['ext']:.1f} ATR · សញ្ញាចាប់ផ្តើម {r['age_h']} ម៉ោងមុន",
        f"📊 សាកល្បង 5 ឆ្នាំ: ត្រូវ {t['win'] * 100:.0f}% · {t['avg']:+.2f}%/ដង · ធ្លាប់ខាតជាប់គ្នា {t['streak']} ដង",
        f"⏳ បើមិនដល់ SL/TP — បិទនៅ {until} (7 ថ្ងៃ)",
        "🔔 ខ្ញុំនឹងប្រាប់អ្នក ពេលដល់ SL, TP ឬ 7 ថ្ងៃ",
    ]
    if DASHBOARD:
        lines += ["", f"🔗 {DASHBOARD}?s={r['sym']}"]
    return "\n".join(lines)


def follow_trade(sym, tr):
    """Did price reach Stop-loss or Take-profit since the alert? (15m candles; if both in one candle → count SL)."""
    raw = get_json(f"{API}?symbol={sym}&interval=15m&startTime={int(tr['at'] * 1000)}&limit=1000")
    side, hit = tr["side"], None
    for k in _rows(raw):
        if (k["low"] <= tr["stop"]) if side > 0 else (k["high"] >= tr["stop"]):
            hit = ("sl", tr["stop"], k["time"])
            break
        if (k["high"] >= tr["tp"]) if side > 0 else (k["low"] <= tr["tp"]):
            hit = ("tp", tr["tp"], k["time"])
            break
    last = float(raw[-1][4]) if raw else tr["entry"]
    if not hit and time.time() - tr["at"] >= HOLD_SEC:
        hit = ("time", last, time.time())
    return hit, last


def exit_message(sym, tr, hit):
    kind, price, _ = hit
    side = tr["side"]
    pct = side * (price / tr["entry"] - 1) * 100 - 2 * FEE * 100
    usd = tr.get("notional", 0) * pct / 100
    hours = (time.time() - tr["at"]) / 3600
    name = f"{'Long' if side > 0 else 'Short'} <b>{label(sym)}</b>"
    head = {"tp": "🎯 <b>ដល់ Take-profit!</b>", "sl": "🛑 <b>ដល់ Stop-loss</b>", "time": "⏱ <b>ដល់ 7 ថ្ងៃ — បិទ position ឥឡូវ</b>"}[kind]
    lines = [head, f"{name} · ចូល {fmt(tr['entry'])} → {fmt(price)}",
             f"{'ចំណេញ' if pct >= 0 else 'ខាត'} <b>{pct:+.2f}%</b>" + (f" · ≈ <b>{'+' if usd >= 0 else '-'}${abs(usd):,.2f}</b>" if usd else "") + f" (ក្រោយថ្លៃសេវា · {hours:.0f} ម៉ោង)"]
    if kind == "sl":
        lines.append("ខាតម្តងៗ ជាផ្នែកមួយនៃផែនការ (ត្រូវ ~45%) — កុំបង្កើនទំហំដើម្បីសងវិញ")
    elif kind == "tp":
        lines.append("Binance បិទឱ្យដោយខ្លួនឯង បើអ្នកបានដាក់ TP · បើមិនទាន់ សូមបិទឥឡូវ")
    else:
        lines.append("ផែនការកាន់យូរបំផុត 7 ថ្ងៃ — បិទដោយដៃនៅលើ Binance")
    return "\n".join(lines)


def status_line(r):
    if r["go"]:
        return f"{'🟢 LONG' if r['go'] > 0 else '🔴 SHORT'}  {label(r['sym'])} ({r['score']:+d})"
    if r["side"]:
        why = "កម្លាំងខ្សោយ" if not r["st"]["strong"] else "សាកល្បងមិនល្អ"
        return f"🟠 {'Long' if r['side'] > 0 else 'Short'} {label(r['sym'])} — {why} ({r['score']:+d})"
    return f"⏸ {label(r['sym'])} — រង់ចាំ ({r['score']:+d})"


# ------------------------------------------------------------------ telegram
def tg(method, tries=4, **params):
    token = os.environ["TELEGRAM_TOKEN"].strip()
    data = urllib.parse.urlencode(params).encode()
    for k in range(tries):
        try:
            with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/{method}", data=data, timeout=40) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:            # wrong token / chat id → no point retrying
            body = e.read().decode(errors="replace")[:200]
            raise RuntimeError(f"Telegram {e.code}: {body}") from None
        except Exception as e:
            print(f"Telegram try {k + 1}/{tries} failed: {type(e).__name__}: {e}")
            if k == tries - 1:
                raise RuntimeError(f"Telegram unreachable: {type(e).__name__}") from None
            time.sleep(5 * (k + 1))


def send(text):
    ok = True
    for chat in os.environ["TELEGRAM_CHAT_ID"].split(","):
        try:
            tg("sendMessage", chat_id=chat.strip(), text=text, parse_mode="HTML", disable_web_page_preview="true")
            print("✓ sent to chat", chat.strip()[-4:].rjust(8, "*"))
        except Exception as e:
            ok = False
            print("✗ SEND FAILED:", e)
    return ok


STATE_FILE = os.environ.get("STATE_FILE", "alert_state.json")


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            st = json.load(f)
    except Exception:
        st = {}
    st.setdefault("alerted", {})
    st.setdefault("tests", {})
    return st


def save_state(st):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, separators=(",", ":"))


def tests_for(sym, st):
    """5-year test of each coin, re-run once a day (it barely changes) so each check stays fast."""
    hit = st["tests"].get(sym)
    if hit and time.time() - hit["at"] < 86400:
        return {1: hit["1"], -1: hit["-1"]}
    hist = klines_range(sym, int((time.time() - YEARS * 365 * 86400 - 210 * STEP) * 1000))
    if len(hist) < 600:
        raise RuntimeError("ទិន្នន័យតិចពេក")
    t = backtest(hist)
    st["tests"][sym] = {"at": int(time.time()), "1": t[1], "-1": t[-1]}
    return t


def main():
    if "--chatid" in sys.argv:
        ups = tg("getUpdates").get("result", [])
        ids = {(u.get("message") or u.get("channel_post") or {}).get("chat", {}).get("id") for u in ups} - {None}
        print("chat id:", ", ".join(map(str, ids)) if ids else "មិនទាន់ឃើញ — សូមផ្ញើសារណាមួយទៅ bot របស់អ្នកសិន ហើយដំណើរការម្តងទៀត")
        return
    test_mode = "--test" in sys.argv
    state = load_state()
    results, errors = [], []
    for sym in COINS:
        sym = sym.strip().upper()
        try:
            results.append(check(sym, tests_for(sym, state)))
        except Exception as e:
            errors.append(f"{sym}: {e}")
    for r in results:
        print(status_line(r))
    for e in errors:
        print("ERR", e)
    print(f"checked {len(results)} coin(s), {len(errors)} error(s)")
    # 1) follow the trades already announced: tell when they hit SL / TP / 7 days
    state.setdefault("trades", {})
    state.pop("alerted", None)
    sent_ok, new = True, []
    for sym, tr in list(state["trades"].items()):
        try:
            hit, last = follow_trade(sym, tr)
        except Exception as e:
            errors.append(f"{sym} follow: {e}")
            continue
        print(f"open {sym} {'L' if tr['side'] > 0 else 'S'} entry {fmt(tr['entry'])} now {fmt(last)}" + (f" → {hit[0]}" if hit else ""))
        if hit and send(exit_message(sym, tr, hit)):
            del state["trades"][sym]
    # 2) announce new setups — one at a time per coin, like the 5-year test
    for r in results:
        if r["go"] and r["sym"] not in state["trades"]:
            ok = send(setup_message(r))
            sent_ok &= ok
            if ok:
                P = plan(r)
                state["trades"][r["sym"]] = {"side": r["go"], "entry": P["entry"], "stop": P["stop"], "tp": P["tp"],
                                             "notional": round(P["notional"], 2), "at": int(time.time())}
                new.append(r)
    save_state(state)
    if test_mode:
        body = "\n".join(status_line(r) for r in results) or "—"
        if state["trades"]:
            body += "\n\n📂 កំពុងតាមដាន: " + ", ".join(f"{'Long' if t['side'] > 0 else 'Short'} {label(k)} (SL {fmt(t['stop'])} · TP {fmt(t['tp'])})" for k, t in state["trades"].items())
        sent_ok &= send("🧪 <b>សាកល្បង Telegram</b> — ស្ថានភាព 4h ឥឡូវ\n\n" + body +
             ("\n\n⚠️ " + "; ".join(errors) if errors else "") +
             "\n\nអ្នកនឹងទទួលសារភ្លាមៗ ពេលកាក់ណាមួយអាចចូល 🟢 LONG ឬ 🔴 SHORT បាន (ពិនិត្យរៀងរាល់ 15 នាទី)")
    print(f"sent {len(new)} setup message(s)" + (" + test" if test_mode else ""))
    if (errors and not results) or not sent_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
