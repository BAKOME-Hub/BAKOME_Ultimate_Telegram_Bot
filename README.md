# 🤖 BAKOME Ultimate Telegram Bot

## *AI‑Powered · Zero‑Trust Security · Memory‑Aware*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4)](https://core.telegram.org/bots)
[![Gemini](https://img.shields.io/badge/Google-Gemini-4285F4)](https://deepmind.google/technologies/gemini/)

---

## 🚀 Features

| Category | Features |
|----------|----------|
| **🧠 AI & Security** | Edge Guard (local injection filter) + Cloud Brain (Gemini / DeepSeek / Ollama) + SQLite memory |
| **💰 Trading** | Live crypto prices (BTC, ETH, SOL) & forex rates (EUR/USD, etc.) |
| **🌤️ Utilities** | Weather, news, image generation, web search, translation |
| **🎮 Engagement** | Quiz system (multiple themes) + score tracking |
| **🛡️ Moderation** | Kick, ban, clear (groups) + audit logs |
| **⭐ Payments** | Telegram Stars integration (buy premium features) |
| **📊 Memory** | Full conversation history per user (SQLite) |
| **🧩 Rich UI** | Inline keyboards, command menus, quiz buttons |

---

## 📦 Installation

```bash
git clone https://github.com/BAKOME-Hub/BAKOME_Ultimate_Telegram_Bot.git
cd BAKOME_Ultimate_Telegram_Bot
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
python telegram_bot_ultimate.py
TELEGRAM_TOKEN=your_telegram_bot_token
GEMINI_API_KEY=your_google_gemini_key
DEEPSEEK_API_KEY=your_deepseek_key
OLLAMA_URL=http://localhost:11434
CLOUD_ENGINE=gemini
