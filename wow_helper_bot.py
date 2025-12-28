#!/usr/bin/env python3
import os
import logging
import asyncio
from pathlib import Path

import discord
from discord.ext import commands
from discord import app_commands
import yaml
from dotenv import load_dotenv

# Konfiguration
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
logger = logging.getLogger("wow-bot")

BASE_DIR = Path(__file__).parent
MAPPINGS_DIR = BASE_DIR / "mappings"


# ---------- Daten-Loader ----------
def safe_load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
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
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Daten laden
        wh, iv = load_guides(MAPPINGS_DIR / "guides.yaml")
        data = {
            "wowhead": wh,
            "icy": iv,
            "mplus": safe_load_yaml(MAPPINGS_DIR / "mplus.yaml").get("dungeons", {}),
            "raids": safe_load_yaml(MAPPINGS_DIR / "raid.yaml").get("bosses", {}),
        }
        await self.add_cog(WowHelper(self, data))

        logger.info("Synchronisiere Slash-Commands mit Discord...")
        await self.tree.sync()
        logger.info("Synchronisierung fertig!")


class WowHelper(commands.Cog):
    def __init__(self, bot, data):
        self.bot = bot
        self.data = data
        self.all_classes = sorted(list(set(k[0] for k in data["wowhead"].keys())))

    # --- Autocomplete Funktionen ---

    async def klasse_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=cls.title(), value=cls)
            for cls in self.all_classes if current.lower() in cls.lower()
        ][:25]

    async def spec_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        selected_class = interaction.namespace.klasse
        if not selected_class:
            return []
        available_specs = [k[1] for k in self.data["wowhead"].keys() if k[0] == selected_class.lower()]
        return [
            app_commands.Choice(name=spec.title(), value=spec)
            for spec in sorted(available_specs) if current.lower() in spec.lower()
        ][:25]

    async def dungeon_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=d["name"], value=slug)
            for slug, d in self.data["mplus"].items()
            if current.lower() in d["name"].lower() or current.lower() in slug.lower()
        ][:25]

    async def raid_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=b["name"], value=slug)
            for slug, b in self.data["raids"].items()
            if current.lower() in b["name"].lower() or current.lower() in slug.lower()
        ][:25]

    # --- Commands ---

    @commands.hybrid_command(name="guide", description="Zeigt WoW Guides für Klasse und Spec")
    @app_commands.describe(klasse="Wähle deine Klasse", spec="Wähle deine Spezialisierung")
    @app_commands.autocomplete(klasse=klasse_autocomplete, spec=spec_autocomplete)
    async def guide(self, ctx: commands.Context, klasse: str, spec: str):
        k, s = klasse.lower(), spec.lower()
        key = (k, s)
        if key not in self.data["wowhead"] and key not in self.data["icy"]:
            await ctx.send(f"Kein Guide für {klasse} {spec} gefunden.", ephemeral=True)
            return

        embed = discord.Embed(title=f"Guides: {k.title()} {s.title()}", color=discord.Color.blue())
        if key in self.data["wowhead"]:
            embed.add_field(name="Wowhead", value=f"[Zum Guide]({self.data['wowhead'][key]})", inline=False)
        if key in self.data["icy"]:
            embed.add_field(name="Icy Veins", value=f"[Zum Guide]({self.data['icy'][key]})", inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="mplus", description="Zeigt die M+ Route für einen Dungeon")
    @app_commands.describe(dungeon="Wähle den Dungeon")
    @app_commands.autocomplete(dungeon=dungeon_autocomplete)
    async def mplus(self, ctx: commands.Context, dungeon: str):
        d_data = self.data["mplus"].get(dungeon.lower())
        if not d_data:
            await ctx.send(f"Dungeon `{dungeon}` nicht gefunden.", ephemeral=True)
            return
        embed = discord.Embed(title=f"M+ Route: {d_data['name']}", color=discord.Color.green())
        embed.add_field(name="Route Link", value=f"[Hier klicken]({d_data['url']})")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="raid", description="Zeigt Boss-Infos aus dem Raid")
    @app_commands.describe(boss="Wähle den Boss")
    @app_commands.autocomplete(boss=raid_autocomplete)
    async def raid(self, ctx: commands.Context, boss: str):
        b_data = self.data["raids"].get(boss.lower())
        if not b_data:
            await ctx.send(f"Boss `{boss}` nicht gefunden.", ephemeral=True)
            return
        embed = discord.Embed(title=f"Raid Boss: {b_data['name']}", color=discord.Color.red())
        embed.add_field(name="Guide Link", value=f"[MythicTrap / Guide]({b_data['url']})")
        await ctx.send(embed=embed)


async def main():
    bot = WoWBot()
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())