# 🤖 BTC Chart AI Bot

Bot Python ដែលវិភាគរូប chart Bitcoin (BTC) ដោយប្រើ AI (Claude vision) ហើយឆ្លើយជាភាសាខ្មែរ។
អ្នកគ្រាន់តែដាក់រូប screenshot chart ចូល វានឹងប្រាប់អំពីនិន្នាការ, support/resistance, pattern, indicator និងសេណារីយ៉ូ។

## 📁 រចនាសម្ព័ន្ធ

```
btc-chart-bot/
├── btc_chart_bot.py   # វិភាគរូប chart
├── btc_monitor.py     # ទាញតម្លៃពី Binance ជាប្រចាំ ហើយវាយតម្លៃ ឡើង/ចុះ
├── analysis.py        # សញ្ញា BUY/SELL, Support/Resistance, គោលដៅ, Stop-loss
├── app.py             # Web server
├── index.html         # Dashboard UI (ដំណើរការលើ GitHub Pages ក៏បាន)
├── start.command      # ចុចពីរដងនៅលើ Mac ដើម្បីបើក
├── requirements.txt   # library ដែលត្រូវការ
├── .env.example       # គំរូសម្រាប់ API key
├── .gitignore
└── charts/            # ដាក់រូប chart របស់អ្នកនៅទីនេះ
```

## ⚙️ ការដំឡើង

1. ដំឡើង Python 3.9 ឡើងទៅ
2. បង្កើត virtual environment (ស្រេចចិត្ត ប៉ុន្តែល្អ)៖
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # Mac/Linux
   source venv/bin/activate
   ```
3. ដំឡើង library៖
   ```bash
   pip install -r requirements.txt
   ```
4. យក API key ពី https://console.anthropic.com
5. ចម្លង `.env.example` ទៅជា `.env` ហើយដាក់ key របស់អ្នក៖
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ```

## ▶️ របៀបប្រើ

Screenshot chart BTC (ពី TradingView, Binance ...) ហើយដាក់ក្នុង folder `charts/`

```bash
python btc_chart_bot.py charts/chart.png
python btc_chart_bot.py charts/chart.png 4H, RSI 14
```

ឬដំណើរការដោយមិនដាក់ argument ហើយវានឹងសួរអ្នក៖

```bash
python btc_chart_bot.py
```

## 🌐 បើកតាម Internet (GitHub Pages)

`index.html` អាចដំណើរការដោយខ្លួនឯងនៅក្នុង browser ដោយទាញទិន្នន័យពី Binance ផ្ទាល់ ដូច្នេះអាចបង្ហោះលើ GitHub Pages ដោយឥតគិតថ្លៃ។
Repo → **Settings › Pages** → Source: **Deploy from a branch** → Branch: **main** / **(root)** → Save។
បន្ទាប់ពី 1–2 នាទី បើក `https://<ឈ្មោះ-github>.github.io/<ឈ្មោះ-repo>/`

ពេលបើកតាម GitHub Pages គ្រប់យ៉ាងដំណើរការ លើកលែងតែ **ប្រវត្តិ ត្រូវ/ខុស** ដែលត្រូវការ `python app.py` នៅលើកុំព្យូទ័រ។

## 🖥️ Web Dashboard (ស្រួលបំផុត)

**នៅលើ Mac:** ចុចពីរដងលើ `start.command` (លើកដំបូង៖ ចុចកណ្ដុរស្ដាំ → Open)
វានឹងដំឡើងអ្វីៗទាំងអស់ ហើយបើក browser នៅ http://localhost:8000 ដោយខ្លួនឯង។

ឬដំណើរការដោយដៃ៖
```bash
pip install -r requirements.txt
python app.py
```

