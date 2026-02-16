import discord
from discord.ext import tasks
import json
import os
import aiosqlite
import asyncio
from datetime import datetime, timedelta

# Charger config
with open("config.json") as f:
    config = json.load(f)

TOKEN = os.getenv("DISCORD_TOKEN") or config["token"]
salons_vocaux = config["salons_vocaux"]
salons_blacklist = config["salons_blacklist_texte"]
temps_message = config["temps_message"]  # 2m50 = 170s
plafond_texte = config["plafond_texte_pour_contrat"]

intents = discord.Intents.default()
intents.members = True
intents.messages = True
intents.guilds = True
intents.voice_states = True
intents.message_content = True

bot = discord.Client(intents=intents)

# Base de données
DB_FILE = "database.sqlite"

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                name TEXT,
                regiment TEXT,
                grade TEXT,
                vocal_total INTEGER DEFAULT 0,
                text_total INTEGER DEFAULT 0
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                type TEXT,
                start TIMESTAMP,
                end TIMESTAMP,
                validated INTEGER DEFAULT 1
            )
        ''')
        await db.commit()

# Gérer temps vocal
vocal_sessions = {}

@bot.event
async def on_ready():
    print(f'{bot.user} connecté')
    await init_db()

@bot.event
async def on_voice_state_update(member, before, after):
    if after.channel and after.channel.name in salons_vocaux and not after.self_mute:
        # Début session vocal
        vocal_sessions[member.id] = datetime.utcnow()
    elif before.channel and member.id in vocal_sessions:
        # Fin session vocal
        start = vocal_sessions.pop(member.id)
        delta = (datetime.utcnow() - start).total_seconds() / 60  # minutes
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute('INSERT INTO sessions(user_id, type, start, end) VALUES (?,?,?,?)',
                             (member.id, "vocal", start, datetime.utcnow()))
            await db.execute('UPDATE users SET vocal_total = vocal_total + ? WHERE id = ?',
                             (int(delta), member.id))
            await db.commit()

# Gérer activité texte
text_timers = {}

@bot.event
async def on_message(message):
    if message.author.bot: 
        return
    if message.channel.name in salons_blacklist:
        return
    if len(message.content) < 15:
        return

    user_id = message.author.id

    # Timer reset
    if user_id in text_timers:
        text_timers[user_id].cancel()

    async def add_text_time():
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute('UPDATE users SET text_total = text_total + ? WHERE id = ?',
                             (int(temps_message/60), user_id))
            await db.commit()

    text_timers[user_id] = bot.loop.call_later(temps_message, asyncio.create_task, add_text_time())

bot.run(TOKEN)
