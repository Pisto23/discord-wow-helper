#!/usr/bin/env python3
"""WoW Discord helper bot.

Provides slash commands to fetch World of Warcraft guides,
Mythic+ routes, and raid boss information from YAML mapping files.

This module defines a `WoWBot` (a subclass of `commands.Bot`) and a
`WowHelper` cog which exposes the following commands:
- `/guide` - lookup class/spec guides from Wowhead, Icy Veins and Archon
- `/mplus` - show Mythic+ route link for a dungeon or show classes from murloc
- `/raid`  - show raid boss guide link

Configuration is read from environment variables (via `.env`), and
mapping files are expected in the `mappings/` directory next to this
script.
"""

import asyncio
import logging
import os
from pathlib import Path

import aiohttp
import discord
import yaml
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

# Configuration
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Vars for rio cmd

RIO_GUILD_NAME = os.getenv("RIO_GUILD_NAME", "")
RIO_REALM = os.getenv("RIO_REALM", "")
RIO_REGION = os.getenv("RIO_REGION", "")
RIO_API_BASE = "https://raider.io/api/v1"


if not TOKEN:
    raise ValueError(
        "DISCORD_TOKEN not found in environment. "
        "Please set it in your .env file or environment variables."
    )

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
logger = logging.getLogger("wow-bot")

BASE_DIR = Path(__file__).parent
MAPPINGS_DIR = BASE_DIR / "mappings"

# Mapping file keys
KEY_WOWHEAD = "wowhead"
KEY_ICY_VEINS = "icy_veins"
KEY_CLASSES = "classes"
KEY_MPLUS_GUIDES = "mplus_class_guides"
KEY_DUNGEONS = "dungeons"
KEY_BOSSES = "bosses"


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
        logger.warning(f"YAML file not found: {path}")
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse YAML file {path}: {e}")
        return {}
    except Exception as e:
        logger.error(f"Error reading file {path}: {e}")
        return {}


def load_guides(
    path: Path,
) -> tuple[dict[tuple[str, str], str], dict[tuple[str, str], str]]:
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
    for src, target in [(KEY_WOWHEAD, wowhead), (KEY_ICY_VEINS, icy)]:
        for cls, specs in (raw.get(src, {}) or {}).items():
            for spec, url in (specs or {}).items():
                target[(cls.lower(), spec.lower())] = url
    return wowhead, icy


# ---------- Bot class ----------
class WoWBot(commands.Bot):
    """Discord bot implementation that loads mappings and registers cogs."""

    def __init__(self):
        """Initialize the WoW bot with default intents."""
        intents = discord.Intents.default()
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.session: aiohttp.ClientSession | None = None

    async def setup_hook(self):
        """Asynchronous setup hook used by discord.py to prepare the bot.

        Loads mapping files, registers the `WowHelper` cog and synchronizes
        application (slash) commands with Discord.
        """
        logger.info("Loading mapping files...")

        # Rio
        self.session = aiohttp.ClientSession()

        # Load mapping data
        wh, iv = load_guides(MAPPINGS_DIR / "guides.yaml")
        mplus_routes = safe_load_yaml(MAPPINGS_DIR / "mplus-routes.yaml").get(KEY_DUNGEONS, {})
        murloc_raw = safe_load_yaml(MAPPINGS_DIR / "murloc.yaml")

        # Extract murloc data from various possible structures
        if isinstance(murloc_raw, dict):
            murloc = murloc_raw.get(KEY_CLASSES) or murloc_raw.get(KEY_MPLUS_GUIDES) or murloc_raw
        else:
            murloc = {}

        archon_raw = safe_load_yaml(MAPPINGS_DIR / "archon.yaml")
        archon_data = {
            "raid": archon_raw.get("raid_class_guides", {}),
            "mplus": archon_raw.get("mplus", {}),
        }

        data = {
            "wowhead": wh,
            "icy": iv,
            "mplus_routes": mplus_routes,
            "murloc": murloc,
            "raids": safe_load_yaml(MAPPINGS_DIR / "raid.yaml"),
            "archon": archon_data,
        }

        logger.info(f"Loaded {len(wh)} Wowhead guides, {len(iv)} Icy Veins guides")
        logger.info(f"Loaded {len(mplus_routes)} M+ routes, {len(murloc)} murloc entries")
        logger.info(
            f"Loaded {len(archon_data['raid'])} archon raid classes, "
            f"{len(archon_data['mplus'])} archon M+ classes"
        )
        total_bosses = sum(len(r.get("bosses", {})) for r in data["raids"].values())
        logger.info(f"Loaded {len(data['raids'])} raids with {total_bosses} bosses")

        await self.add_cog(WowHelper(self, data))
        await self.add_cog(RioCog(self))

        logger.info("Synchronizing slash commands with Discord...")
        await self.tree.sync()
        logger.info("Synchronization complete!")

    async def close(self):
        """Clean up the aiohttp session when the bot process exits."""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("aiohttp session closed.")
        await super().close()


