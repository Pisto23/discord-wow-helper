# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
uv sync

# Run the bot
uv run python wow_helper_bot.py

# Lint
uv run ruff check .

# Format check / auto-fix
uv run ruff format --check .
uv run ruff format .
```

## Environment

Requires a `.env` file in the project root with:
```
DISCORD_TOKEN=YOUR_BOT_TOKEN_HERE
```

## Architecture

The entire bot lives in a single file ([wow_helper_bot.py](wow_helper_bot.py)) with two classes:

- **`WoWBot`** (`commands.Bot` subclass) — `setup_hook()` loads all YAML mapping files, registers the `WowHelper` cog, and globally syncs slash commands via `self.tree.sync()`. Slash command sync happens on every startup.

- **`WowHelper`** (`commands.Cog`) — All hybrid commands (`/guide`, `/mplus`, `/raid`) and their autocomplete handlers live here. Receives all mapping data as a dict at construction time.

### Data flow

YAML files in `mappings/` → loaded in `WoWBot.setup_hook()` → passed as a `data` dict to `WowHelper.__init__()` → accessed via `self.data` in command handlers.

### Mapping files

| File | Key used | Loaded into `data[...]` |
|---|---|---|
| `guides.yaml` | `wowhead` / `icy_veins` | `data["wowhead"]`, `data["icy"]` (keyed by `(class, spec)` tuples) |
| `mplus-routes.yaml` | `dungeons` | `data["mplus_routes"]` |
| `murloc.yaml` | `classes` / `mplus_class_guides` / root | `data["murloc"]` |
| `raid.yaml` | `bosses` | `data["raids"]` |
| `archon.yaml` | `raid_class_guides` / `mplus` | `data["archon"]["raid"]`, `data["archon"]["mplus"]` |

### Hybrid commands and ephemeral responses

Commands use `@commands.hybrid_command` — they work as both slash commands (`/cmd`) and text prefix commands (`!cmd`). When using `ctx.send()`:

- Error/not-found responses use `ephemeral=True` so only the invoking user sees them.
- Successful embed responses go to `ctx.send(embed=embed)` — **without** `ephemeral=True`, making them visible to everyone in the channel.

If a response should only be visible to the invoking user, pass `ephemeral=True` to `ctx.send()`.

### Autocomplete

The `/mplus item` autocomplete is context-aware — it reads `interaction.namespace.source` and delegates to `dungeon_autocomplete`, `murloc_autocomplete`, or `archon_mplus_klasse_autocomplete` accordingly.

## Code style

- **Ruff** for linting and formatting (100-char line length, Python 3.11 target)
- Google-style docstrings, double quotes, 4-space indentation
- All classes and public methods require docstrings

## Deployment

```bash
# Docker
docker build -t wow-helper-bot .
docker run -e DISCORD_TOKEN=your_token wow-helper-bot

# Kubernetes (reads DISCORD_TOKEN from secret 'bot-token')
kubectl create secret generic bot-token --from-literal=DISCORD_TOKEN=your_token
kubectl apply -f deployment.yaml
```
