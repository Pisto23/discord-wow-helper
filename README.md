# discord-wow-helper

A Discord bot for World of Warcraft that provides quick access to class guides, Mythic+ routes, and raid boss resources through slash commands and autocomplete.

## Overview

`discord-wow-helper` provides interactive slash commands with smart autocomplete to help WoW players quickly find guides and resources. The bot is driven by YAML mapping files in the `mappings/` folder which map class/spec combinations, dungeons, and bosses to external URLs (Wowhead, Icy Veins, MythicTrap, route links, etc.).

Built with professional standards including comprehensive error handling, detailed logging and robust configuration validation.

## Features

- **Slash Commands**: `/guide`, `/mplus`, `/raid` with smart autocomplete
- **Hybrid Commands**: Works as both slash commands and traditional text commands with `!` prefix
- **Intelligent Autocomplete**: Filters classes, specs, dungeons, and bosses as you type
- **Configurable Mappings**: Add or edit `mappings/*.yaml` to extend content without changing code
- **Robust Error Handling**: Gracefully handles missing files, invalid YAML, and configuration errors
- **Comprehensive Logging**: Detailed startup information and error tracking

## Expected mapping files

The bot loads mapping files from the `mappings/` directory. By default it expects:

- `guides.yaml` — maps classes and specs to Wowhead / Icy Veins guide URLs.
- `mplus-routes.yaml` — maps dungeon slugs to route names and URLs.
- `murloc.yaml` — optional mappings for Murloc class guides or single-entry items.
- `raid.yaml` — maps raid boss slugs to names and MythicTrap (or other) URLs.

If your YAML files use different names (for example `mplus.yaml` or `raids.yaml`), rename them to the expected filenames or update the code constants in [wow_helper_bot.py](wow_helper_bot.py).

## Quick start

1. Create a Python virtual environment and activate it:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies (this project uses `discord.py` and `PyYAML`):

   ```bash
   pip install -r requirements.txt
   ```

3. Save your Discord bot token in a `.env` file placed in the project root. The file should use simple KEY=VALUE format (no quotes):

   ```bash
   DISCORD_TOKEN=YOUR_BOT_TOKEN_HERE
   ```

   **Important**: The bot validates that `DISCORD_TOKEN` is set on startup and will exit with a clear error message if missing.

4. Ensure your `mappings/` directory contains the required YAML files (see "Expected mapping files" section above).

5. Run the bot:

   ```bash
   python3 wow_helper_bot.py
   ```

   The bot will:

   - Validate configuration
   - Load mapping files with detailed logging
   - Connect to Discord
   - Sync slash commands
   - Begin responding to commands

   Check the console output for startup information including counts of loaded guides, routes, and bosses.

## Slash Commands & Examples

### `/guide <klasse> <spec>`

Displays class and spec guides from Wowhead and Icy Veins.

- **Autocomplete**: Filters available classes and specs as you type
- **Example**: `/guide paladin protection`
- **Output**: Embedded message with guide links

### `/mplus <source> <item>`

Shows Mythic+ route links or Murloc class guides.

- **Source Options**:
  - `routes` - Dungeon routes from mplus-routes.yaml
  - `murloc` - Class guides from murloc.yaml
- **Autocomplete**: Dynamic filtering based on selected source
- **Examples**:
  - `/mplus routes hoa`
  - `/mplus murloc paladin`

### `/raid <boss>`

Displays raid boss guide links.

- **Autocomplete**: Filters available bosses as you type
- **Example**: `/raid dimensius`
- **Output**: Embedded message with MythicTrap guide link

All commands also work with the `!` prefix for traditional text commands (e.g., `!guide paladin protection`).

## Configuration / extending mappings

Open the YAML files in `mappings/` to add or update entries. The loader functions in `wow_helper_bot.py` document the expected structure (see the top of the file for details). After modifying mappings, restart the bot to pick up changes.

## Development

### Project Structure

- **Entry point**: [wow_helper_bot.py](wow_helper_bot.py)
- **Configuration**: `.env` file (DISCORD_TOKEN)
- **Mappings**: `mappings/` directory (YAML files)

### Code Quality

The codebase follows typical Python standards:

- **Type Hints**: Full type annotations for all functions and methods
- **Error Handling**: Comprehensive try/except blocks with informative logging
- **Documentation**: Detailed docstrings following Google style
- **Constants**: Centralized configuration keys to avoid magic strings
- **Logging**: Structured logging with appropriate levels (INFO, WARNING, ERROR)
- **Validation**: Startup checks for required configuration and files

### Key Components

- **`WoWBot`**: Main bot class extending `commands.Bot`
  - Handles setup and slash command synchronization
  - Loads all mapping files on startup

- **`WowHelper`**: Cog containing all commands and autocomplete logic
  - Implements `/guide`, `/mplus`, `/raid` commands
  - Provides dynamic autocomplete for all parameters

- **Data Loaders**:
  - `safe_load_yaml()`: Safely loads YAML with error handling
  - `load_guides()`: Parses guide mappings into indexed dictionaries

### Running Tests

To verify your setup:

1. Check that all mapping files exist and are valid YAML
2. Ensure DISCORD_TOKEN is set in `.env`
3. Run the bot and verify startup logs show loaded data counts
4. Test slash commands in Discord

### Extending the Bot

To add new commands:

1. Create autocomplete functions in the `WowHelper` cog
2. Define hybrid commands using `@commands.hybrid_command`
3. Add `@app_commands.autocomplete` decorators for parameters
4. Update YAML mappings as needed

## Error Handling

The bot includes comprehensive error handling:

- **Missing Token**: Clear error message on startup if `DISCORD_TOKEN` not found
- **Invalid YAML**: Logs warnings for missing or malformed mapping files
- **Login Failures**: Catches and reports Discord authentication errors
- **Missing Data**: Graceful responses when requested guides/routes don't exist

All errors are logged with context to help diagnose issues quickly.

## Logging

The bot provides detailed logging during operation:

```text
2026-01-31 12:00:00 | Loading mapping files...
2026-01-31 12:00:00 | Loaded 36 Wowhead guides, 36 Icy Veins guides
2026-01-31 12:00:00 | Loaded 8 M+ routes, 13 murloc entries
2026-01-31 12:00:00 | Loaded 8 raid bosses
2026-01-31 12:00:00 | Synchronizing slash commands with Discord...
2026-01-31 12:00:00 | Synchronization complete!
2026-01-31 12:00:01 | Starting WoW Discord bot...
```

## Contributing

Contributions are welcome! When contributing:

- Follow the existing code style with type hints and docstrings
- Add error handling for new features
- Update mapping files with clear slugs and full URLs
- Test slash commands before submitting PRs

---

**Need help?** Open an issue on GitHub or check the code documentation in [wow_helper_bot.py](wow_helper_bot.py).
