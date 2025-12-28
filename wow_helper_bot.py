#!/usr/bin/env python3
import os
import logging
import asyncio
from pathlib import Path
from typing import Dict, Tuple, Optional

import discord
from discord.ext import commands
from discord import app_commands
import yaml
from dotenv import load_dotenv

# Konfiguration
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s')
logger = logging.getLogger("wow-bot")

BASE_DIR = Path(__file__).parent
MAPPINGS_DIR = BASE_DIR / "mappings"

# ---------- Daten-Loader ----------
def safe_load_yaml(path: Path) -> dict:
    if not path.exists(): return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def load_guides(path: Path):
    raw = safe_load_yaml(path)
    wowhead, icy = {}, {}
    for src, target in [("wowhead", wowhead), ("icy_veins", icy)]:
        for cls, specs in (raw.get(src, {}) or {}).items():
            for spec, url in (specs or {}).items():
                target[(cls.lower(), spec.lower())] = url
    return wowhead, icy

# ---------- Bot Klasse ----------
class WoWBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True 
        # Der Bot reagiert auf !
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Daten laden
        wh, iv = load_guides(MAPPINGS_DIR / "guides.yaml")
        data = {
            'wowhead': wh, 'icy': iv,
            'mplus': safe_load_yaml(MAPPINGS_DIR / "mplus.yaml").get("dungeons", {}),
            'raids': safe_load_yaml(MAPPINGS_DIR / "raid.yaml").get("bosses", {})
        }
        await self.add_cog(WowHelper(self, data))
        
        # WICHTIG: Erzwingt das Update der / Befehle bei Discord
        logger.info("Synchronisiere Slash-Commands mit Discord...")
        await self.tree.sync()
        logger.info("Synchronisierung fertig!")

class WowHelper(commands.Cog):
    def __init__(self, bot, data):
        self.bot = bot
        self.data = data
        self.guide_keys = set(list(data['wowhead'].keys()) + list(data['icy'].keys()))

    # Dieser Befehl funktioniert als /guide UND als !guide
    @commands.hybrid_command(name="guide", description="Zeigt WoW Guides für Klasse und Spec")
    @app_commands.describe(klasse="z.B. warrior", spec="z.B. fury")
    async def guide(self, ctx: commands.Context, klasse: str, spec: str):
        k, s = klasse.lower(), spec.lower()
        if (k, s) not in self.guide_keys:
            await ctx.send(f"Kein Guide für {klasse} {spec} gefunden.", ephemeral=True)
            return

        embed = discord.Embed(title=f"Guides: {k.title()} {s.title()}", color=discord.Color.blue())
        if (k, s) in self.data['wowhead']: embed.add_field(name="Wowhead", value=self.data['wowhead'][(k, s)], inline=False)
        if (k, s) in self.data['icy']: embed.add_field(name="Icy Veins", value=self.data['icy'][(k, s)], inline=False)
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot: return
        # Auto-Erkennung für normale Nachrichten (ohne !)
        if not message.content.startswith("!"):
            text = message.content.lower()
            for (cls, spec) in self.guide_keys:
                if f"{spec} {cls}" in text or f"{cls} {spec}" in text:
                    # Hier rufen wir die Logik manuell auf oder senden kurze Info
                    await message.reply(f"Meintest du den Guide für **{cls.title()} {spec.title()}**? Nutze `/guide {cls} {spec}`")
                    break

async def main():
    bot = WoWBot()
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