Dashboard មាន៖
- 🤖 **សួរ AI** (ប៊ូតុងខាងក្រោមឆ្វេង)៖ សួរជាភាសាខ្មែរ — AI មើលសញ្ញា តម្លៃ និង trade របស់អ្នកនៅលើ dashboard ពេលនោះ។ 🆓 ឥតគិតថ្លៃជាមួយ Google Gemini៖ យក key ពី aistudio.google.com/apikey (Gmail · មិនត្រូវការកាត) ហើយបិទភ្ជាប់ក្នុងផ្ទាំង chat តែម្តង។ ឬប្រើ Claude (បង់លុយ)៖ `ANTHROPIC_API_KEY=sk-ant-...` ក្នុង `.env`
- 🕯️ **នាឡិកា Candle**៖ រាប់ថយក្រោយដល់ candle ថ្មី 5m/15m/1h/4h/1D និងជូនដំណឹងពេលមាន candle ថ្មី
- 🚦 **ពេលចូលលេង**៖ ឥឡូវអាចចូលបានទេ · រាប់ថយក្រោយដល់ candle 4h បិទ · ម៉ោងពិនិត្យ 03/07/11/15/19/23
- 🌡 **អារម្មណ៍ផ្សារ**៖ Fear & Greed · BTC Dominance · ទំហំផ្សារ 24ម៉ោង · Order book ទិញ/លក់ (±1%)
- 🔍 **ស្កេនកាក់**៖ កាក់ទាំងអស់ជាមួយសញ្ញា 4 ម៉ោង និងលទ្ធផលសាកល្បង 5 ឆ្នាំ
- 📈 **ក្រាហ្វ**៖ Volume · EMA200 · Bollinger · RSI · MACD (ចុចបើក/បិទ)
- 🔔 **ប្រាប់ពេលតម្លៃដល់**៖ កំណត់តម្លៃផ្ទាល់ខ្លួន (ឬ ±1%, ±3%, R1, S1) — បង្ហាញជាបន្ទាត់លើក្រាហ្វ
- 🗂 **4 ទំព័រ**៖ 🏠 សង្ខេប · 📈 ក្រាហ្វ · 📅 ព្យាករណ៍ · 🔬 ភាពត្រឹមត្រូវ
- 💼 **Trade របស់ខ្ញុំ**៖ គណនាថាគួរទិញប៉ុន្មាន (តាមទុន និង % ហ៊ានខាត) · តាមដានចំណេញ/ខាតផ្ទាល់ · ជូនដំណឹងពេលដល់គោលដៅ / Stop / 7 ថ្ងៃ · កត់ត្រា trade ដែលបិទ (រក្សាទុកក្នុង browser របស់អ្នក)
- 📈 **ក្រាហ្វលុយ 5 ឆ្នាំ**៖ $1,000 ធ្វើតាមសញ្ញា 4 ម៉ោង ធៀបនឹងការទិញទុក
- 📱 **ដំឡើងជា app លើទូរស័ព្ទ**៖ បើកតាម https (GitHub Pages) → iPhone: Share › Add to Home Screen · Android: ⋮ › Install app
- 🎯 **សញ្ញាសំខាន់ 4 ម៉ោង (Swing)** — សញ្ញាតែមួយគត់ដែលចំណេញក្រោយថ្លៃសេវា ពេលសាកល្បង 5 ឆ្នាំ (BTC, ETH, មាស ...)។ ទិញពេលពិន្ទុ 4h ≥ +30 · Stop = 3×ATR · គោលដៅ = 3R · កាន់ទុក ≤ 7 ថ្ងៃ។ ការសាកល្បងប្រើ 2/3 ដំបូងនៃទិន្នន័យដើម្បីជ្រើសការកំណត់ ហើយ 1/3 ចុងក្រោយដើម្បីផ្ទៀងផ្ទាត់
- ⚠️ សញ្ញា 5 នាទី / 15 នាទី / 1 ម៉ោង ខាតក្រោយថ្លៃសេវាក្នុងការសាកល្បង — ប្រើសម្រាប់មើលតែប៉ុណ្ណោះ
- 📰 **ព័ត៌មាន**៖ ប្រតិទិនព្រឹត្តិការណ៍ធំៗ US (Fed, CPI, NFP…) ជាម៉ោងរបស់អ្នក ជាមួយការរាប់ថយក្រោយ, ជូនដំណឹង 30 នាទីមុន, និងព័ត៌មាន crypto ថ្មីៗពី CoinDesk, Cointelegraph, Decrypt, The Block, Bitcoin Magazine (ព័ត៌មានទាញតាម server លើ Mac)
- ⚡ **Futures · Long / Short**៖ គណនា Leverage, Margin, តម្លៃ Liquidation, ពិនិត្យថា Stop-loss នៅមុន Liquidation ឬអត់ ហើយបង្ហាញលទ្ធផលសាកល្បង 5 ឆ្នាំ ខាង Long និង Short
- 🪙 **ជ្រើសរើសកាក់**៖ BTC, មាស (PAXG = មាស 1 អោន), ETH, BNB, SOL, XRP, DOGE ឬវាយឈ្មោះកាក់ផ្សេង (ឧ. ADA, LINK)
- ⚡ **ជួញដូរ 5 នាទី** — ប្រាប់ ទិញ / លក់ / រង់ចាំ ជាជំហានៗ៖ ចូលទិញនៅតម្លៃប៉ុន្មាន, លក់យកចំណេញនៅប៉ុន្មាន, កាត់ខាតនៅប៉ុន្មាន និងម៉ោងរាប់ថយក្រោយរហូតដល់ candle 5m បិទ
- 🧭 **ឥឡូវគួរធ្វើអ្វី?** — សេចក្តីសម្រេចរួមពីគ្រប់ timeframe
- តម្លៃ BTC ផ្ទាល់ (live) ពី Binance
- សញ្ញា **BUY / SELL / HOLD** សម្រាប់ 5m, 15m, 1h, 4h, 1D និងសញ្ញារួម
- **កម្រិតតម្លៃ**៖ បើឡើង អាចទៅដល់ R1/R2/R3 · បើចុះ អាចធ្លាក់ដល់ S1/S2/S3
- **ផែនការ**៖ តម្លៃចូល, Stop-loss, គោលដៅ 1 និង 2, Risk:Reward
- ក្រាហ្វ candlestick ជាមួយ EMA និងបន្ទាត់ Support/Resistance
- 🔔 **ការជូនដំណឹង** (សំឡេង + notification) ពេលសញ្ញារួមប្តូរ ឬតម្លៃកាត់ S1/R1 — ចុចប៊ូតុង "បើកការជូនដំណឹង" ម្តង
- 📋 **ប្រវត្តិសញ្ញា** — រាល់ពេលសញ្ញាប្តូរ ពិនិត្យតម្លៃ 1 ម៉ោងក្រោយ ហើយបង្ហាញថាត្រូវប៉ុន្មាន %

