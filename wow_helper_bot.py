# ...existing code...
#!/usr/bin/env python3
"""WoW Discord helper bot.

Provides slash and hybrid commands to fetch World of Warcraft guides,
Mythic+ routes, and raid boss information from YAML mapping files.

This module defines a `WoWBot` (a subclass of `commands.Bot`) and a
`WowHelper` cog which exposes the following commands:
- `/guide` - lookup class/spec guides from Wowhead and Icy Veins
- `/mplus` - show Mythic+ route link for a dungeon or show classes from murloc
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
        mplus_routes = safe_load_yaml(MAPPINGS_DIR / "mplus-routes.yaml").get(
            "dungeons", {}
        )
        murloc_raw = safe_load_yaml(MAPPINGS_DIR / "murloc.yaml")
        if isinstance(murloc_raw, dict):
            if "classes" in murloc_raw:
                murloc = murloc_raw["classes"]
            elif "mplus_class_guides" in murloc_raw:
                murloc = murloc_raw["mplus_class_guides"]
            else:
                murloc = murloc_raw
        else:
            murloc = {}

        data = {
            "wowhead": wh,
            "icy": iv,
            "mplus_routes": mplus_routes,
            "murloc": murloc,
            "raids": safe_load_yaml(MAPPINGS_DIR / "raid.yaml").get("bosses", {}),
        }
        await self.add_cog(WowHelper(self, data))

        logger.info("Synchronisiere Slash-Commands mit Discord...")
        await self.tree.sync()
        logger.info("Synchronisierung fertig!")


class WowHelper(commands.Cog):
    """Cog providing commands and autocompletes for WoW resources.

    The `data` argument must contain the mappings prepared in ``setup_hook``:
    keys: 'wowhead', 'icy', 'mplus_routes', 'murloc', 'raids'.
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
        """Autocomplete for Mythic+ dungeons by name or slug (legacy)."""
        return [
            app_commands.Choice(name=d["name"], value=slug)
            for slug, d in self.data["mplus_routes"].items()
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

    async def murloc_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for murloc classes or entries by name or slug."""
        m = self.data.get("murloc", {}) or {}
        choices = []
        for slug, val in m.items():
            if isinstance(val, dict):
                name = val.get("name") or slug.replace("_", " ").title()
            else:
                name = str(val)
            if current.lower() in name.lower() or current.lower() in slug.lower():
                choices.append(app_commands.Choice(name=name, value=slug))
        return choices[:25]

    async def mplus_item_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for the second parameter of /mplus.

        Determines which mapping to search based on the selected `source`
        (may be a plain string or app_commands.Choice in different contexts).
        """
        source = getattr(interaction.namespace, "source", None)
        # normalize source to plain string (handle Choice or None)
        if isinstance(source, app_commands.Choice):
            src = source.value
        else:
            src = str(source) if source is not None else ""

        if src == "routes":
            return [
                app_commands.Choice(name=d.get("name", slug), value=slug)
                for slug, d in self.data.get("mplus_routes", {}).items()
                if current.lower() in (d.get("name", "") or slug).lower()
                or current.lower() in slug.lower()
            ][:25]
        if src == "murloc":
            return await self.murloc_autocomplete(interaction, current)
        return []

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
        name="mplus", description="Zeigt M+ Routes oder Murloc Klassen"
    )
    @app_commands.describe(
        source="Wähle 'routes' oder 'murloc'", item="Route oder Klasse"
    )
    @app_commands.choices(
        source=[
            app_commands.Choice(name="Routes (mplus-routes.yaml)", value="routes"),
            app_commands.Choice(name="Murloc Classes (murloc.yaml)", value="murloc"),
        ]
    )
    @app_commands.autocomplete(item=mplus_item_autocomplete)
    async def mplus(self, ctx: commands.Context, source: str, item: str):
        """Show either a Mythic+ route (from mplus-routes.yaml) or a Murloc class entry.

        /mplus asks for a source (routes or murloc) and then an item selected
        from an autocomplete list for that source.
        """
        src = str(source)

        if src == "routes":
            # item is expected to be the dungeon slug (e.g. 'hoa'); try both raw and lowercased
            d_data = self.data.get("mplus_routes", {}).get(item) or self.data.get(
                "mplus_routes", {}
            ).get((item or "").lower())
            if not d_data:
                await ctx.send(f"Dungeon `{item}` nicht gefunden.", ephemeral=True)
                return
            embed = discord.Embed(
                title=f"M+ Route: {d_data.get('name', item)}",
                color=discord.Color.green(),
            )
            embed.add_field(
                name="Route Link", value=f"[Hier klicken]({d_data.get('url', '')})"
            )
            await ctx.send(embed=embed)
            return

        if src == "murloc":
            c_data = self.data.get("murloc", {}).get(item) or self.data.get(
                "murloc", {}
            ).get((item or "").lower())
            if not c_data:
                await ctx.send(f"Eintrag `{item}` nicht gefunden.", ephemeral=True)
                return

            if isinstance(c_data, dict):
                # If values are URLs (spec -> url), list them
                if any(
                    isinstance(v, str) and v.startswith("http") for v in c_data.values()
                ):
                    embed = discord.Embed(
                        title=f"Class Guides: {item.replace('_', ' ').title()}",
                        color=discord.Color.teal(),
                    )
                    for spec, url in sorted(c_data.items()):
                        if isinstance(url, str) and url.startswith("http"):
                            embed.add_field(
                                name=spec.title(), value=f"[Guide]({url})", inline=False
                            )
                    await ctx.send(embed=embed)
                    return

                # Fallback: dict with 'name'/'url'
                name = c_data.get("name", item.replace("_", " ").title())
                url = c_data.get("url")
                embed = discord.Embed(
                    title=f"Murloc: {name}", color=discord.Color.teal()
                )
                if url:
                    embed.add_field(name="Link", value=f"[Hier klicken]({url})")
                await ctx.send(embed=embed)
                return

            # Simple string entry
            name = str(c_data)
            embed = discord.Embed(title=f"Murloc: {name}", color=discord.Color.teal())
            await ctx.send(embed=embed)
            return

        await ctx.send("Ungültige Quelle gewählt.", ephemeral=True)

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
