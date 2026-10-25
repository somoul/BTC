"""
BTC Chart AI Bot - វិភាគរូប chart Bitcoin ដោយប្រើ Claude (vision)

របៀបប្រើ:
    pip install -r requirements.txt
    copy .env.example ទៅ .env ហើយដាក់ API key របស់អ្នក
    python btc_chart_bot.py charts/chart.png 4H

ឬដំណើរការដោយមិនដាក់ argument ហើយវានឹងសួររកទីតាំងរូបភាព។
"""

import base64
import mimetypes
import os
import sys

import anthropic

try:
    from dotenv import load_dotenv

    load_dotenv()  # អាន ANTHROPIC_API_KEY ពីឯកសារ .env
except ImportError:
    pass

MODEL = os.environ.get("BTC_BOT_MODEL", "claude-sonnet-5-5")

SYSTEM_PROMPT = """អ្នកជាអ្នកវិភាគបច្ចេកទេស (technical analyst) សម្រាប់ Bitcoin។
អ្នកនឹងទទួលរូប chart តម្លៃ BTC។ សូមឆ្លើយជាភាសាខ្មែរ តាមទម្រង់ខាងក្រោម៖

1. 📊 ព័ត៌មានពី chart: timeframe, តម្លៃបច្ចុប្បន្ន (បើមើលឃើញ), indicator ដែលមាន
2. 📈 និន្នាការ (Trend): ឡើង / ចុះ / ចំហៀង និងមូលហេតុ
3. 🧱 Support និង Resistance សំខាន់ៗ (តម្លៃប្រហាក់ប្រហែល)
4. 🕯️ Pattern ឬ Candlestick ដែលគួរកត់សម្គាល់
5. 📉 Indicators (RSI, MACD, MA, Volume...) បើមានក្នុងរូប
6. 🔮 សេណារីយ៉ូ៖
   - Bullish: លក្ខខណ្ឌ + គោលដៅតម្លៃ
   - Bearish: លក្ខខណ្ឌ + គោលដៅតម្លៃ
7. ⭐ ពិន្ទុទិសដៅ: Bullish / Neutral / Bearish និងកម្រិតជឿជាក់ (ទាប/មធ្យម/ខ្ពស់)
8. ⚠️ ហានិភ័យ និងចំណុចដែលមិនច្បាស់ក្នុងរូប

ច្បាប់:
- និយាយត្រង់ៗ ប្រសិនបើរូបមិនច្បាស់ ឬមិនមែនជា chart BTC សូមប្រាប់។
- កុំប្រឌិតលេខដែលមើលមិនឃើញក្នុងរូប។
- បញ្ចប់ដោយកំណត់សម្គាល់ថា នេះមិនមែនជាដំបូន្មានហិរញ្ញវត្ថុទេ។
"""


def load_image(path: str):
    if not os.path.isfile(path):
        raise FileNotFoundError(f"រកមិនឃើញឯកសារ: {path}")
    media_type, _ = mimetypes.guess_type(path)
    if media_type not in ("image/png", "image/jpeg", "image/gif", "image/webp"):
        raise ValueError("សូមប្រើរូបភាព .png, .jpg, .gif ឬ .webp")
    with open(path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return media_type, data


def analyze_chart(image_path: str, note: str = "") -> str:
    media_type, data = load_image(image_path)
    client = anthropic.Anthropic()  # អាន ANTHROPIC_API_KEY ពី environment

    user_text = "សូមវិភាគ chart BTC នេះ។"
    if note:
        user_text += f"\nព័ត៌មានបន្ថែម: {note}"

    message = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": data},
                    },
                    {"type": "text", "text": user_text},
                ],
            }
        ],
    )
    return "".join(block.text for block in message.content if block.type == "text")


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("⚠️ សូមកំណត់ ANTHROPIC_API_KEY ជាមុនសិន។")
        sys.exit(1)

    if len(sys.argv) > 1:
        image_path = sys.argv[1]
        note = " ".join(sys.argv[2:])
    else:
        image_path = input("📷 ដាក់ទីតាំងរូប chart BTC: ").strip().strip('"')
        note = input("📝 ព័ត៌មានបន្ថែម (ឧ. timeframe 4H) — Enter ដើម្បីរំលង: ").strip()

    print("\n⏳ កំពុងវិភាគ...\n")
    try:
        print(analyze_chart(image_path, note))
    except Exception as e:
        print(f"❌ មានបញ្ហា: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
