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
        # Der Bot reagiert auf !
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

        # WICHTIG: Erzwingt das Update der / Befehle bei Discord
        logger.info("Synchronisiere Slash-Commands mit Discord...")
        await self.tree.sync()
        logger.info("Synchronisierung fertig!")


class WowHelper(commands.Cog):
    def __init__(self, bot, data):
        self.bot = bot
        self.data = data
        # Erstellt eine Liste aller verfügbaren Klassen für das erste Feld
        self.all_classes = sorted(list(set(k[0] for k in data["wowhead"].keys())))

    # --- Autocomplete Funktionen ---

    async def klasse_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=cls.title(), value=cls)
            for cls in self.all_classes
            if current.lower() in cls.lower()
        ][:25]  # Discord erlaubt maximal 25 Vorschläge

    async def spec_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        # Holt die bereits gewählte Klasse aus dem anderen Feld
        selected_class = interaction.namespace.klasse
        if not selected_class:
            return []

        # Findet alle Specs, die zu dieser Klasse in den Daten existieren
        available_specs = [
            k[1] for k in self.data["wowhead"].keys() if k[0] == selected_class.lower()
        ]

        return [
            app_commands.Choice(name=spec.title(), value=spec)
            for spec in sorted(available_specs)
            if current.lower() in spec.lower()
        ][:25]

    # --- Der Command mit Autocomplete-Verknüpfung ---

    @commands.hybrid_command(
        name="guide", description="Zeigt WoW Guides für Klasse und Spec"
    )
    @app_commands.describe(
        klasse="Wähle deine Klasse", spec="Wähle deine Spezialisierung"
    )
    @app_commands.autocomplete(klasse=klasse_autocomplete, spec=spec_autocomplete)
    async def guide(self, ctx: commands.Context, klasse: str, spec: str):
        k, s = klasse.lower(), spec.lower()
        key = (k, s)

        # Check ob Daten existieren
        if key not in self.data["wowhead"] and key not in self.data["icy"]:
            await ctx.send(f"Kein Guide für {klasse} {spec} gefunden.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"Guides: {k.title()} {s.title()}",
            color=discord.Color.blue(),
            description="Hier sind die aktuellsten Guides für deine Wahl:",
        )

        if key in self.data["wowhead"]:
            embed.add_field(
                name="Wowhead",
                value=f"[Zum Wowhead Guide]({self.data['wowhead'][key]})",
                inline=False,
            )
        if key in self.data["icy"]:
            embed.add_field(
                name="Icy Veins",
                value=f"[Zum Icy Veins Guide]({self.data['icy'][key]})",
                inline=False,
            )

        await ctx.send(embed=embed)


async def main():
    bot = WoWBot()
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
