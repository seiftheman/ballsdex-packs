from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import timedelta

from bd_models.models import Ball, BallInstance, Player, Special
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from settings.models import settings

from packs.models import Pack, PackClaim, PackEntry, PackInstance


class PackError(Exception):
    """Base class for recoverable pack errors."""


class PackNotFound(PackError):
    def __init__(self, pack_type: str):
        self.pack_type = pack_type
        super().__init__(f"Pack type {pack_type!r} does not exist.")


class PackUnavailable(PackError):
    def __init__(self, pack: Pack):
        self.pack = pack
        super().__init__(f"{pack.name} is not currently available.")


class PackClaimDisabled(PackError):
    def __init__(self, pack: Pack):
        self.pack = pack
        super().__init__(f"Free claims are disabled for {pack.name}; it is shop-only.")


class PackCooldown(PackError):
    def __init__(self, pack: Pack, remaining: float):
        self.pack = pack
        self.remaining = remaining
        super().__init__(f"{pack.name} is on cooldown for {remaining:.0f} seconds.")


class NotEnoughPacks(PackError):
    def __init__(self, pack: Pack, available: int, requested: int):
        self.pack = pack
        self.available = available
        self.requested = requested
        super().__init__(f"Only {available} of {requested} {pack.name} packs are available.")


class NoBalls(PackError):
    def __init__(self, pack: Pack):
        self.pack = pack
        super().__init__(f"No collectibles are available for {pack.name}.")


class OutOfStock(PackError):
    def __init__(self, pack: Pack):
        self.pack = pack
        super().__init__(f"{pack.name} is out of stock.")


class PurchaseLimitReached(PackError):
    def __init__(self, pack: Pack, limit: int, purchased: int):
        self.pack = pack
        self.limit = limit
        self.purchased = purchased
        super().__init__(f"You already purchased {purchased}/{limit} {pack.name} packs.")


class NotEnoughMoney(PackError):
    def __init__(self, pack: Pack, total: int, balance: int):
        self.pack = pack
        self.total = total
        self.balance = balance
        self.shortfall = max(0, total - balance)
        super().__init__(f"Not enough currency for {pack.name}.")


class PackConflict(PackError):
    """The underlying rows changed while an operation was in progress."""


@dataclass(slots=True)
class ClaimStatus:
    pack: Pack
    can_claim: bool
    remaining: float


@dataclass(slots=True)
class ClaimOutcome:
    pack: Pack
    claimed: bool
    remaining: float


@dataclass(slots=True)
class OpenedBall:
    country: str
    ball_id: int
    instance_id: int | None
    attack_bonus: int
    health_bonus: int
    rarity: float
    special: str | None
    is_new: bool


@dataclass(slots=True)
class OpenOutcome:
    pack: Pack
    balls: list[OpenedBall]
    opened: int


@dataclass(slots=True)
class GiveOutcome:
    pack: Pack
    given: int


@dataclass(slots=True)
class BuyOutcome:
    pack: Pack
    bought: int
    total_cost: int
    new_balance: int


@dataclass(slots=True)
class PoolPreview:
    pack: Pack
    total_balls: int
    rows: list[tuple[Ball, float]]


def _get_pack_by_type(pack_type: str) -> Pack:
    pack = Pack.objects.filter(type=pack_type.strip().lower()).first()
    if pack is None:
        raise PackNotFound(pack_type)
    return pack


def get_claim_status(discord_id: int, pack_id: int) -> ClaimStatus:
    pack = Pack.objects.get(pk=pack_id)
    claim = PackClaim.objects.filter(discord_id=discord_id, pack=pack).first()
    if pack.cooldown_seconds is None:
        return ClaimStatus(pack=pack, can_claim=False, remaining=0.0)
    if claim is None:
        return ClaimStatus(pack=pack, can_claim=pack.available, remaining=0.0)

    elapsed = (timezone.now() - claim.last_claim_date).total_seconds()
    remaining = max(0.0, pack.cooldown_seconds - elapsed)
    return ClaimStatus(pack=pack, can_claim=remaining <= 0 and pack.available, remaining=remaining)


