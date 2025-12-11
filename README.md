# discord-wow-helper

A small Discord helper bot for World of Warcraft that answers quick questions and shares useful links for class guides, Mythic+ routes, and raid boss resources.

## Overview

`discord-wow-helper` listens to chat and responds with helpful links based on short commands or simple auto-detection of class/spec, dungeon, or boss names. It is driven by YAML mapping files in the `mappings/` folder which map known slugs and names to external URLs (Wowhead, Icy Veins, MythicTrap, route links, etc.).

## Features

- Command-based lookups: `!guide`, `!mplus`, `!raid`.
- Auto-detection: the bot scans messages for class+spec, M+ dungeon names, or raid boss names and posts helpful links.
- Configurable mappings: add or edit `mappings/*.yaml` to extend or fix content without changing code.

## Expected mapping files

The bot loads mapping files from the `mappings/` directory. By default it expects:

- `guides.yaml` — maps classes and specs to Wowhead / Icy Veins guide URLs.
- `mplus.yaml` — maps dungeon slugs to route names and URLs.
- `raids.yaml` — maps raid boss slugs to names and MythicTrap (or other) URLs.

If your YAML files use different names (for example `raid.yaml`), rename them to the expected filenames or update the code constants in `wow_helper_bot.py`.

## Quick start

1. Create a Python virtual environment and activate it:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies (this project uses `discord.py` and `PyYAML`):

```powershell
pip install -U discord.py PyYAML
```

3. Set your Discord bot token as an environment variable:

```powershell
$env:DISCORD_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
```

4. Run the bot:

```powershell
python wow_helper_bot.py
```

The bot will log in and begin responding in any server where it is invited and has the necessary permissions.

## Commands & examples

- `!guide class <klasse> <spec>` — explicit guide lookup.
	- Example: `!guide class paladin prot`
- `!mplus route <dungeon_slug> [stufe]` — posts a route link for a dungeon.
	- Example: `!mplus route hoa 16`
- `!raid <boss_slug> [mode]` — posts raid/boss info link.
	- Example: `!raid raszageth mythic`

In addition to commands, the bot attempts to auto-detect mentions of class/spec (e.g. "prot paladin"), M+ references (e.g. dungeon names), and raid boss names and will reply with the best-matching links.

## Configuration / extending mappings

Open the YAML files in `mappings/` to add or update entries. The loader functions in `wow_helper_bot.py` document the expected structure (see the top of the file for details). After modifying mappings, restart the bot to pick up changes.

## Development

- Code entry point: `wow_helper_bot.py`
- Main settings: `DISCORD_BOT_TOKEN` environment variable
- Mapping directory: `mappings/`

To run locally for development, follow the Quick start and edit the YAML files or Python code as needed.

## Contributing

Feel free to open issues or submit pull requests. When adding mappings, prefer clear slugs and full URLs so auto-detection works reliably.

## License

This repository does not include a license file. Add a LICENSE if you want to define reuse terms.

---

If anything in this README should reflect additional project details or custom commands you use, tell me what to add and I will update it.

