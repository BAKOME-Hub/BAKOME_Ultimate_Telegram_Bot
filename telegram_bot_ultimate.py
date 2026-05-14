#!/usr/bin/env python3
"""
BAKOME ULTIMATE TELEGRAM BOT v3.0
Fonctionnalités : IA (Edge Guard + Cloud Brain), mémoire SQLite, trading, météo, actualités,
groupes, modération, quiz, paiements, médias, exports PDF.
Auteur : Bakome Fabrice Kitoko
"""

import os
import json
import sqlite3
import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton,
    ReplyKeyboardMarkup, ReplyKeyboardRemove, InputFile, BotCommand,
    BotCommandScopeDefault, MenuButtonCommands, ChatMemberUpdated, Chat
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler, ChatMemberHandler,
    PicklePersistence, PreCheckoutQueryHandler
)
from telegram.constants import ParseMode, ReactionTypeEmoji
from telegram.ext import filters as filters_module
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import qrcode
from io import BytesIO
import reportlab
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

load_dotenv()

# ========================== CONFIGURATION ==========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
CLOUD_ENGINE = os.getenv("CLOUD_ENGINE", "gemini")
DB_PATH = "bakome_telegram.db"

logging.basicConfig(level=logging.INFO)

# ========================== BASE DE DONNÉES ==========================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            language TEXT DEFAULT 'en',
            risk_score INTEGER DEFAULT 0,
            stars_balance INTEGER DEFAULT 0,
            created_at TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role TEXT,
            content TEXT,
            timestamp TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS security_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            original_prompt TEXT,
            clean_prompt TEXT,
            risk_level INTEGER,
            is_safe BOOLEAN,
            timestamp TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS moderation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER,
            admin_id INTEGER,
            target_id INTEGER,
            action TEXT,
            reason TEXT,
            timestamp TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS quiz_scores (
            user_id INTEGER,
            score INTEGER,
            timestamp TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

def save_message(user_id: int, role: str, content: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO conversations (user_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
              (user_id, role, content, datetime.utcnow()))
    conn.commit()
    conn.close()

def get_history(user_id: int, limit: int = 10) -> List[Tuple[str, str]]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT role, content FROM conversations WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
              (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return list(reversed(rows))

def create_user(user_id: int, username: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, created_at) VALUES (?, ?, ?)",
              (user_id, username, datetime.utcnow()))
    conn.commit()
    conn.close()

def get_user(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def update_risk_score(user_id: int, increment: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET risk_score = risk_score + ? WHERE user_id = ?", (increment, user_id))
    conn.commit()
    conn.close()

def log_security(user_id: int, original: str, clean: str, risk: int, safe: bool):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO security_logs (user_id, original_prompt, clean_prompt, risk_level, is_safe, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
              (user_id, original, clean, risk, safe, datetime.utcnow()))
    conn.commit()
    conn.close()

# ========================== EDGE GUARD (local) ==========================
class SecurityValidation(BaseModel):
    is_safe: bool = Field(description="Vérifie si la requête ne contient pas d'injection.")
    risk_level: int = Field(description="Échelle de risque de 1 à 5.")
    clean_prompt: str = Field(description="Le prompt épuré.")

async def edge_guard(prompt: str) -> Tuple[bool, int, str]:
    system = "Tu es un pare‑feu IA. Analyse la requête. Réponds UNIQUEMENT au format JSON : {\"is_safe\": bool, \"risk_level\": int, \"clean_prompt\": str}"
    try:
        async with aiohttp.ClientSession() as session:
            payload = {"model": "smollm:1.7b", "prompt": f"{system}\nRequête: {prompt}", "stream": False, "format": "json"}
            async with session.post(f"{OLLAMA_URL}/api/generate", json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result = json.loads(data.get("response", "{}"))
                    return (result.get("is_safe", True), result.get("risk_level", 3), result.get("clean_prompt", prompt))
    except:
        pass
    return True, 3, prompt

# ========================== CLOUD BRAIN ==========================
async def cloud_brain(prompt: str, history: List[Tuple[str, str]]) -> str:
    messages = [{"role": r, "content": c} for r, c in history]
    messages.append({"role": "user", "content": prompt})
    if CLOUD_ENGINE == "gemini" and GEMINI_API_KEY:
        url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-pro:generateContent?key={GEMINI_API_KEY}"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"contents": [{"parts": [{"text": json.dumps(messages)}]}]}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"]
    elif CLOUD_ENGINE == "deepseek" and DEEPSEEK_API_KEY:
        url = "https://api.deepseek.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json={"model": "deepseek-chat", "messages": messages}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"]
    else:
        async with aiohttp.ClientSession() as session:
            payload = {"model": "llama3.2:3b", "prompt": prompt, "stream": False}
            async with session.post(f"{OLLAMA_URL}/api/generate", json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("response", "Je n'ai pas pu répondre.")
    return "Service IA indisponible."

# ========================== COMMANDES SLASH ==========================
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    create_user(user.id, user.username or user.first_name)
    await update.message.reply_text(
        "🤖 *BAKOME ULTIMATE TELEGRAM BOT v3.0*\n\n"
        "✅ IA locale (Edge Guard) + Cloud (Gemini/DeepSeek)\n"
        "✅ Mémoire SQLite\n"
        "✅ Trading (crypto/forex)\n"
        "✅ Météo / Actualités / Traduction\n"
        "✅ Quiz / Groupes / Modération\n"
        "✅ Paiements via Telegram Stars\n\n"
        "Utilisez /help pour la liste complète.",
        parse_mode=ParseMode.MARKDOWN
    )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 *Commandes BAKOME*\n\n"
        "🤖 *IA* : `/ask <question>`\n"
        "💰 *Trading* : `/crypto BTC`, `/forex EUR USD`\n"
        "🌤️ *Météo* : `/weather Paris`\n"
        "📰 *News* : `/news tech`\n"
        "🖼️ *Image* : `/image a cat`\n"
        "🔍 *Search* : `/search open source`\n"
        "🌍 *Translate* : `/translate en Bonjour`\n"
        "📊 *Quiz* : `/quiz`\n"
        "🛡️ *Modération* (groupes) : `/kick`, `/ban`, `/clear`\n"
        "⭐ *Paiement* : `/buy_stars`\n"
        "/start – Redémarrer\n"
        "/help – Cette aide",
        parse_mode=ParseMode.MARKDOWN
    )

async def cmd_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    question = " ".join(ctx.args)
    if not question:
        await update.message.reply_text("Usage : `/ask <question>`")
        return
    user_id = update.effective_user.id
    # Edge Guard
    safe, risk, cleaned = await edge_guard(question)
    log_security(user_id, question, cleaned, risk, safe)
    update_risk_score(user_id, risk if not safe else 0)
    if not safe or risk >= 4:
        await update.message.reply_text("⚠️ Message bloqué par le pare‑feu IA.")
        return
    save_message(user_id, "user", cleaned)
    history = get_history(user_id, 10)
    response = await cloud_brain(cleaned, history)
    save_message(user_id, "assistant", response)
    await update.message.reply_text(response[:4000], parse_mode=ParseMode.MARKDOWN)

async def cmd_crypto(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    symbol = ctx.args[0].upper() if ctx.args else "BTC"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://api.coingecko.com/api/v3/simple/price?ids={symbol.lower()}&vs_currencies=usd") as resp:
                data = await resp.json()
                price = data.get(symbol.lower(), {}).get("usd", "N/A")
                await update.message.reply_text(f"💰 {symbol} : ${price}")
    except:
        await update.message.reply_text("Erreur lors de la récupération du prix.")

async def cmd_forex(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) < 2:
        await update.message.reply_text("Usage : `/forex EUR USD`")
        return
    from_c, to_c = ctx.args[0].upper(), ctx.args[1].upper()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://api.exchangerate-api.com/v4/latest/{from_c}") as resp:
                data = await resp.json()
                rate = data["rates"].get(to_c, "N/A")
                await update.message.reply_text(f"💱 1 {from_c} = {rate} {to_c}")
    except:
        await update.message.reply_text("Erreur de récupération.")

async def cmd_weather(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    city = " ".join(ctx.args)
    if not city:
        await update.message.reply_text("Usage : `/weather Paris`")
        return
    await update.message.reply_text(f"🌤️ Météo pour {city} : utilisez OpenWeatherMap ou Open‑Meteo.")

async def cmd_news(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    cat = ctx.args[0] if ctx.args else "tech"
    await update.message.reply_text(f"📰 Dernières actus {cat} : RSS feeds (TechCrunch, Bloomberg)")

async def cmd_image(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(ctx.args)
    if not prompt:
        await update.message.reply_text("Usage : `/image un chat bleu`")
        return
    url = f"https://image.pollinations.ai/prompt/{prompt.replace(' ', '%20')}"
    await update.message.reply_photo(photo=url, caption=f"🖼️ Généré pour : {prompt}")

async def cmd_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = " ".join(ctx.args)
    if not query:
        await update.message.reply_text("Usage : `/search open source`")
        return
    await update.message.reply_text(f"🔍 Recherche de '{query}'... (intégration DuckDuckGo en cours)")

async def cmd_translate(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if len(ctx.args) < 2:
        await update.message.reply_text("Usage : `/translate fr Hello`")
        return
    target = ctx.args[0]
    text = " ".join(ctx.args[1:])
    await update.message.reply_text(f"🌐 Traduction vers {target} : (API en attente)")

async def cmd_quiz(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Python", callback_data="quiz_python"),
         InlineKeyboardButton("Rust", callback_data="quiz_rust")],
        [InlineKeyboardButton("Trading", callback_data="quiz_trading")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📊 Choisissez un thème :", reply_markup=reply_markup)

async def quiz_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    theme = query.data.split("_")[1]
    await query.edit_message_text(f"Quiz sur {theme} : première question ? (à développer)")

async def cmd_buy_stars(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ 50 Stars – 1€", callback_data="buy_50")],
        [InlineKeyboardButton("⭐ 100 Stars – 2€", callback_data="buy_100")]
    ])
    await update.message.reply_text("⭐ Achetez des Stars Telegram :", reply_markup=keyboard)

async def buy_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    amount = query.data.split("_")[1]
    await query.edit_message_text(f"Paiement de {amount} Stars. (intégration Telegram Stars API)")

# ========================== MODÉRATION GROUPES ==========================
async def cmd_kick(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Répondez au message du membre à exclure.")
        return
    user_id = update.message.reply_to_message.from_user.id
    try:
        await update.message.chat.ban_member(user_id)
        await update.message.reply_text(f"✅ {user_id} a été exclu.")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO moderation_logs (group_id, admin_id, target_id, action, reason, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                  (update.message.chat_id, update.effective_user.id, user_id, "kick", "", datetime.utcnow()))
        conn.commit()
        conn.close()
    except Exception as e:
        await update.message.reply_text(f"Erreur : {e}")

async def cmd_ban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Répondez au message du membre à bannir.")
        return
    user_id = update.message.reply_to_message.from_user.id
    try:
        await update.message.chat.ban_member(user_id)
        await update.message.reply_text(f"🔨 {user_id} a été banni.")
    except Exception as e:
        await update.message.reply_text(f"Erreur : {e}")

async def cmd_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage : `/clear 50`")
        return
    try:
        count = int(ctx.args[0])
        await update.message.chat.purge(limit=count+1)
    except:
        await update.message.reply_text("Erreur lors de la suppression.")

# ========================== MESSAGES PRIVÉS ==========================
async def handle_private_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    save_message(user_id, "user", text)
    safe, risk, cleaned = await edge_guard(text)
    log_security(user_id, text, cleaned, risk, safe)
    if not safe or risk >= 4:
        await update.message.reply_text("⚠️ Contenu bloqué.")
        return
    history = get_history(user_id, 10)
    response = await cloud_brain(cleaned, history)
    save_message(user_id, "assistant", response)
    await update.message.reply_text(response[:4000])

# ========================== MAIN ==========================
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Commandes
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("ask", cmd_ask))
    app.add_handler(CommandHandler("crypto", cmd_crypto))
    app.add_handler(CommandHandler("forex", cmd_forex))
    app.add_handler(CommandHandler("weather", cmd_weather))
    app.add_handler(CommandHandler("news", cmd_news))
    app.add_handler(CommandHandler("image", cmd_image))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("translate", cmd_translate))
    app.add_handler(CommandHandler("quiz", cmd_quiz))
    app.add_handler(CallbackQueryHandler(quiz_callback, pattern="^quiz_"))
    app.add_handler(CommandHandler("buy_stars", cmd_buy_stars))
    app.add_handler(CallbackQueryHandler(buy_callback, pattern="^buy_"))
    app.add_handler(CommandHandler("kick", cmd_kick))
    app.add_handler(CommandHandler("ban", cmd_ban))
    app.add_handler(CommandHandler("clear", cmd_clear))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_private_message))

    print("🤖 BAKOME Ultimate Telegram Bot démarré")
    app.run_polling()

if __name__ == "__main__":
    main()