def claim_pack(discord_id: int, pack_id: int) -> ClaimOutcome:
    """Atomically claim a free pack and enforce the per-user cooldown."""
    now = timezone.now()
    with transaction.atomic():
        try:
            pack = Pack.objects.select_for_update().get(pk=pack_id)
        except Pack.DoesNotExist as exc:
            raise PackError("This pack no longer exists.") from exc

        if pack.cooldown_seconds is None:
            raise PackClaimDisabled(pack)
        if not pack.available:
            raise PackUnavailable(pack)

        claim, created = PackClaim.objects.get_or_create(
            discord_id=discord_id,
            pack=pack,
            defaults={"last_claim_date": now},
        )
        if not created:
            cutoff = now - timedelta(seconds=pack.cooldown_seconds)
            updated = PackClaim.objects.filter(pk=claim.pk, last_claim_date__lte=cutoff).update(
                last_claim_date=now
            )
            if not updated:
                remaining = max(
                    0.0,
                    (claim.last_claim_date + timedelta(seconds=pack.cooldown_seconds) - now).total_seconds(),
                )
                raise PackCooldown(pack, remaining)

        if pack.stock is not None:
            if pack.stock <= 0:
                raise OutOfStock(pack)
            pack.stock -= 1
            pack.save(update_fields=["stock"])

        PackInstance.objects.create(
            pack=pack,
            discord_id=discord_id,
            claimed_by_discord_id=discord_id,
            source=PackInstance.Source.CLAIM,
            last_claim_date=now,
        )

    return ClaimOutcome(pack=pack, claimed=True, remaining=0.0)


def get_pack_pool(pack: Pack) -> tuple[list[Ball], list[float]]:
    """Return the eligible balls and their relative weights for a pack."""
    has_entries = PackEntry.objects.filter(pack=pack).exists()
    if has_entries:
        # A curated pool replaces the rarity pool. If every entry is disabled or has
        # zero weight, the pack is empty rather than silently falling back.
        entries = list(
            PackEntry.objects.filter(
                pack=pack, weight__gt=0, ball__enabled=True
            ).select_related("ball")
        )
        balls = [entry.ball for entry in entries]
        weights = [entry.weight for entry in entries]
    else:
        query = Ball.enabled_objects.filter(rarity__gt=0)
        if pack.min_rarity is not None:
            query = query.filter(rarity__gte=pack.min_rarity)
        if pack.max_rarity is not None:
            query = query.filter(rarity__lte=pack.max_rarity)
        balls = list(query)
        weights = [ball.rarity for ball in balls]

    if not balls or sum(weights) <= 0:
        raise NoBalls(pack)
    return balls, weights


def _active_specials() -> list[Special]:
    now = timezone.now()
    return list(
        Special.enabled_objects.filter(
            Q(start_date__isnull=True) | Q(start_date__lte=now),
            Q(end_date__isnull=True) | Q(end_date__gte=now),
        )
    )


def _roll_special(pack: Pack, specials: list[Special]) -> Special | None:
    if not pack.allow_specials or not specials:
        return None
    weights = [max(0.0, special.rarity) for special in specials]
    common_weight = max(0.0, 1.0 - sum(weights))
    population: list[Special | None] = [*specials, None]
    weights.append(common_weight)
    if sum(weights) <= 0:
        return None
    return random.choices(population=population, weights=weights, k=1)[0]


