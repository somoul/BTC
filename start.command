#!/bin/bash
# ចុចពីរដងលើឯកសារនេះនៅលើ Mac ដើម្បីបើក BTC Dashboard
cd "$(dirname "$0")"

# បិទ server ចាស់ (ប្រសិនបើកំពុងដំណើរការ) ដើម្បីប្រើកូដថ្មីបំផុត
OLD=$(lsof -ti tcp:8000 2>/dev/null)
if [ -n "$OLD" ]; then
  echo "🔄 បិទ server ចាស់..."
  kill $OLD 2>/dev/null
  sleep 1
fi

if [ ! -d ".venv" ]; then
  echo "⏳ ដំឡើងលើកដំបូង (ប្រហែល 1 នាទី)..."
  python3 -m venv .venv || { echo "❌ សូមដំឡើង Python 3 ពី python.org"; read -r; exit 1; }
fi
source .venv/bin/activate
pip install -q -r requirements.txt

( sleep 3; open "http://localhost:8000" ) &
python app.py
