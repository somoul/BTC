"""
analysis.py - ម៉ាស៊ីនវិភាគ: សញ្ញា BUY/SELL/HOLD, Support/Resistance, គោលដៅតម្លៃ, Stop-loss
ប្រើដោយ app.py (web) និងអាចប្រើផ្ទាល់:  python analysis.py
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pandas as pd

from btc_monitor import add_indicators, fetch_klines, score_row

def px(x):
    """ប្រាក់ (price) → រក្សាលេខសំខាន់ 7 ខ្ទង់ ដើម្បីឱ្យកាក់ថោក (DOGE $0.1987) មិនបាត់ទសភាគ"""
    return float(f"{float(x):.7g}")


TIMEFRAMES = ["5m", "15m", "1h", "4h", "1d"]
TF_WEIGHT = {"5m": 0.3, "15m": 0.5, "1h": 1.0, "4h": 1.5, "1d": 2.0}


def add_atr(df: pd.DataFrame, n=14) -> pd.DataFrame:
    prev = df["close"].shift()
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1
    ).max(axis=1)
    df["atr"] = tr.ewm(alpha=1 / n, adjust=False).mean()
    return df


def signal_of(score: int) -> str:
    if score >= 30:
        return "BUY"
    if score <= -30:
        return "SELL"
    return "HOLD"


# ---------------------------------------------------------------- Support / Resistance
def swing_levels(df: pd.DataFrame, k=5, lookback=300):
    """រក swing high/low (ចំណុចកំពូល/បាត) ហើយបូកបញ្ចូលកម្រិតដែលជិតគ្នា"""
    d = df.tail(lookback).reset_index(drop=True)
    pts = []
    for i in range(k, len(d) - k):
        win = d.iloc[i - k: i + k + 1]
        if d.high[i] == win.high.max():
            pts.append(d.high[i])
        if d.low[i] == win.low.min():
            pts.append(d.low[i])
    pts.sort()

    tol = 0.004  # 0.4% → ចាត់ទុកជាកម្រិតតែមួយ
    clusters = []
    for p in pts:
        if clusters and abs(p - clusters[-1]["avg"]) / clusters[-1]["avg"] < tol:
            c = clusters[-1]
            c["sum"] += p
            c["n"] += 1
            c["avg"] = c["sum"] / c["n"]
        else:
            clusters.append({"sum": p, "n": 1, "avg": p})
    return [(c["avg"], c["n"]) for c in clusters]


def price_levels(df: pd.DataFrame, price: float, atr: float, count=3):
    levels = swing_levels(df)
    min_gap = atr * 0.3  # កុំយកកម្រិតជិតតម្លៃពេក
    sup = sorted([l for l in levels if l[0] < price - min_gap], key=lambda x: -x[0])
    res = sorted([l for l in levels if l[0] > price + min_gap], key=lambda x: x[0])

    def pack(items, side):
        out = [{"price": px(float(p)), "touches": int(n), "source": "swing",
                "dist_pct": round(float(p - price) / price * 100, 2)} for p, n in items[:count]]
        # បំពេញដោយ ATR ប្រសិនបើរកមិនគ្រប់
        step = 1 if side == "res" else -1
        last = out[-1]["price"] if out else price
        while len(out) < count:
            last = last + step * 1.5 * atr
            out.append({"price": px(last), "touches": 0, "source": "atr",
                        "dist_pct": round((last - price) / price * 100, 2)})
        return out

    return pack(sup, "sup"), pack(res, "res")


# ---------------------------------------------------------------- Trade plan
def trade_plan(signal, price, atr, supports, resistances):
    s1, s2 = supports[0]["price"], supports[1]["price"]
    r1, r2 = resistances[0]["price"], resistances[1]["price"]

    def pick_targets(levels, entry, risk, direction):
        """គោលដៅ 1 = កម្រិតដំបូងដែលចំណេញ ≥ ហានិភ័យ (R:R ≥ 1); គោលដៅ 2 = កម្រិតបន្ទាប់"""
        prices = [l["price"] for l in levels]
        far = [p for p in prices if abs(p - entry) >= risk]
        t1 = far[0] if far else prices[-1]
        rest = [p for p in prices if (p - t1) * direction > 0]
        t2 = rest[0] if rest else t1 + direction * 1.5 * atr
        return t1, t2

    entry = price
    if signal == "BUY":
        stop = max(s1 - 0.5 * atr, price - 3 * atr)
        tp1, tp2 = pick_targets(resistances, entry, entry - stop, +1)
    elif signal == "SELL":
        stop = min(r1 + 0.5 * atr, price + 3 * atr)
        tp1, tp2 = pick_targets(supports, entry, stop - entry, -1)
    else:
        return {
            "action": "HOLD",
            "entry": None, "stop": None, "tp1": None, "tp2": None, "rr": None,
            "buy_zone": px(s1), "sell_zone": px(r1),
        }

    risk = abs(entry - stop)
    reward = abs(tp1 - entry)
    return {
        "action": signal,
        "entry": px(float(entry)), "stop": px(float(stop)),
        "tp1": px(float(tp1)), "tp2": px(float(tp2)),
        "rr": round(float(reward / risk), 2) if risk else None,
        "buy_zone": px(float(s1)), "sell_zone": px(float(r1)),
    }


# ---------------------------------------------------------------- វិភាគ timeframe មួយ
def analyze_df(df: pd.DataFrame, interval: str) -> dict:
    df = add_atr(add_indicators(df))
    row = df.iloc[-2]                 # candle ចុងក្រោយដែលបិទរួច
    price = float(df.iloc[-1].close)  # តម្លៃបច្ចុប្បន្ន
    atr = float(row.atr)
    score, reasons = score_row(row)
    sig = signal_of(score)
    supports, resistances = price_levels(df, price, atr)

    candles = [
        {"time": int(t.timestamp()), "open": o, "high": h, "low": l, "close": c}
        for t, o, h, l, c in df.tail(200)[["time", "open", "high", "low", "close"]].itertuples(index=False)
    ]
    ema = lambda col: [  # noqa: E731
        {"time": int(t.timestamp()), "value": px(v)}
        for t, v in df.tail(200)[["time", col]].itertuples(index=False)
    ]

    return {
        "interval": interval,
        "price": price,
        "score": score,
        "signal": sig,
        "reasons": reasons,
        "supports": supports,
        "resistances": resistances,
        "plan": trade_plan(sig, price, atr, supports, resistances),
        "indicators": {
            "rsi": round(float(row.rsi), 1),
            "macd_hist": px(float(row.macd_hist)),
            "ema20": px(float(row.ema20)),
            "ema50": px(float(row.ema50)),
            "ema200": px(float(row.ema200)),
            "bb_upper": px(float(row.bb_upper)),
            "bb_lower": px(float(row.bb_lower)),
            "atr": px(atr),
            "vol_ratio": round(float(row.vol_ratio), 2),
        },
        "candles": candles,
        "ema20": ema("ema20"),
        "ema50": ema("ema50"),
    }


def analyze(symbol="BTCUSDT", interval="1h") -> dict:
    return analyze_df(fetch_klines(symbol, interval, limit=500), interval)


def analyze_all(symbol="BTCUSDT", previous=None) -> dict:
    """វិភាគគ្រប់ timeframe (ស្របគ្នា) ហើយរួមបញ្ចូលជាសញ្ញាមួយ។
    ប្រសិនបើ timeframe មួយបរាជ័យ ប្រើលទ្ធផលចាស់របស់វា ជំនួសឱ្យគាំងទាំងអស់។"""
    results, errors = {}, {}
    with ThreadPoolExecutor(max_workers=len(TIMEFRAMES)) as pool:
        futures = {tf: pool.submit(analyze, symbol, tf) for tf in TIMEFRAMES}
        for tf, fut in futures.items():
            try:
                results[tf] = fut.result(timeout=30)
            except Exception as e:
                errors[tf] = str(e)
                if previous and tf in previous.get("frames", {}):
                    results[tf] = previous["frames"][tf]
    if not results:
        raise ConnectionError("; ".join(f"{k}: {v}" for k, v in errors.items()))

    tfs = [tf for tf in TIMEFRAMES if tf in results]
    total_w = sum(TF_WEIGHT[tf] for tf in tfs)
    combined = round(sum(results[tf]["score"] * TF_WEIGHT[tf] for tf in tfs) / total_w)
    return {
        "symbol": symbol,
        "updated": datetime.now(timezone.utc).isoformat(),
        "overall": {"score": combined, "signal": signal_of(combined)},
        "mtf": {tf: {"score": results[tf]["score"], "signal": results[tf]["signal"]} for tf in tfs},
        "frames": results,
        "verdict": decide(results, combined),
        "scalp": scalp_5m(results),
        "partial_errors": errors,
    }


# ---------------------------------------------------------------- ជួញដូរ 5 នាទី
def scalp_5m(frames: dict):
    """ផែនការសម្រាប់ជួញដូររយៈពេលខ្លី (5 នាទី)
    - សញ្ញាពី 5m
    - តម្រងនិន្នាការពី 15m + 1h (កុំទិញពេលនិន្នាការធំកំពុងចុះ ហើយផ្ទុយមកវិញ)
    - Stop / គោលដៅ គណនាពី ATR 5m"""
    f = frames.get("5m")
    if not f:
        return None
    price = f["price"]
    ind = f["indicators"]
    atr = ind["atr"]
    s1, r1 = f["supports"][0]["price"], f["resistances"][0]["price"]

    trend_score = round(0.4 * frames.get("15m", {}).get("score", 0) + 0.6 * frames.get("1h", {}).get("score", 0))
    trend = "UP" if trend_score >= 20 else "DOWN" if trend_score <= -20 else "FLAT"

    score = f["score"]
    if score >= 30 and trend != "DOWN":
        action = "BUY"
    elif score <= -30 and trend != "UP":
        action = "SELL"
    else:
        action = "WAIT"

    # ហេតុផលរង់ចាំ
    why = []
    if action == "WAIT":
        if score >= 30 and trend == "DOWN":
            why.append("5 នាទីឡើង ប៉ុន្តែនិន្នាការធំ (15m/1h) កំពុងចុះ — ងាយធ្លាក់មកវិញ")
        elif score <= -30 and trend == "UP":
            why.append("5 នាទីចុះ ប៉ុន្តែនិន្នាការធំ (15m/1h) កំពុងឡើង — ប្រហែលគ្រាន់តែស្រកបន្តិច")
        else:
            why.append(f"សញ្ញា 5 នាទីមិនទាន់ខ្លាំងគ្រប់គ្រាន់ (ពិន្ទុ {score:+d}, ត្រូវការ ±30)")

    r = lambda x: px(float(x))  # noqa: E731
    plan = {"entry": None, "better_entry": None, "stop": None, "tp1": None, "tp2": None,
            "rr": None, "buy_above": None, "buy_dip": None, "sell_below": None}

    if action == "BUY":
        stop = min(price - 1.2 * atr, s1 - 0.3 * atr)
        stop = max(stop, price - 2.5 * atr)          # កុំឱ្យ stop ឆ្ងាយពេក
        risk = price - stop
        plan.update(entry=r(price), better_entry=r(max(ind["ema20"], stop + 0.5 * risk)) if ind["ema20"] < price else None,
                    stop=r(stop), tp1=r(price + 1.5 * risk), tp2=r(price + 2.5 * risk), rr=1.5)
    elif action == "SELL":
        stop = max(price + 1.2 * atr, r1 + 0.3 * atr)
        stop = min(stop, price + 2.5 * atr)
        risk = stop - price
        plan.update(entry=r(price), better_entry=r(min(ind["ema20"], stop - 0.5 * risk)) if ind["ema20"] > price else None,
                    stop=r(stop), tp1=r(price - 1.5 * risk), tp2=r(price - 2.5 * risk), rr=1.5)
    else:
        plan.update(buy_above=r(r1), buy_dip=r(s1), sell_below=r(s1))

    # ពេលវេលា: candle 5m បិទរៀងរាល់ 5 នាទី
    now = datetime.now(timezone.utc)
    next_close = (int(now.timestamp()) // 300 + 1) * 300

    return {
        "action": action,
        "score": score,
        "trend": trend,
        "trend_score": trend_score,
        "price": price,
        "atr": atr,
        "rsi": ind["rsi"],
        "why": why,
        "plan": plan,
        "max_hold_minutes": 60,
        "next_candle_close": next_close,
    }


# ---------------------------------------------------------------- សេចក្តីសម្រេចចុងក្រោយ
TF_KM = {"5m": "5 នាទី", "15m": "15 នាទី", "1h": "1 ម៉ោង", "4h": "4 ម៉ោង", "1d": "1 ថ្ងៃ"}


def decide(frames: dict, combined: int) -> dict:
    """រួមបញ្ចូលគ្រប់ timeframe ជាចម្លើយតែមួយ: BUY / SELL / WAIT
    - ទិញ/លក់ លុះត្រាតែពិន្ទុរួមខ្លាំងគ្រប់គ្រាន់ ហើយ timeframe ធំ (4h, 1D) មិនប្រឆាំង
    - បើ timeframe ខ្លី និងវែងប្រឆាំងគ្នា → រង់ចាំ"""
    sig = {tf: f["signal"] for tf, f in frames.items()}
    big = [sig.get("4h"), sig.get("1d")]
    reasons = []

    if combined >= 30 and "SELL" not in big:
        action = "BUY"
    elif combined <= -30 and "BUY" not in big:
        action = "SELL"
    else:
        action = "WAIT"

    agree = [tf for tf, s in sig.items() if s == action]
    against = [tf for tf, s in sig.items() if s in ("BUY", "SELL") and s != action and action != "WAIT"]

    # កម្រិតជឿជាក់
    if action == "WAIT":
        confidence = "-"
    elif abs(combined) >= 50 and len(agree) >= 3 and not against:
        confidence = "ខ្ពស់"
    elif len(agree) >= 2 and not against:
        confidence = "មធ្យម"
    else:
        confidence = "ទាប"

    # ហេតុផលជាភាសាធម្មតា
    ups = [TF_KM[tf] for tf in TIMEFRAMES if sig.get(tf) == "BUY"]
    downs = [TF_KM[tf] for tf in TIMEFRAMES if sig.get(tf) == "SELL"]
    if ups:
        reasons.append("📈 ទំនងឡើង: " + ", ".join(ups))
    if downs:
        reasons.append("📉 ទំនងចុះ: " + ", ".join(downs))
    if action == "WAIT":
        if combined >= 30 or combined <= -30:
            reasons.append("⚖️ timeframe ធំ (4 ម៉ោង / 1 ថ្ងៃ) ប្រឆាំងនឹងទិសដៅ — គ្រោះថ្នាក់ពេកក្នុងការចូល")
        else:
            reasons.append("⚖️ សញ្ញាមិនទាន់ខ្លាំងគ្រប់គ្រាន់ (ពិន្ទុរួម {:+d}, ត្រូវការ ±30)".format(combined))

    # ប្រើ timeframe 1h សម្រាប់តម្លៃចូល/ចេញ (បើគ្មាន ប្រើ 4h)
    base_tf = "1h" if "1h" in frames else next(iter(frames))
    f = frames[base_tf]
    price, atr = f["price"], f["indicators"]["atr"]
    rsi = f["indicators"]["rsi"]
    if action == "BUY" and rsi > 70:
        reasons.append(f"⚠️ RSI {rsi:.0f} ខ្ពស់ពេក — អាចធ្លាក់មកវិញបន្តិចមុនឡើងបន្ត")
        confidence = "ទាប" if confidence != "ខ្ពស់" else "មធ្យម"
    if action == "SELL" and rsi < 30:
        reasons.append(f"⚠️ RSI {rsi:.0f} ទាបពេក — អាចងើបវិញបន្តិចមុនធ្លាក់បន្ត")
        confidence = "ទាប" if confidence != "ខ្ពស់" else "មធ្យម"

    plan = trade_plan(action if action != "WAIT" else "HOLD", price, atr, f["supports"], f["resistances"])
    if action != "WAIT" and plan.get("rr") is not None and plan["rr"] < 1.2:
        reasons.append(f"⚠️ Risk:Reward ត្រឹម 1:{plan['rr']} — ចំណេញតិចបើធៀបនឹងហានិភ័យ")
        if confidence == "ខ្ពស់":
            confidence = "មធ្យម"

    headline = {
        "BUY": "សញ្ញាបច្ចេកទេសភាគច្រើនចង្អុលឡើង",
        "SELL": "សញ្ញាបច្ចេកទេសភាគច្រើនចង្អុលចុះ",
        "WAIT": "មិនទាន់មានឱកាសច្បាស់ — ល្អបំផុតគឺរង់ចាំ",
    }[action]

    return {
        "action": action,
        "score": combined,
        "confidence": confidence,
        "headline": headline,
        "reasons": reasons,
        "agree": agree,
        "base_tf": base_tf,
        "plan": plan,
    }


if __name__ == "__main__":
    a = analyze_all()
    o = a["overall"]
    print(f"សរុប: {o['signal']} ({o['score']:+d})")
    for tf, r in a["frames"].items():
        p = r["plan"]
        print(f"[{tf}] {r['signal']:4} {r['score']:+4d} | S1 {r['supports'][0]['price']:,.0f} "
              f"| R1 {r['resistances'][0]['price']:,.0f} | stop {p['stop']} tp1 {p['tp1']}")
