#!/usr/bin/env python3
"""WoW Discord helper bot.

Provides slash and hybrid commands to fetch World of Warcraft guides,
Mythic+ routes, and raid boss information from YAML mapping files.

This module defines a `WoWBot` (a subclass of `commands.Bot`) and a
`WowHelper` cog which exposes the following commands:
- `/guide` - lookup class/spec guides from Wowhead and Icy Veins
- `/mplus` - show Mythic+ route link for a dungeon
- `/raid`  - show raid boss guide link

Configuration is read from environment variables (via `.env`), and
mapping files are expected in the `mappings/` directory next to this
script.
"""

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


# ---------- Data-Loader ----------
def safe_load_yaml(path: Path) -> dict:
    """Load a YAML file from ``path`` and return a dictionary.

    If the file does not exist or is empty, return an empty dictionary.

    Args:
        path: Path to the YAML file.

    Returns:
        A dict parsed from YAML or an empty dict on missing/empty file.
    """
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_guides(path: Path):
    """Load guide mappings from a YAML file and return two dicts.

    The YAML is expected to contain top-level mappings for 'wowhead' and
    'icy_veins'. Each of these should map class names to spec mappings.
    Returned dictionaries use ``(class, spec)`` tuples as keys (both
    lowercased) and the guide URL as the value.

    Args:
        path: Path to the guides YAML file.

    Returns:
        A tuple ``(wowhead, icy)`` where each element is a dict mapping
        ``(class, spec)`` -> url.
    """
    raw = safe_load_yaml(path)
    wowhead, icy = {}, {}
    for src, target in [("wowhead", wowhead), ("icy_veins", icy)]:
        for cls, specs in (raw.get(src, {}) or {}).items():
            for spec, url in (specs or {}).items():
                target[(cls.lower(), spec.lower())] = url
    return wowhead, icy


# ---------- Bot class ----------
class WoWBot(commands.Bot):
    """Discord bot implementation that loads mappings and registers cogs.

    The bot enables message content intents and uses a hybrid command
    prefix for compatibility with both text and slash commands.
    """

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        """Asynchronous setup hook used by discord.py to prepare the bot.

        Loads mapping files, registers the `WowHelper` cog and synchronizes
        application (slash) commands with Discord.
        """
        # Load mapping data
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
    """Cog providing commands and autocompletes for WoW resources.

    The `data` argument must contain the mappings prepared in ``setup_hook``:
    keys: 'wowhead', 'icy', 'mplus', 'raids'.
    """

    def __init__(self, bot, data):
        self.bot = bot
        self.data = data
        self.all_classes = sorted(list(set(k[0] for k in data["wowhead"].keys())))

    # --- Autocomplete Functions ---

    async def klasse_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete handler for class names.

        Filters available classes by the current input (case-insensitive)
        and returns up to 25 choices.
        """
        return [
            app_commands.Choice(name=cls.title(), value=cls)
            for cls in self.all_classes
            if current.lower() in cls.lower()
        ][:25]

    async def spec_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete handler for specialization names.

        Uses the selected class from the interaction namespace to limit
        available specs. Returns up to 25 choices filtered by `current`.
        """
        selected_class = interaction.namespace.klasse
        if not selected_class:
            return []
        available_specs = [
            k[1] for k in self.data["wowhead"].keys() if k[0] == selected_class.lower()
        ]
        return [
            app_commands.Choice(name=spec.title(), value=spec)
            for spec in sorted(available_specs)
            if current.lower() in spec.lower()
        ][:25]

    async def dungeon_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for Mythic+ dungeons by name or slug."""
        return [
            app_commands.Choice(name=d["name"], value=slug)
            for slug, d in self.data["mplus"].items()
            if current.lower() in d["name"].lower() or current.lower() in slug.lower()
        ][:25]

    async def raid_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for raid bosses by name or slug."""
        return [
            app_commands.Choice(name=b["name"], value=slug)
            for slug, b in self.data["raids"].items()
            if current.lower() in b["name"].lower() or current.lower() in slug.lower()
        ][:25]

    # --- Commands ---

    @commands.hybrid_command(
        name="guide", description="Zeigt WoW Guides für Klasse und Spec"
    )
    @app_commands.describe(
        klasse="Wähle deine Klasse", spec="Wähle deine Spezialisierung"
    )
    @app_commands.autocomplete(klasse=klasse_autocomplete, spec=spec_autocomplete)
    async def guide(self, ctx: commands.Context, klasse: str, spec: str):
        """Hybrid command to show guides for a given class and spec.

        Parameters reflect the user's chosen `klasse` and `spec` and the
        function will reply with links found in the loaded mappings. If no
        guide exists the user is informed.
        """
        k, s = klasse.lower(), spec.lower()
        key = (k, s)
        if key not in self.data["wowhead"] and key not in self.data["icy"]:
            await ctx.send(f"Kein Guide für {klasse} {spec} gefunden.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"Guides: {k.title()} {s.title()}", color=discord.Color.blue()
        )
        if key in self.data["wowhead"]:
            embed.add_field(
                name="Wowhead",
                value=f"[Zum Guide]({self.data['wowhead'][key]})",
                inline=False,
            )
        if key in self.data["icy"]:
            embed.add_field(
                name="Icy Veins",
                value=f"[Zum Guide]({self.data['icy'][key]})",
                inline=False,
            )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="mplus", description="Zeigt die M+ Route für einen Dungeon"
    )
    @app_commands.describe(dungeon="Wähle den Dungeon")
    @app_commands.autocomplete(dungeon=dungeon_autocomplete)
    async def mplus(self, ctx: commands.Context, dungeon: str):
        """Show Mythic+ route link for the requested dungeon.

        If the dungeon slug or name is not known, the user receives an
        ephemeral error message.
        """
        d_data = self.data["mplus"].get(dungeon.lower())
        if not d_data:
            await ctx.send(f"Dungeon `{dungeon}` nicht gefunden.", ephemeral=True)
            return
        embed = discord.Embed(
            title=f"M+ Route: {d_data['name']}", color=discord.Color.green()
        )
        embed.add_field(name="Route Link", value=f"[Hier klicken]({d_data['url']})")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="raid", description="Zeigt Boss-Infos aus dem Raid")
    @app_commands.describe(boss="Wähle den Boss")
    @app_commands.autocomplete(boss=raid_autocomplete)
    async def raid(self, ctx: commands.Context, boss: str):
        """Show raid boss information and a guide link for the chosen boss.

        If the boss is unknown the user receives an ephemeral error message.
        """
        b_data = self.data["raids"].get(boss.lower())
        if not b_data:
            await ctx.send(f"Boss `{boss}` nicht gefunden.", ephemeral=True)
            return
        embed = discord.Embed(
            title=f"Raid Boss: {b_data['name']}", color=discord.Color.red()
        )
        embed.add_field(
            name="Guide Link", value=f"[MythicTrap / Guide]({b_data['url']})"
        )
        await ctx.send(embed=embed)


async def main():
    """Create and run the WoW bot using the configured token."""
    bot = WoWBot()
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
