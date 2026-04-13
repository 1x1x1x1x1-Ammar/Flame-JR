import discord
import os
from flask import Flask
from threading import Thread

# ====== KEEP ALIVE SERVER ======
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive"

def run():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ====== DISCORD BOT ======
intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content == "!ping":
        await message.channel.send("Pong!")

keep_alive()

client.run(os.getenv("DISCORD_TOKEN"))
