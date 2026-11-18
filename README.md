# ballsdex-packs

**A BallsDex extension package that adds a pack collection and opening system.**

Users can claim free packs (daily, weekly, or custom), open them for random collectibles,
gift unopened packs to other users, and buy packs from a currency shop.

## Requirements

- BallsDex 3.0 or newer.
- **PostgreSQL.** The migrations use PostgreSQL-specific operations and are not supported on SQLite.
  Back up your database before upgrading an existing installation.

## Installation

Add the following to your `config/extra.toml` file:

```toml
[[ballsdex.packages]]
location = "git+https://github.com/seiftheman/ballsdex-packs.git@v2.3.0#main"
path = "packs"
enabled = true
```

Start the bot once so Django applies the package migrations. The `daily` and `weekly` packs
are created automatically if they do not already exist.

## Commands

All commands are under `/pack`:

| Command | Description |
| --- | --- |
| `/pack claim <type>` | Claim a free pack, respecting its cooldown and stock. Shop-only packs cannot be claimed for free. |
| `/pack open <type> [amount]` | Open up to 100 unopened packs at once. |
| `/pack give <type> <user> [amount]` | Give unopened packs to another user. |
| `/pack shop` | Browse and purchase packs with the bot currency. Packs with a blank cooldown are shop-only. |
| `/pack list` | View your unopened packs, with pagination. |
| `/pack info <type>` | Inspect a pack's price, cooldown, stock and top drop odds. |

For backwards compatibility, enabled packs whose type is a valid command name also get a
legacy claim command such as `/pack daily` or `/pack weekly`. Types that collide with the
built-in commands above, or that are longer than Discord's 32-character command limit, are
skipped and logged.

## Configuration

Packs are managed from the Django admin panel. Each pack supports:

- a display name, description and lowercase slug type;
- a free-claim cooldown (86,400 seconds for daily, 604,800 for weekly), or blank to
  disable free claims and make the pack shop-only. New custom packs start with a blank
  cooldown, so set one explicitly to enable free claims;
- rarity-range drops, or a curated list of `PackEntry` rows with relative weights;
- a price, total stock and per-user purchase limit;
- optional start/end dates;
- optional special-ball rolls (`allow_specials`);
- an enabled flag.

Pack entries override the rarity range when present. If no entries are configured, eligible
balls are drawn from enabled balls within the pack's rarity range, weighted by their rarity.

Pack instances record how they were obtained (free claim, shop, admin grant or migration),
the original claimer/purchaser, and their acquired/opened timestamps. Deleting a pack is
protected while pack instances still reference it.

### Admin commands

- `/admin pack give <type> <user> [amount]` grants packs.
- `/admin pack list` lists configured packs and their availability.
- `/admin pack setrarity <type> <min> <max>` updates a pack's rarity range.
- `b.reloadpacks` reloads the legacy pack commands and syncs the slash command tree.

## Upgrading from 2.2.x

Version 2.3.0 adds migrations `0011`-`0015` safeguards:

- `0011` now creates a fallback pack when no packs exist, so legacy installations with
  orphaned pack instances can reach the non-null `pack_id` migration.
- `0015` backfills per-user cooldown state, fills empty pack names, disables free claims
  for existing paid packs, enforces `Pack.name NOT NULL`, removes the redundant
  `packs_pack_type_key` unique constraint, and adds indexes for owner/opened and
  purchase-history queries.

Run migrations on PostgreSQL and check the migration output before deploying.

## Development

```bash
python -m pip install -e ".[dev]"
pytest -q
ruff check .
python -m compileall -q packs
```

A PostgreSQL instance with the BallsDex `bd_models` and `settings` apps installed is required
for full migration and service integration testing.

## Contact

- You can contact me via the **official Discord server**.
[![Discord](https://img.shields.io/discord/1433459095129559170?label=Support%20Server&logo=discord&color=7289DA&logoColor=white)](https://discord.gg/Sagg5CejWX)
