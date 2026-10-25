"""
BTC Monitor - ទាញតម្លៃ BTC ពី Binance ជាប្រចាំ ហើយវាយតម្លៃថានឹង ឡើង ឬ ចុះ

របៀបប្រើ:
    python btc_monitor.py                      # ពិនិត្យម្តង (1h)
    python btc_monitor.py --loop 15            # ពិនិត្យរៀងរាល់ 15 នាទី
    python btc_monitor.py --interval 4h        # ប្រើ chart 4 ម៉ោង
    python btc_monitor.py --ai                 # បន្ថែមការពន្យល់ពី AI ជាភាសាខ្មែរ
    python btc_monitor.py --backtest           # សាកល្បងលើទិន្នន័យចាស់ ដើម្បីដឹងថាត្រូវប៉ុន្មាន %

⚠️ គ្មាននរណាម្នាក់ ឬ AI ណាមួយអាចទាយតម្លៃបានត្រឹមត្រូវ 100% ទេ។
   នេះជាឧបករណ៍ជំនួយ មិនមែនជាដំបូន្មានហិរញ្ញវត្ថុទេ។
"""

import argparse
import csv
import os
import sys
import time
from datetime import datetime

import pandas as pd
import requests

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# data-api.binance.vision ជា endpoint សាធារណៈសម្រាប់តែទិន្នន័យទីផ្សារ (មិនត្រូវការ API key)
BINANCE_URLS = [
    "https://data-api.binance.vision/api/v3/klines",
    "https://api.binance.com/api/v3/klines",
]
LOG_FILE = "signals_log.csv"
MODEL = os.environ.get("BTC_BOT_MODEL", "claude-sonnet-5-5")


# ---------------------------------------------------------------- ទាញទិន្នន័យ
def fetch_klines(symbol="BTCUSDT", interval="1h", limit=500) -> pd.DataFrame:
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    last_error = None
    for url in BINANCE_URLS:
        try:
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            rows = r.json()
            break
        except Exception as e:  # សាក URL បន្ទាប់
            last_error = e
    else:
        raise ConnectionError(f"មិនអាចភ្ជាប់ទៅ Binance បានទេ: {last_error}")

    df = pd.DataFrame(
        rows,
        columns=["open_time", "open", "high", "low", "close", "volume",
                 "close_time", "qav", "trades", "tbbav", "tbqav", "ignore"],
    )
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    df["time"] = pd.to_datetime(df["open_time"], unit="ms")
    return df[["time", "open", "high", "low", "close", "volume"]]


# ---------------------------------------------------------------- Indicators
def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    c = df["close"]

    df["ema20"] = c.ewm(span=20, adjust=False).mean()
    df["ema50"] = c.ewm(span=50, adjust=False).mean()
    df["ema200"] = c.ewm(span=200, adjust=False).mean()

    # RSI 14 (Wilder)
    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    df["rsi"] = 100 - 100 / (1 + gain / loss)

    # MACD 12/26/9
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    df["macd"] = macd
    df["macd_signal"] = macd.ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    # Bollinger Bands 20, 2
    mid = c.rolling(20).mean()
    std = c.rolling(20).std()
    df["bb_upper"] = mid + 2 * std
    df["bb_lower"] = mid - 2 * std
    df["bb_pos"] = (c - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])

    df["vol_ratio"] = df["volume"] / df["volume"].rolling(20).mean()
    df["mom10"] = c.pct_change(10) * 100
    return df


