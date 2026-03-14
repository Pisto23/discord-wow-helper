# discord-wow-helper

A Discord bot for World of Warcraft that provides quick access to class guides, Mythic+ routes, and raid boss resources through slash commands and autocomplete.

## Overview

`discord-wow-helper` provides interactive slash commands with smart autocomplete to help WoW players quickly find guides and resources. The bot is driven by YAML mapping files in the `mappings/` folder which map class/spec combinations, dungeons, and bosses to external URLs (Wowhead, Icy Veins, MythicTrap, keystone.guru, archon.gg, etc.).

## Features

- **Slash Commands**: `/guide`, `/mplus`, `/raid`, `/rio` with smart autocomplete
- **Intelligent Autocomplete**: Filters classes, specs, dungeons, and bosses as you type
- **Configurable Mappings**: Add or edit `mappings/*.yaml` to extend content without changing code
- **Robust Error Handling**: Gracefully handles missing files, invalid YAML, and configuration errors
- **Containerized Deployment**: Docker image + Kubernetes manifest included

## Mapping files

The bot loads mapping files from the `mappings/` directory:

| File | Description |
| --- | --- |
| `guides.yaml` | (class, spec) → Wowhead / Icy Veins guide URLs |
| `mplus-routes.yaml` | Dungeon slug → name + keystone.guru route URL |
| `murloc.yaml` | (class, spec) → Murloc class guide URLs |
| `raid.yaml` | Boss slug → name + MythicTrap guide URL |
| `archon.yaml` | (class, spec) → archon.gg raid build URLs |

## Quick start

1. Install dependencies with [uv](https://github.com/astral-sh/uv):

   ```bash
   uv sync
   ```

2. Save your Discord bot token and guild config in a `.env` file in the project root:

   ```bash
   DISCORD_TOKEN=YOUR_BOT_TOKEN_HERE

   RIO_GUILD_NAME=YourGuildName
   RIO_REALM=your-realm
   RIO_REGION=eu
   ```

3. Ensure your `mappings/` directory contains the required YAML files.

4. Run the bot:

   ```bash
   uv run python wow_helper_bot.py
   ```

   On startup the bot validates configuration, loads all mapping files, syncs slash commands with Discord, and logs a summary of loaded entries.

## Slash Commands

### `/guide <klasse> <spec>`

Displays class/spec guides from Wowhead and Icy Veins.

- **Autocomplete**: Filters available classes and specs as you type
- **Example**: `/guide paladin protection`

### `/mplus <source> <item>`

Shows Mythic+ route links or Murloc class guides.

- **Source Options**:
  - `routes` — Dungeon routes from `mplus-routes.yaml`
  - `murloc` — Class guides from `murloc.yaml`
- **Autocomplete**: Dynamic filtering based on selected source
- **Examples**: `/mplus routes hoa` · `/mplus murloc paladin`

### `/raid <raid> <boss>`

Displays a raid boss guide link from MythicTrap.

- **Autocomplete**: Filters raids and bosses as you type
- **Example**: `/raid voidspire dimensius`

### `/rio`

Fetches the current season M+ scores for all guild members from [raider.io](https://raider.io) and displays a top 10 leaderboard.

- **No parameters** — guild is configured via `.env` (`RIO_GUILD_NAME`, `RIO_REALM`, `RIO_REGION`)
- **Example**: `/rio`

## Development

### Project structure

```text
discord-wow-helper/
├── wow_helper_bot.py   # Entry point — bot + cog
├── pyproject.toml      # Dependencies and Ruff config
├── Dockerfile
├── deployment.yaml     # Kubernetes manifest
├── .env                # DISCORD_TOKEN (not committed)
└── mappings/
    ├── guides.yaml
    ├── mplus-routes.yaml
    ├── murloc.yaml
    ├── raid.yaml
    └── archon.yaml
```

### Commands

```bash
# Install dependencies
uv sync

# Run
uv run python wow_helper_bot.py

# Lint
uv run ruff check .

# Format check
uv run ruff format --check .

# Auto-fix formatting
uv run ruff format .
```

### Code style

- **Ruff** for linting and formatting (100-char line length, Python 3.11 target)
- **Google-style docstrings**, double quotes, 4-space indentation

### Key components

- **`WoWBot`** — `commands.Bot` subclass. `setup_hook()` loads all YAML files, registers both cogs, manages the `aiohttp` session lifecycle, and syncs slash commands.
- **`WowHelper`** — Cog containing `/guide`, `/mplus`, and `/raid` with their autocomplete handlers. The `/mplus` `item` autocomplete is context-aware and changes based on the selected `source`.
- **`RioCog`** — Cog containing `/rio`. Makes live requests to the raider.io API to fetch guild member M+ scores and returns a top 10 leaderboard.

### Extending the bot

To add new commands:

1. Create autocomplete functions in the `WowHelper` cog
2. Add `@app_commands.autocomplete` decorators for parameters
3. Update/add YAML mappings as needed

## Deployment [Just a Playground ;) ]

### Docker

```bash
docker build -t wow-helper-bot .
docker run \
  -e DISCORD_TOKEN=your_token \
  -e RIO_GUILD_NAME=YourGuildName \
  -e RIO_REALM=your-realm \
  -e RIO_REGION=eu \
  wow-helper-bot
```

### Kubernetes

`deployment.yaml` contains a single-replica Deployment that reads `DISCORD_TOKEN` from a secret named `bot-token`:

```bash
kubectl create secret generic bot-token --from-literal=DISCORD_TOKEN=your_token
kubectl apply -f deployment.yaml
```

## Contributing

- Follow the existing code style with type hints and Google-style docstrings
- Update mapping files with clear slugs and full URLs
- Test slash commands in Discord before submitting PRs

---

**Need help?** Open an issue on GitHub or check the code documentation in [wow_helper_bot.py](wow_helper_bot.py).