def open_packs(
    discord_id: int,
    pack_type: str,
    amount: int,
    *,
    server_id: int | None = None,
) -> OpenOutcome:
    """Atomically consume unopened packs and create the rewarded ball instances."""
    if amount < 1:
        raise ValueError("amount must be at least 1")

    with transaction.atomic():
        try:
            pack = Pack.objects.get(type=pack_type.strip().lower())
        except Pack.DoesNotExist as exc:
            raise PackNotFound(pack_type) from exc

        instances = list(
            PackInstance.objects.select_for_update()
            .filter(discord_id=discord_id, pack=pack, is_opened=False)
            .order_by("acquired_at", "pk")[:amount]
        )
        if len(instances) < amount:
            raise NotEnoughPacks(pack, len(instances), amount)

        player, _ = Player.objects.get_or_create(discord_id=discord_id)
        balls, weights = get_pack_pool(pack)
        existing = set(
            BallInstance.objects.filter(player=player).values_list("ball_id", flat=True)
        )
        specials = _active_specials()
        now = timezone.now()
        max_attack_bonus = max(0, settings.max_attack_bonus)
        max_health_bonus = max(0, settings.max_health_bonus)

        created_instances: list[BallInstance] = []
        result_rows: list[tuple[BallInstance, Ball, bool, Special | None]] = []
        for _ in range(amount):
            ball = random.choices(balls, weights=weights, k=1)[0]
            attack_bonus = random.randint(-max_attack_bonus, max_attack_bonus)
            health_bonus = random.randint(-max_health_bonus, max_health_bonus)
            special = _roll_special(pack, specials)
            is_new = ball.pk not in existing
            existing.add(ball.pk)
            instance = BallInstance(
                ball=ball,
                player=player,
                attack_bonus=attack_bonus,
                health_bonus=health_bonus,
                special=special,
                server_id=server_id,
            )
            created_instances.append(instance)
            result_rows.append((instance, ball, is_new, special))

        BallInstance.all_objects.bulk_create(created_instances)
        PackInstance.objects.filter(
            pk__in=[instance.pk for instance in instances],
            is_opened=False,
        ).update(is_opened=True, opened_at=now)

        opened = [
            OpenedBall(
                country=ball.country,
                ball_id=ball.pk,
                instance_id=instance.pk,
                attack_bonus=instance.attack_bonus,
                health_bonus=instance.health_bonus,
                rarity=ball.rarity,
                special=special.name if special else None,
                is_new=is_new,
            )
            for instance, ball, is_new, special in result_rows
        ]

    return OpenOutcome(pack=pack, balls=opened, opened=len(opened))


def give_packs(discord_id: int, target_id: int, pack_type: str, amount: int) -> GiveOutcome:
    if amount < 1:
        raise ValueError("amount must be at least 1")

    with transaction.atomic():
        pack = _get_pack_by_type(pack_type)
        ids = list(
            PackInstance.objects.select_for_update()
            .filter(discord_id=discord_id, pack=pack, is_opened=False)
            .order_by("acquired_at", "pk")
            .values_list("pk", flat=True)[:amount]
        )
        if len(ids) < amount:
            raise NotEnoughPacks(pack, len(ids), amount)

        updated = PackInstance.objects.filter(
            pk__in=ids,
            discord_id=discord_id,
            is_opened=False,
        ).update(discord_id=target_id)
        if updated != len(ids):
            raise PackConflict("Some packs changed owners before the transfer completed.")

    return GiveOutcome(pack=pack, given=updated)


def buy_packs(discord_id: int, pack_id: int, amount: int) -> BuyOutcome:
    if amount < 1:
        raise ValueError("amount must be at least 1")

    with transaction.atomic():
        try:
            pack = Pack.objects.select_for_update().get(pk=pack_id)
        except Pack.DoesNotExist as exc:
            raise PackError("This pack no longer exists.") from exc

        if not pack.available:
            raise PackUnavailable(pack)
        if pack.price is None:
            raise PackUnavailable(pack)
        if pack.stock is not None and pack.stock < amount:
            raise OutOfStock(pack)

        player, _ = Player.objects.get_or_create(discord_id=discord_id)
        player = Player.objects.select_for_update().get(pk=player.pk)

        if pack.purchase_limit is not None:
            purchased = PackInstance.objects.filter(
                pack=pack,
                purchased_by_discord_id=discord_id,
            ).count()
            if purchased + amount > pack.purchase_limit:
                raise PurchaseLimitReached(pack, pack.purchase_limit, purchased)

        total_cost = pack.price * amount
        if player.money < total_cost:
            raise NotEnoughMoney(pack, total_cost, player.money)

        new_balance = player.money - total_cost
        Player.objects.filter(pk=player.pk).update(money=F("money") - total_cost)

        if pack.stock is not None:
            pack.stock -= amount
            pack.save(update_fields=["stock"])

        PackInstance.objects.bulk_create(
            [
                PackInstance(
                    pack=pack,
                    discord_id=discord_id,
                    purchased_by_discord_id=discord_id,
                    source=PackInstance.Source.SHOP,
                )
                for _ in range(amount)
            ]
        )

    return BuyOutcome(pack=pack, bought=amount, total_cost=total_cost, new_balance=new_balance)


def get_pool_preview(pack: Pack, limit: int = 10) -> PoolPreview:
    balls, weights = get_pack_pool(pack)
    total = sum(weights)
    rows = sorted(
        ((ball, weight / total) for ball, weight in zip(balls, weights, strict=True)),
        key=lambda item: item[1],
        reverse=True,
    )
    return PoolPreview(pack=pack, total_balls=len(balls), rows=rows[:limit])