Server ទាញ និងវិភាគទិន្នន័យដោយខ្លួនឯងរៀងរាល់ 15 វិនាទី អ្នកមិនចាំបាច់ចុចអ្វីទេ។
បើកពីទូរស័ព្ទក្នុង WiFi តែមួយ៖ `http://<IP កុំព្យូទ័រ>:8000`

ប្តូររយៈពេល៖ `REFRESH_SECONDS=60 python app.py`

## 📡 BTC Monitor (ក្នុង Terminal)

ទាញតម្លៃ BTC ពី Binance ដោយផ្ទាល់ (មិនត្រូវការគណនី ឬ API key Binance ទេ)
រួចគណនា EMA, RSI, MACD, Bollinger, Momentum ហើយផ្តល់ពិន្ទុ -100 ដល់ +100៖

- ពិន្ទុ ≥ +30 → 📈 ទំនងឡើង
- ពិន្ទុ ≤ -30 → 📉 ទំនងចុះ
- ចន្លោះនោះ → ➖ មិនច្បាស់

```bash
python btc_monitor.py                    # ពិនិត្យម្តង
python btc_monitor.py --loop 15          # ពិនិត្យរៀងរាល់ 15 នាទី (Ctrl+C ដើម្បីឈប់)
python btc_monitor.py --interval 4h      # chart 4 ម៉ោង (1m, 5m, 15m, 1h, 4h, 1d)
python btc_monitor.py --ai               # បន្ថែមការពន្យល់ពី AI ជាភាសាខ្មែរ
python btc_monitor.py --symbol ETHUSDT   # កាក់ផ្សេង
python btc_monitor.py --backtest         # សាកល្បងលើទិន្នន័យ 1000 candle ចាស់
```

រាល់ការពិនិត្យត្រូវបានកត់ទុកក្នុង `signals_log.csv` ដើម្បីឱ្យអ្នកផ្ទៀងផ្ទាត់ពេលក្រោយថាត្រូវឬខុស។

**សូមដំណើរការ `--backtest` មុនគេ** វាបង្ហាញថាសញ្ញា UP/DOWN ធ្លាប់ត្រូវប៉ុន្មាន % បើប្រៀបនឹងការទាយចៃដន្យ។

## 💡 គន្លឹះសម្រាប់លទ្ធផលល្អ

- ប្រើរូបច្បាស់ ឃើញលេខតម្លៃនៅអ័ក្សខាងស្តាំ
- បង្ហាញ timeframe និង indicator (RSI, MACD, Volume) ក្នុងរូប
- ប្រាប់ timeframe ជា argument បន្ថែម (ឧ. `4H`, `1D`)

## ⚠️ ចំណាំ

- AI អាចអានបានតែអ្វីដែលមើលឃើញក្នុងរូបប៉ុណ្ណោះ វាមិនអាចទាយតម្លៃអនាគតបានត្រឹមត្រូវទេ។
- នេះមិនមែនជាដំបូន្មានហិរញ្ញវត្ថុទេ។ សូមប្រើជាជំនួយក្នុងការគិតតែប៉ុណ្ណោះ។
- ការហៅ API នីមួយៗមានថ្លៃ។ កុំចែករំលែកឯកសារ `.env` ឬ API key ជាមួយអ្នកណាម្នាក់។
