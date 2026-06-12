#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import os
import sqlite3
import uuid
from datetime import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.environ.get("PORT", 10000))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN обязателен")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ==================== БАЗА ДАННЫХ ====================
db_lock = asyncio.Lock()

def init_db():
    with sqlite3.connect("users.db", timeout=30) as conn:
        c = conn.cursor()
        c.execute("PRAGMA journal_mode=WAL;")
        c.execute("PRAGMA synchronous=NORMAL;")
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            uuid TEXT NOT NULL,
            created_at TIMESTAMP
        )''')
        conn.commit()

init_db()

# ==================== ГОТОВАЯ КОНФИГУРАЦИЯ СЕРВЕРА ====================
# Сервер уже развёрнут на Render, можно использовать
SERVER = {
    "name": "Render VLESS (Frankfurt)",
    "address": "vless-frankfurt.onrender.com",
    "port": "443",
    "encryption": "none",
    "security": "tls",
    "type": "ws",
    "path": "/ws-secret-path",
    "fingerprint": "chrome"
}

def get_server_keyboard():
    buttons = [[InlineKeyboardButton(text=SERVER["name"], callback_data="get_config")]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def generate_vless_link(uuid_str):
    return f"vless://{uuid_str}@{SERVER['address']}:{SERVER['port']}?encryption={SERVER['encryption']}&security={SERVER['security']}&sni={SERVER['address']}&fp={SERVER['fingerprint']}&type={SERVER['type']}&path={SERVER['path']}#{SERVER['name']}"

def generate_config_text(uuid_str):
    return f"""
╔══════════════════════════════════════╗
║ {SERVER['name']}
╠══════════════════════════════════════╣
║ Протокол: VLESS
║ Адрес: {SERVER['address']}
║ Порт: {SERVER['port']}
║ UUID: {uuid_str}
║ Шифрование: {SERVER['encryption']}
║ Транспорт: {SERVER['type']}
║ Путь: {SERVER['path']}
║ TLS: включён
║ SNI: {SERVER['address']}
║ Fingerprint: {SERVER['fingerprint']}
╚══════════════════════════════════════╝
"""

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    async with db_lock:
        with sqlite3.connect("users.db", timeout=30) as conn:
            c = conn.cursor()
            c.execute("SELECT uuid FROM users WHERE user_id = ?", (user_id,))
            row = c.fetchone()
            if row is None:
                new_uuid = str(uuid.uuid4())
                c.execute("INSERT INTO users (user_id, uuid, created_at) VALUES (?, ?, ?)",
                          (user_id, new_uuid, datetime.now()))
                conn.commit()
                uuid_str = new_uuid
            else:
                uuid_str = row[0]
    await message.answer(
        f"🔐 *Ваш персональный UUID:*\n`{uuid_str}`\n\n"
        f"Нажмите кнопку, чтобы получить конфигурацию:",
        reply_markup=get_server_keyboard(),
        parse_mode="Markdown"
    )

@dp.callback_query()
async def handle_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data

    if data == "get_config":
        async with db_lock:
            with sqlite3.connect("users.db", timeout=30) as conn:
                c = conn.cursor()
                c.execute("SELECT uuid FROM users WHERE user_id = ?", (user_id,))
                row = c.fetchone()
                uuid_str = row[0] if row else str(uuid.uuid4())
        link = generate_vless_link(uuid_str)
        text_config = generate_config_text(uuid_str)
        await callback.message.edit_text(
            f"{text_config}\n\n"
            f"🔗 *Ссылка для быстрого импорта:*\n"
            f"`{link}`\n\n"
            f"📱 *Как использовать:*\n"
            f"1. Скопируйте ссылку\n"
            f"2. В v2rayNG / Nekoray нажмите + → Import from Clipboard\n"
            f"3. Подключитесь",
            parse_mode="Markdown"
        )
        await callback.answer()
        return

# ==================== HEALTH CHECK ====================
async def handle_health(reader, writer):
    writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")
    await writer.drain()
    writer.close()

async def start_web_server():
    server = await asyncio.start_server(handle_health, "0.0.0.0", PORT)
    print(f"Health check server listening on 0.0.0.0:{PORT}")
    asyncio.create_task(server.serve_forever())

async def main():
    print("=== MAIN START ===")
    print(f"PORT = {PORT}")
    await start_web_server()
    await asyncio.sleep(2)
    print("🚀 Bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