class WowHelper(commands.Cog):
    """Cog providing slash commands and autocompletes for WoW resources.

    The `data` argument must contain the mappings prepared in ``setup_hook``:
    keys: 'wowhead', 'icy', 'mplus_routes', 'murloc', 'raids'.
    """

    def __init__(self, bot: commands.Bot, data: dict[str, dict]):
        """Initialize the WowHelper cog with bot instance and mapping data.

        Args:
            bot: The Discord bot instance this cog is attached to.
            data: Dictionary containing WoW resource mappings with keys:
                'wowhead', 'icy', 'mplus_routes', 'murloc', 'raids'.
        """
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
        """Autocomplete for raid names (top-level keys in raid.yaml)."""
        return [
            app_commands.Choice(name=slug.title(), value=slug)
            for slug in self.data["raids"].keys()
            if current.lower() in slug.lower()
        ][:25]

    async def boss_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for boss slugs filtered by the selected raid."""
        raid_slug = interaction.namespace.raid
        if not raid_slug:
            return []
        bosses = self.data["raids"].get(raid_slug, {}).get("bosses", {})
        return [
            app_commands.Choice(name=b.get("name") or slug, value=slug)
            for slug, b in bosses.items()
            if current.lower() in (b.get("name") or slug).lower() or current.lower() in slug.lower()
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

    async def archon_mplus_klasse_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for Archon M+ class names."""
        classes = self.data.get("archon", {}).get("mplus", {})
        return [
            app_commands.Choice(name=cls.replace("_", " ").title(), value=cls)
            for cls in sorted(classes.keys())
            if current.lower() in cls.lower()
        ][:25]

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
        if src == "archon":
            return await self.archon_mplus_klasse_autocomplete(interaction, current)
        return []

    # --- Commands ---

    @app_commands.command(name="guide", description="Zeigt WoW Guides für Klasse und Spec")
    @app_commands.describe(klasse="Wähle deine Klasse", spec="Wähle deine Spezialisierung")
    @app_commands.autocomplete(klasse=klasse_autocomplete, spec=spec_autocomplete)
    async def guide(self, interaction: discord.Interaction, klasse: str, spec: str):
        """Show guides for a given class and spec.

        Args:
            interaction: The Discord interaction object.
            klasse: The chosen WoW class.
            spec: The chosen specialization.
        """
        logger.info(
            f"/guide | user={interaction.user} | guild={interaction.guild} "
            f"| channel={interaction.channel} | klasse={klasse} | spec={spec}"
        )
        k, s = klasse.lower(), spec.lower()
        key = (k, s)
        archon_url = self.data.get("archon", {}).get("raid", {}).get(k, {}).get(s)
        if key not in self.data["wowhead"] and key not in self.data["icy"] and not archon_url:
            await interaction.response.send_message(
                f"Kein Guide für {klasse} {spec} gefunden.", ephemeral=True
            )
            return

        embed = discord.Embed(title=f"Guides: {k.title()} {s.title()}", color=discord.Color.blue())
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
        if archon_url:
            embed.add_field(
                name="Archon.gg",
                value=f"[Zum Guide]({archon_url})",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="mplus", description="Zeigt M+ Routes, Murloc Klassen oder Archon Builds"
    )
    @app_commands.describe(source="Wähle eine Quelle", item="Route, Klasse oder Dungeon")
    @app_commands.choices(
        source=[
            app_commands.Choice(name="Routes (mplus-routes.yaml)", value="routes"),
            app_commands.Choice(name="Murloc Classes (murloc.yaml)", value="murloc"),
            app_commands.Choice(name="Archon.gg M+ Builds", value="archon"),
        ]
    )
    @app_commands.autocomplete(item=mplus_item_autocomplete)
    async def mplus(self, interaction: discord.Interaction, source: str, item: str):
        """Show a Mythic+ route, a Murloc class entry, or an Archon M+ build.

        Args:
            interaction: The Discord interaction object.
            source: The data source to query (routes, murloc, or archon).
            item: The dungeon slug, class name, or entry to look up.
        """
        logger.info(
            f"/mplus | user={interaction.user} | guild={interaction.guild} "
            f"| channel={interaction.channel} | source={source} | item={item}"
        )
        src = str(source)

        if src == "routes":
            d_data = self.data.get("mplus_routes", {}).get(item) or self.data.get(
                "mplus_routes", {}
            ).get((item or "").lower())
            if not d_data:
                await interaction.response.send_message(
                    f"Dungeon `{item}` nicht gefunden.", ephemeral=True
                )
                return
            embed = discord.Embed(
                title=f"M+ Route: {d_data.get('name', item)}",
                color=discord.Color.green(),
            )
            embed.add_field(name="Route Link", value=f"[Hier klicken]({d_data.get('url', '')})")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if src == "murloc":
            murloc_data = self.data.get("murloc", {})
            c_data = murloc_data.get(item) or murloc_data.get((item or "").lower())
            if not c_data:
                await interaction.response.send_message(
                    f"Eintrag `{item}` nicht gefunden.", ephemeral=True
                )
                return

            if isinstance(c_data, dict):
                # If values are URLs (spec -> url), list them
                if any(isinstance(v, str) and v.startswith("http") for v in c_data.values()):
                    embed = discord.Embed(
                        title=f"Class Guides: {item.replace('_', ' ').title()}",
                        color=discord.Color.teal(),
                    )
                    for spec, url in sorted(c_data.items()):
                        if isinstance(url, str) and url.startswith("http"):
                            embed.add_field(
                                name=spec.title(), value=f"[Guide]({url})", inline=False
                            )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return

                # Fallback: dict with 'name'/'url'
                name = c_data.get("name", item.replace("_", " ").title())
                url = c_data.get("url")
                embed = discord.Embed(title=f"Murloc: {name}", color=discord.Color.teal())
                if url:
                    embed.add_field(name="Link", value=f"[Hier klicken]({url})")
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            # Simple string entry
            name = str(c_data)
            embed = discord.Embed(title=f"Murloc: {name}", color=discord.Color.teal())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if src == "archon":
            archon_mplus = self.data.get("archon", {}).get("mplus", {})
            cls_data = archon_mplus.get(item) or archon_mplus.get((item or "").lower())
            if not cls_data:
                await interaction.response.send_message(
                    f"Klasse `{item}` nicht gefunden.", ephemeral=True
                )
                return
            embed = discord.Embed(
                title=f"Archon.gg M+: {item.replace('_', ' ').title()}",
                color=discord.Color.purple(),
            )
            for spec, url in sorted(cls_data.items()):
                if isinstance(url, str) and url.startswith("http"):
                    embed.add_field(
                        name=spec.replace("_", " ").title(),
                        value=f"[Archon.gg]({url})",
                        inline=False,
                    )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.send_message("Ungültige Quelle gewählt.", ephemeral=True)

    @app_commands.command(name="raid", description="Zeigt Boss-Infos aus dem Raid")
    @app_commands.describe(raid="Wähle den Raid", boss="Wähle den Boss")
    @app_commands.autocomplete(raid=raid_autocomplete, boss=boss_autocomplete)
    async def raid(self, interaction: discord.Interaction, raid: str, boss: str):
        """Show raid boss information and a guide link for the chosen boss.

        Args:
            interaction: The Discord interaction object.
            raid: The raid slug to look up.
            boss: The boss slug to look up.
        """
        logger.info(
            f"/raid | user={interaction.user} | guild={interaction.guild} "
            f"| channel={interaction.channel} | raid={raid} | boss={boss}"
        )
        bosses = self.data["raids"].get(raid, {}).get("bosses", {})
        b_data = bosses.get(boss)
        if not b_data:
            await interaction.response.send_message(
                f"Boss `{boss}` nicht gefunden.", ephemeral=True
            )
            return
        embed = discord.Embed(title=f"Raid Boss: {b_data['name']}", color=discord.Color.red())
        embed.add_field(name="Mythictrap Link", value=f"[{b_data['name']}]({b_data['url']})")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class RioCog(commands.Cog):
    """Cog providing the /rio slash command to display guild M+ leaderboards."""

    def __init__(self, bot):
        """Initialize the RioCog with the bot instance.

        Args:
            bot: The Discord bot instance this cog is attached to.
        """
        self.bot = bot

    async def fetch_char_score(
        self,
        session: aiohttp.ClientSession,
        name: str,
        semaphore: asyncio.Semaphore,
        realm: str = "",
    ) -> tuple:
        """Holt den Score für einen einzelnen Charakter mit Rate-Limiting."""
        char_realm = realm or RIO_REALM
        url = (
            f"{RIO_API_BASE}/characters/profile"
            f"?region={RIO_REGION}"
            f"&realm={char_realm}"
            f"&name={name}"
            f"&fields=mythic_plus_scores_by_season:current"
        )

        async with semaphore:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        seasons = data.get("mythic_plus_scores_by_season", [])
                        char_class = data.get("class", "Unknown")
                        score = seasons[0]["scores"]["all"] if seasons else 0.0
                        return (score, name, char_class)
            except Exception as e:
                logger.debug(f"Fehler beim Abrufen von {name}: {e}")

        return (0.0, name, "Unknown")

    @app_commands.command(
        name="rio", description="Zeigt die Top 10 M+ Scores der Gilde von Raider.io"
    )
    async def rio(self, interaction: discord.Interaction) -> None:
        """Fetch and display the top 10 M+ scores for the configured guild.

        Args:
            interaction: The Discord interaction object.
        """
        logger.info(
            f"/rio | user={interaction.user} | guild={interaction.guild} "
            f"| channel= {interaction.channel}"
        )

        if not RIO_GUILD_NAME or not RIO_REALM:
            await interaction.response.send_message(
                "Gildenkonfiguration fehlt. Bitte `RIO_GUILD_NAME` und"
                " `RIO_REALM` in `.env` setzen.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        guild_url = (
            f"{RIO_API_BASE}/guilds/profile"
            f"?region={RIO_REGION}"
            f"&realm={RIO_REALM}"
            f"&name={RIO_GUILD_NAME}"
            f"&fields=members"
        )

        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with self.bot.session.get(guild_url, timeout=timeout) as resp:
                if resp.status == 400:
                    await interaction.followup.send(
                        "Gilde nicht gefunden. Bitte Konfiguration prüfen.",
                        ephemeral=True,
                    )
                    return
                if resp.status != 200:
                    await interaction.followup.send(
                        f"Raider.io API Fehler (HTTP {resp.status}). Bitte später versuchen.",
                        ephemeral=True,
                    )
                    return
                guild_data = await resp.json()
        except aiohttp.ClientError as exc:
            logger.error(f"/rio | aiohttp error: {exc}")
            await interaction.followup.send(
                "Netzwerkfehler beim Abrufen der Raider.io Daten.", ephemeral=True
            )
            return

        members = guild_data.get("members", [])

        # IMPORTANT: Limitation!
        # If the guild has 500 members, this will exceed Raider.IO's request limit.
        # Filter to the first 100 roster entries to stay within bounds.
        members = members[:100]

        if not members:
            await interaction.followup.send(
                "Die Gilde hat scheinbar keine Mitglieder.", ephemeral=True
            )
            return

        semaphore = asyncio.Semaphore(10)

        tasks = [
            self.fetch_char_score(
                self.bot.session,
                entry["character"]["name"],
                semaphore,
                realm=entry["character"].get("realm", ""),
            )
            for entry in members
            if "character" in entry
        ]

        scored = await asyncio.gather(*tasks)

        scored.sort(key=lambda x: x[0], reverse=True)
        top10 = [x for x in scored if x[0] > 0][:10]  # Only ppls with > 0 Score

        guild_display = guild_data.get("name", RIO_GUILD_NAME)
        embed = discord.Embed(
            title=f"Raider.io M+ Top 10 - {guild_display}",
            color=discord.Color.gold(),
        )
        embed.set_footer(text=f"Region: {RIO_REGION.upper()} | Realm: {RIO_REALM.title()}")

        if not top10:
            embed.description = "Keine Scores (oder nur 0.0) in der Gilde gefunden."
        else:
            lines = []
            for rank, (score, name, char_class) in enumerate(top10, start=1):
                score_str = f"{score:.1f}"
                class_label = f"({char_class})" if char_class else ""
                lines.append(f"`{rank:>2}.` **{name}** {class_label} - {score_str}")
            embed.description = "\n".join(lines)

        await interaction.followup.send(embed=embed, ephemeral=True)


async def main():
    """Create and run the WoW bot using the configured token."""
    bot = WoWBot()
    try:
        async with bot:
            logger.info("Starting WoW Discord bot...")
            await bot.start(TOKEN)
    except discord.LoginFailure:
        logger.error("Invalid Discord token. Please check your DISCORD_TOKEN.")
        raise
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
