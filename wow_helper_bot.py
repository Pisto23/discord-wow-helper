#!/usr/bin/env python3
import os
import logging
import asyncio
from typing import Dict, Tuple, Optional

import discord
from discord.ext import commands
import yaml

# Logging basic setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("discord-wow-bot")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MAPPINGS_DIR = os.path.join(BASE_DIR, "mappings")


# ---------- Loader-Funktionen für YAML ----------

def load_guides(path: str) -> Tuple[Dict[Tuple[str, str], str], Dict[Tuple[str, str], str]]:
    """
    Lädt guides.yaml und baut zwei Dicts:
    - wowhead[(klasse, spec)] = url
    - icy_veins[(klasse, spec)] = url
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    wowhead_raw = raw.get("wowhead", {}) or {}
    icy_raw = raw.get("icy_veins", {}) or {}

    wowhead: Dict[Tuple[str, str], str] = {}
    icy_veins: Dict[Tuple[str, str], str] = {}

    for cls, specs in wowhead_raw.items():
        for spec, url in (specs or {}).items():
            wowhead[(cls.lower(), spec.lower())] = url

    for cls, specs in icy_raw.items():
        for spec, url in (specs or {}).items():
            icy_veins[(cls.lower(), spec.lower())] = url

    return wowhead, icy_veins


def load_mplus(path: str) -> Dict[str, Dict[str, str]]:
    """
    Lädt mplus.yaml und gibt ein Dict der Form zurück:
    dungeons[slug] = {"name": str, "url": str}
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    return raw.get("dungeons", {}) or {}