# ---------------------------------------------------------------- វាយតម្លៃ
def score_row(row) -> tuple[int, list[str]]:
    """ផ្តល់ពិន្ទុ -100..+100 និងហេតុផលនីមួយៗ"""
    points, reasons = 0, []

    def vote(cond_up, cond_down, weight, up_txt, down_txt):
        nonlocal points
        if cond_up:
            points += weight
            reasons.append(f"🟢 {up_txt}")
        elif cond_down:
            points -= weight
            reasons.append(f"🔴 {down_txt}")

    vote(row.close > row.ema200, row.close < row.ema200, 20,
         "តម្លៃនៅលើ EMA200 (និន្នាការធំឡើង)", "តម្លៃនៅក្រោម EMA200 (និន្នាការធំចុះ)")
    vote(row.ema20 > row.ema50, row.ema20 < row.ema50, 20,
         "EMA20 នៅលើ EMA50", "EMA20 នៅក្រោម EMA50")
    vote(row.macd_hist > 0, row.macd_hist < 0, 15,
         "MACD histogram វិជ្ជមាន", "MACD histogram អវិជ្ជមាន")
    vote(row.mom10 > 0, row.mom10 < 0, 15,
         f"Momentum 10 candle +{row.mom10:.2f}%", f"Momentum 10 candle {row.mom10:.2f}%")

    # RSI: ខ្លាំងពេកអាចត្រឡប់វិញ
    if row.rsi < 30:
        points += 15
        reasons.append(f"🟢 RSI {row.rsi:.0f} — Oversold (អាចងើបវិញ)")
    elif row.rsi > 70:
        points -= 15
        reasons.append(f"🔴 RSI {row.rsi:.0f} — Overbought (អាចធ្លាក់វិញ)")
    else:
        vote(row.rsi > 50, row.rsi < 50, 10,
             f"RSI {row.rsi:.0f} លើ 50", f"RSI {row.rsi:.0f} ក្រោម 50")

    # Bollinger
    if row.bb_pos < 0.05:
        points += 10
        reasons.append("🟢 តម្លៃប៉ះ Bollinger ខាងក្រោម")
    elif row.bb_pos > 0.95:
        points -= 10
        reasons.append("🔴 តម្លៃប៉ះ Bollinger ខាងលើ")

    return max(-100, min(100, int(points))), reasons


def verdict(score: int) -> str:
    if score >= 30:
        return "📈 ទំនងឡើង (UP)"
    if score <= -30:
        return "📉 ទំនងចុះ (DOWN)"
    return "➖ មិនច្បាស់ (NEUTRAL)"


# ---------------------------------------------------------------- AI (ស្រេចចិត្ត)
def ai_explain(summary: str) -> str:
    try:
        import anthropic
    except ImportError:
        return "(មិនទាន់ដំឡើង anthropic)"
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return "(មិនមាន ANTHROPIC_API_KEY ក្នុង .env)"
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=MODEL,
        max_tokens=800,
        system=("អ្នកជាអ្នកវិភាគបច្ចេកទេស BTC។ ពន្យល់ជាភាសាខ្មែរ ខ្លីៗ ច្បាស់ៗ (មិនលើស 8 បន្ទាត់)។ "
                "ប្រាប់ថាសញ្ញាទាំងនេះមានន័យយ៉ាងណា កម្រិតតម្លៃដែលគួរមើល និងហានិភ័យ។ "
                "និយាយត្រង់ៗថាគ្មានអ្នកណាទាយបានប្រាកដ។ មិនមែនជាដំបូន្មានហិរញ្ញវត្ថុទេ។"),
        messages=[{"role": "user", "content": summary}],
    )
    return "".join(b.text for b in msg.content if b.type == "text")


# ---------------------------------------------------------------- ពិនិត្យម្តង
def check_once(symbol, interval, use_ai=False):
    df = add_indicators(fetch_klines(symbol, interval))
    row = df.iloc[-2]          # candle ចុងក្រោយដែលបិទរួច (មិនប្រើ candle កំពុងរត់)
    live_price = df.iloc[-1].close
    score, reasons = score_row(row)
    v = verdict(score)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "=" * 52,
        f"🕒 {now}   {symbol}  ({interval})",
        f"💰 តម្លៃបច្ចុប្បន្ន: ${live_price:,.2f}",
        f"🎯 ការវាយតម្លៃ: {v}   ពិន្ទុ {score:+d}/100",
        "-" * 52,
        *reasons,
        "-" * 52,
        f"EMA20 ${row.ema20:,.0f} | EMA50 ${row.ema50:,.0f} | EMA200 ${row.ema200:,.0f}",
        f"Bollinger: ${row.bb_lower:,.0f} – ${row.bb_upper:,.0f}",
    ]
    report = "\n".join(lines)
    print(report)

    if use_ai:
        print("\n🤖 AI ពន្យល់:\n" + ai_explain(report))

    log_signal(now, symbol, interval, live_price, score, v)
    print("⚠️ មិនមែនជាដំបូន្មានហិរញ្ញវត្ថុទេ។")


