# Changelog

## Unreleased

### Added

- New ballsdex-packs logo and README banner.

### Changed

- Refreshed the `/pack shop` layout with availability status, clearer pricing/stock details,
  stable pagination controls, and selected-pack highlighting.

## 2.3.0

### Fixed

- Negative or zero amounts can no longer be used to open or give packs.
- Paid packs can no longer be claimed for free indefinitely: leaving the cooldown blank
  disables free claims, and the migration disables them for existing paid packs.
- Opening, giving and shop purchases are now transactional, preventing duplicate rewards,
  lost packs and currency overdrafts under concurrent use.
- Free claims use a unique per-user/per-pack claim row, closing the check-then-create race.
- Claim interactions defer before the database work, avoiding expired-interaction errors during
  concurrent claims.
- Shop currency formatting uses BallsDex's `format_currency` instead of crashing on unset
  currency names or rendering `None100`. The wrapper supports both the BallsDex 3.0 and 3.1
  formatter signatures.
- Weekly packs now default to a seven-day cooldown instead of one day.
- Package startup no longer resets admin-configured pack names.
- Legacy migration `0011` creates a fallback pack when orphaned instances exist and no packs
  are configured.
- Migration `0015` enforces `Pack.name NOT NULL`, removes the redundant `type` unique
  constraint, and backfills claim cooldowns.

### Added

- `/pack claim`, `/pack info` and a paginated `/pack list`.
- Pack descriptions, stock, per-user purchase limits, start/end dates and special rolls.
- Optional shop-only packs by leaving the free-claim cooldown blank.
- Curated `PackEntry` drop tables with relative weights.
- Pack instance provenance (claim/shop/admin/migration), acquisition and opening timestamps.
- Admin pack list, bulk-safe give, and index-backed owner/purchase queries.
- CI, unit tests, changelog, and PostgreSQL migration verification guidance.

### Changed

- Dynamic legacy claim command names are validated against Discord limits and reserved names.
- `/pack shop` is always registered and reports when currency is disabled.
- Pack deletion is protected while instances exist.