def load_raids(path: str) -> Dict[str, Dict[str, str]]:
    """
    Lädt raids.yaml und gibt ein Dict der Form zurück:
    bosses[slug] = {"name": str, "url": str}
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    return raw.get("bosses", {}) or {}


# ---------- Discord Bot Setup ----------

intents = discord.Intents.default()
intents.message_content = True  # wichtig für on_message
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    logger.info("Logged in as %s (%s)", bot.user, bot.user.id)
    logger.info("Bot is ready.")


# ---------- Cog für WoW-Helper-Funktionen ----------

class WowHelperCog(commands.Cog):
    """
    Ein Cog, das alle Befehle und die Auto-Erkennungslogik für den WoW-Bot bündelt.
    """
    def __init__(self, bot, wowhead_guides, icy_veins_guides, mplus_dungeons, raid_bosses):
        self.bot = bot
        self.wowhead_guides = wowhead_guides
        self.icy_veins_guides = icy_veins_guides
        self.mplus_dungeons = mplus_dungeons
        self.raid_bosses = raid_bosses
        logger.info("WowHelperCog initialisiert.")

    # ---------- Helper ----------

    def _find_class_spec_in_text(self, text: str) -> Optional[Tuple[str, str]]:
        """
        Sehr einfache Auto-Erkennung:
        Wir schauen, ob im Text "<spec> <class>" oder "<class> <spec>" vorkommt,
        basierend auf allen bekannten (klasse, spec)-Keys.
        """
        text = text.lower()
        all_keys = set(list(self.wowhead_guides.keys()) + list(self.icy_veins_guides.keys()))

        for (cls, spec) in all_keys:
            combo1 = f"{spec} {cls}"
            combo2 = f"{cls} {spec}"
            if combo1 in text or combo2 in text:
                return cls, spec
        return None

    def _find_dungeon_in_text(self, text: str) -> Optional[str]:
        """
        Dungeon anhand slug oder name erkennen.
        Sehr simpel: prüft, ob slug oder dungeon-name im Text vorkommt.
        """
        text = text.lower()
        for slug, data in self.mplus_dungeons.items():
            name = (data.get("name") or "").lower()
            if slug.lower() in text or (name and name in text):
                return slug
        return None

    def _find_boss_in_text(self, text: str) -> Optional[str]:
        """
        Raidboss anhand slug oder name erkennen.
        """
        text = text.lower()
        for slug, data in self.raid_bosses.items():
            name = (data.get("name") or "").lower()
            if slug.lower() in text or (name and name in text):
                return slug
        return None

    # ---------- Commands ----------

    @commands.command(name="guide")
    async def guide_command(self, ctx: commands.Context, kind: str, cls: str, spec: str):
        """
        !guide class <klasse> <spec>
        Beispiel: !guide class paladin prot
        """
        kind = kind.lower()
        cls = cls.lower()
        spec = spec.lower()

        if kind != "class":
            await ctx.send("Aktuell unterstütze ich nur `!guide class <klasse> <spec>`.")
            return

        key = (cls, spec)
        wowhead = self.wowhead_guides.get(key)
        icy = self.icy_veins_guides.get(key)

        if not wowhead and not icy:
            await ctx.send(f"Keinen Guide gefunden für Klasse **{cls}** / Spec **{spec}**")
            return

        parts = [f"Guides für **{cls.title()} {spec.title()}**:"]
        if wowhead:
            parts.append(f"- Wowhead: {wowhead}")
        if icy:
            parts.append(f"- Icy Veins: {icy}")

        await ctx.send("\n".join(parts))

    @commands.command(name="mplus")
    async def mplus_command(self, ctx: commands.Context, subcmd: str, dungeon_slug: str, level: Optional[int] = None):
        """
        !mplus route <dungeon_slug> [stufe]
        Beispiel: !mplus route hoa
        """
        subcmd = subcmd.lower()
        dungeon_slug = dungeon_slug.lower()

        if subcmd != "route":
            await ctx.send("Verwendung: `!mplus route <dungeon> [stufe]`")
            return

        dungeon = self.mplus_dungeons.get(dungeon_slug)
        if not dungeon:
            await ctx.send(f"Keine Route für Dungeon **{dungeon_slug}** gefunden 🙈")
            return

        name = dungeon.get("name", dungeon_slug)
        url = dungeon.get("url")

        if not url:
            await ctx.send(f"Für **{name}** ist noch keine Route-URL hinterlegt.")
            return

        if level:
            await ctx.send(f"M+ Route für **{name}** (Level {level}):\n{url}")
        else:
            await ctx.send(f"M+ Route für **{name}**:\n{url}")

    @commands.command(name="raid")
    async def raid_command(self, ctx: commands.Context, boss_slug: str, mode: Optional[str] = None):
        """
        !raid <boss_slug> [mode]
        Beispiel: !raid raszageth mythic
        """
        boss_slug = boss_slug.lower()
        boss = self.raid_bosses.get(boss_slug)

        if not boss:
            await ctx.send(f"Kein MythicTrap-Link für Boss **{boss_slug}** gefunden")
            return

        name = boss.get("name", boss_slug)
        url = boss.get("url")

        if not url:
            await ctx.send(f"Für **{name}** ist noch kein MythicTrap-Link hinterlegt.")
            return

        if mode:
            await ctx.send(f"Infos zu **{name}** ({mode}):\n{url}")
        else:
            await ctx.send(f"Infos zu **{name}**:\n{url}")

    # ---------- Auto-Erkennung im Chat ----------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # eigene Messages ignorieren
        if message.author == self.bot.user:
            return

        content = message.content.lower()

        # Nur ausführen, wenn es kein expliziter Command ist, um doppelte Antworten zu vermeiden.
        if not content.startswith(self.bot.command_prefix):
            # --- 1) Klassenguide Auto-Hilfe ---
            cls_spec = self._find_class_spec_in_text(content)
            if cls_spec:
                cls, spec = cls_spec
                key = (cls, spec)
                wowhead = self.wowhead_guides.get(key)
                icy = self.icy_veins_guides.get(key)

                if wowhead or icy:
                    parts = [f"Guides für **{cls.title()} {spec.title()}** gefunden:"]
                    if wowhead:
                        parts.append(f"- Wowhead: {wowhead}")
                    if icy:
                        parts.append(f"- Icy Veins: {icy}")
                    await message.channel.send("\n".join(parts))
                    return

            # --- 2) M+ Auto-Hilfe ---
            dungeon_slug = self._find_dungeon_in_text(content)
            if dungeon_slug:
                dungeon = self.mplus_dungeons.get(dungeon_slug)
                if dungeon:
                    name = dungeon.get("name", dungeon_slug)
                    url = dungeon.get("url")
                    if url:
                        await message.channel.send(f"M+ Route für **{name}**:\n{url}")
                        return

            # --- 3) Raid-Boss Auto-Hilfe ---
            boss_slug = self._find_boss_in_text(content)
            if boss_slug:
                boss = self.raid_bosses.get(boss_slug)
                if boss:
                    name = boss.get("name", boss_slug)
                    url = boss.get("url")
                    if url:
                        await message.channel.send(f"Infos zu **{name}**:\n{url}")
                        return

        # WICHTIG: Commands weiterhin verarbeiten
        await self.bot.process_commands(message)


# ---------- Start ----------

async def main():
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise SystemExit("Bitte DISCORD_BOT_TOKEN als Umgebungsvariable setzen.")

    # ---------- Daten laden ----------
    guides_path = os.path.join(MAPPINGS_DIR, "guides.yaml")
    mplus_path = os.path.join(MAPPINGS_DIR, "mplus.yaml")
    raids_path = os.path.join(MAPPINGS_DIR, "raid.yaml")

    wowhead_guides, icy_veins_guides = load_guides(guides_path)
    mplus_dungeons = load_mplus(mplus_path)
    raid_bosses = load_raids(raids_path)

    logger.info("Mappings geladen: %d Wowhead, %d Icy-Veins, %d Dungeons, %d Bosse",
                len(wowhead_guides),
                len(icy_veins_guides),
                len(mplus_dungeons),
                len(raid_bosses),
                )

    # ---------- Cog laden und Bot starten ----------
    cog = WowHelperCog(bot, wowhead_guides, icy_veins_guides, mplus_dungeons, raid_bosses)
    await bot.add_cog(cog)
    await bot.start(token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot wird heruntergefahren.")
