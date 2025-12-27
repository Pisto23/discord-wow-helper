#!/usr/bin/env python3
import os
import logging
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


# ---------- Daten laden ----------

GUIDES_PATH = os.path.join(MAPPINGS_DIR, "guides.yaml")
MPLUS_PATH = os.path.join(MAPPINGS_DIR, "mplus.yaml")
RAIDS_PATH = os.path.join(MAPPINGS_DIR, "raid.yaml")

WOWHEAD_GUIDES, ICY_VEINS_GUIDES = load_guides(GUIDES_PATH)
MPLUS_DUNGEONS = load_mplus(MPLUS_PATH)
RAID_BOSSES = load_raids(RAIDS_PATH)

logger.info("Mappings geladen: %d Wowhead, %d Icy-Veins, %d Dungeons, %d Bosse",
            len(WOWHEAD_GUIDES),
            len(ICY_VEINS_GUIDES),
            len(MPLUS_DUNGEONS),
            len(RAID_BOSSES),
            )

# ---------- Discord Bot Setup ----------

intents = discord.Intents.default()
intents.message_content = True  # wichtig für on_message
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    logger.info("Logged in as %s (%s)", bot.user, bot.user.id)
    logger.info("Bot is ready.")


# ---------- Helper ----------

def find_class_spec_in_text(text: str) -> Optional[Tuple[str, str]]:
    """
    Sehr einfache Auto-Erkennung:
    Wir schauen, ob im Text "<spec> <class>" oder "<class> <spec>" vorkommt,
    basierend auf allen bekannten (klasse, spec)-Keys.
    """
    text = text.lower()

    for (cls, spec) in set(list(WOWHEAD_GUIDES.keys()) + list(ICY_VEINS_GUIDES.keys())):
        combo1 = f"{spec} {cls}"
        combo2 = f"{cls} {spec}"
        if combo1 in text or combo2 in text:
            return cls, spec

    return None


def find_dungeon_in_text(text: str) -> Optional[str]:
    """
    Dungeon anhand slug oder name erkennen.
    Sehr simpel: prüft, ob slug oder dungeon-name im Text vorkommt.
    """
    text = text.lower()

    for slug, data in MPLUS_DUNGEONS.items():
        name = (data.get("name") or "").lower()
        if slug.lower() in text or (name and name in text):
            return slug

    return None


def find_boss_in_text(text: str) -> Optional[str]:
    """
    Raidboss anhand slug oder name erkennen.
    """
    text = text.lower()

    for slug, data in RAID_BOSSES.items():
        name = (data.get("name") or "").lower()
        if slug.lower() in text or (name and name in text):
            return slug

    return None


# ---------- Commands ----------

@bot.command(name="guide")
async def guide_command(ctx: commands.Context, kind: str, cls: str, spec: str):
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
    wowhead = WOWHEAD_GUIDES.get(key)
    icy = ICY_VEINS_GUIDES.get(key)

    if not wowhead and not icy:
        await ctx.send(f"Keinen Guide gefunden für Klasse **{cls}** / Spec **{spec}**")
        return

    parts = [f"Guides für **{cls.title()} {spec.title()}**:"]
    if wowhead:
        parts.append(f"- Wowhead: {wowhead}")
    if icy:
        parts.append(f"- Icy Veins: {icy}")

    await ctx.send("\n".join(parts))


@bot.command(name="mplus")
async def mplus_command(ctx: commands.Context, subcmd: str, dungeon_slug: str, level: Optional[int] = None):
    """
    !mplus route <dungeon_slug> [stufe]
    Beispiel: !mplus route hoa
    """
    subcmd = subcmd.lower()
    dungeon_slug = dungeon_slug.lower()

    if subcmd != "route":
        await ctx.send("Verwendung: `!mplus route <dungeon> [stufe]`")
        return

    dungeon = MPLUS_DUNGEONS.get(dungeon_slug)
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


@bot.command(name="raid")
async def raid_command(ctx: commands.Context, boss_slug: str, mode: Optional[str] = None):
    """
    !raid <boss_slug> [mode]
    Beispiel: !raid raszageth mythic
    """
    boss_slug = boss_slug.lower()
    boss = RAID_BOSSES.get(boss_slug)

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

@bot.event
async def on_message(message: discord.Message):
    # eigene Messages ignorieren
    if message.author == bot.user:
        return

    content = message.content.lower()

    # Nur ausführen, wenn es kein expliziter Command ist, um doppelte Antworten zu vermeiden.
    if not content.startswith(bot.command_prefix):
        # --- 1) Klassenguide Auto-Hilfe ---
        cls_spec = find_class_spec_in_text(content)
        if cls_spec:
            cls, spec = cls_spec
            key = (cls, spec)
            wowhead = WOWHEAD_GUIDES.get(key)
            icy = ICY_VEINS_GUIDES.get(key)

            if wowhead or icy:
                parts = [f"Guides für **{cls.title()} {spec.title()}** gefunden:"]
                if wowhead:
                    parts.append(f"- Wowhead: {wowhead}")
                if icy:
                    parts.append(f"- Icy Veins: {icy}")
                await message.channel.send("\n".join(parts))
                return

        # --- 2) M+ Auto-Hilfe ---
        dungeon_slug = find_dungeon_in_text(content)
        if dungeon_slug:
            dungeon = MPLUS_DUNGEONS.get(dungeon_slug)
            if dungeon:
                name = dungeon.get("name", dungeon_slug)
                url = dungeon.get("url")
                if url:
                    await message.channel.send(f"M+ Route für **{name}**:\n{url}")
                    return

        # --- 3) Raid-Boss Auto-Hilfe ---
        boss_slug = find_boss_in_text(content)
        if boss_slug:
            boss = RAID_BOSSES.get(boss_slug)
            if boss:
                name = boss.get("name", boss_slug)
                url = boss.get("url")
                if url:
                    await message.channel.send(f"Infos zu **{name}**:\n{url}")
                    return

    # WICHTIG: Commands weiterhin verarbeiten
    await bot.process_commands(message)


# ---------- Start ----------

def main():
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise SystemExit("Bitte DISCORD_BOT_TOKEN als Umgebungsvariable setzen.")
    bot.run(token)


if __name__ == "__main__":
    main()