def log_signal(now, symbol, interval, price, score, v):
    new = not os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "symbol", "interval", "price", "score", "verdict"])
        w.writerow([now, symbol, interval, f"{price:.2f}", score, v])


# ---------------------------------------------------------------- Backtest
def backtest(df: pd.DataFrame, horizon=4) -> dict:
    """ពិនិត្យថា សញ្ញា UP/DOWN ត្រូវប៉ុន្មាន % ក្រោយ horizon candle"""
    df = add_indicators(df).dropna().reset_index(drop=True)
    stats = {"UP": [0, 0], "DOWN": [0, 0]}
    ups_real = 0
    for i in range(len(df) - horizon):
        score, _ = score_row(df.iloc[i])
        future_up = df.close.iloc[i + horizon] > df.close.iloc[i]
        ups_real += future_up
        if score >= 30:
            stats["UP"][1] += 1
            stats["UP"][0] += future_up
        elif score <= -30:
            stats["DOWN"][1] += 1
            stats["DOWN"][0] += not future_up
    n = len(df) - horizon
    return {"samples": n, "base_up_rate": ups_real / n * 100 if n else 0, "stats": stats}


def run_backtest(symbol, interval, horizon):
    df = fetch_klines(symbol, interval, limit=1000)
    r = backtest(df, horizon)
    print(f"📊 Backtest {symbol} {interval} — ទាយ {horizon} candle ទៅមុខ ({r['samples']} ករណី)")
    print(f"   តម្លៃឡើងដោយខ្លួនឯង (ទាយចៃដន្យ): {r['base_up_rate']:.1f}%")
    for k, (hit, total) in r["stats"].items():
        pct = hit / total * 100 if total else 0
        print(f"   សញ្ញា {k:4}: ត្រូវ {hit}/{total} = {pct:.1f}%")
    print("👉 បើភាគរយមិនខ្ពស់ជាង 'ទាយចៃដន្យ' ច្រើនទេ មានន័យថាសញ្ញានោះមិនសូវមានប្រយោជន៍។")


# ---------------------------------------------------------------- main
def main():
    p = argparse.ArgumentParser(description="BTC Monitor - Binance")
    p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument("--interval", default="1h", help="1m 5m 15m 1h 4h 1d ...")
    p.add_argument("--loop", type=int, default=0, help="ពិនិត្យរៀងរាល់ N នាទី (0 = ម្តង)")
    p.add_argument("--ai", action="store_true", help="បន្ថែមការពន្យល់ពី AI")
    p.add_argument("--backtest", action="store_true")
    p.add_argument("--horizon", type=int, default=4, help="ចំនួន candle ទៅមុខសម្រាប់ backtest")
    a = p.parse_args()

    try:
        if a.backtest:
            run_backtest(a.symbol, a.interval, a.horizon)
            return
        if a.loop <= 0:
            check_once(a.symbol, a.interval, a.ai)
            return
        print(f"🔁 ពិនិត្យរៀងរាល់ {a.loop} នាទី — ចុច Ctrl+C ដើម្បីបញ្ឈប់")
        while True:
            try:
                check_once(a.symbol, a.interval, a.ai)
            except Exception as e:
                print(f"❌ {e} — នឹងសាកម្តងទៀត")
            time.sleep(a.loop * 60)
    except KeyboardInterrupt:
        print("\n👋 បានបញ្ឈប់")
    except Exception as e:
        print(f"❌ មានបញ្ហា: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
