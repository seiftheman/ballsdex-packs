from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

SLUG_VALIDATOR = RegexValidator(
    r"^[a-z0-9_-]+$",
    "Pack types must contain only lowercase letters, numbers, hyphens and underscores.",
)


class Pack(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=100, default="Unnamed Pack", help_text="Name of the pack.")
    type = models.SlugField(
        max_length=100,
        unique=True,
        validators=(SLUG_VALIDATOR,),
        help_text=(
            "Type of the pack. Must be a lowercase slug (letters, numbers, hyphens and underscores). "
            "It is also used to build the legacy per-pack command name."
        ),
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text="Description shown in the shop and the pack info command.",
    )
    min_rarity = models.FloatField(
        null=True,
        blank=True,
        validators=(MinValueValidator(0),),
        help_text="Minimum rarity (spawn weight) for balls in this pack.",
    )
    max_rarity = models.FloatField(
        null=True,
        blank=True,
        validators=(MinValueValidator(0),),
        help_text="Maximum rarity (spawn weight) for balls in this pack.",
    )
    cooldown_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        default=None,
        help_text=(
            "Cooldown between free claims in seconds (e.g. 86400 for 1 day, 604800 for 1 week). "
            "Leave blank to disable free claims and make the pack shop-only."
        ),
    )
    price = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        help_text="Cost of the pack. If null, the pack cannot be purchased.",
    )
    stock = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Remaining packs available for free claims and purchases. If null, stock is unlimited.",
    )
    purchase_limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum number of times a user may purchase this pack. If null, there is no limit.",
    )
    starts_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the pack becomes available. If null, it is available immediately.",
    )
    ends_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the pack stops being available. If null, it never expires.",
    )
    allow_specials = models.BooleanField(
        default=True,
        help_text="Whether balls opened from this pack can roll an active special.",
    )
    enabled = models.BooleanField(default=True, help_text="Whether this pack is active.")

    class Meta:
        ordering = ("name",)
        constraints = (
            models.CheckConstraint(
                condition=(
                    Q(min_rarity__isnull=True)
                    | Q(max_rarity__isnull=True)
                    | Q(min_rarity__lte=F("max_rarity"))
                ),
                name="pack_rarity_range_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(starts_at__isnull=True)
                    | Q(ends_at__isnull=True)
                    | Q(starts_at__lte=F("ends_at"))
                ),
                name="pack_dates_valid",
            ),
        )

    def __str__(self) -> str:
        return f"{self.name} ({self.type})"

    @property
    def available(self) -> bool:
        """Whether the pack can currently be claimed or purchased."""
        if not self.enabled:
            return False
        now = timezone.now()
        if self.starts_at is not None and self.starts_at > now:
            return False
        if self.ends_at is not None and self.ends_at <= now:
            return False
        if self.stock is not None and self.stock <= 0:
            return False
        return True

    def clean(self) -> None:
        super().clean()
        if (
            self.min_rarity is not None
            and self.max_rarity is not None
            and self.min_rarity > self.max_rarity
        ):
            raise ValidationError({"max_rarity": "Maximum rarity cannot be lower than minimum rarity."})
        if self.starts_at is not None and self.ends_at is not None and self.starts_at > self.ends_at:
            raise ValidationError({"ends_at": "End date cannot be before the start date."})

    def save(self, *args, **kwargs):
        # Keep existing data usable even when it was created through the Django shell
        # rather than the admin form, which validates the slug.
        if self.type:
            self.type = self.type.strip().lower().replace(" ", "_")
        return super().save(*args, **kwargs)


class PackEntry(models.Model):
    """Optional curated drop entry. When a pack has entries, they replace the rarity pool."""

    id = models.BigAutoField(primary_key=True)
    pack = models.ForeignKey(Pack, on_delete=models.CASCADE, related_name="entries")
    ball = models.ForeignKey("bd_models.Ball", on_delete=models.CASCADE, related_name="pack_entries")
    weight = models.FloatField(
        default=1.0,
        validators=(MinValueValidator(0),),
        help_text="Relative weight of this ball in the pack. A weight of 0 removes it from the pool.",
    )

    class Meta:
        ordering = ("-weight", "ball__country")
        constraints = (
            models.UniqueConstraint(fields=("pack", "ball"), name="unique_pack_entry"),
        )

    def __str__(self) -> str:
        return f"{self.ball} in {self.pack.name}"


class PackClaim(models.Model):
    """Per-user pack state, used to enforce free-claim cooldowns atomically."""

    id = models.BigAutoField(primary_key=True)
    discord_id = models.BigIntegerField(db_index=True, help_text="Discord user ID.")
    pack = models.ForeignKey(Pack, on_delete=models.CASCADE, related_name="claims")
    last_claim_date = models.DateTimeField(help_text="When this pack was last claimed for free.")

    class Meta:
        ordering = ("-last_claim_date",)
        constraints = (
            models.UniqueConstraint(fields=("discord_id", "pack"), name="unique_pack_claim"),
        )

    def __str__(self) -> str:
        return f"{self.pack.type} claim for {self.discord_id}"


class PackInstance(models.Model):
    class Source(models.TextChoices):
        CLAIM = "claim", "Free claim"
        SHOP = "shop", "Shop purchase"
        ADMIN = "admin", "Admin grant"
        MIGRATION = "migration", "Migration"

    id = models.BigAutoField(primary_key=True)
    pack = models.ForeignKey(Pack, on_delete=models.PROTECT, related_name="instances")
    discord_id = models.BigIntegerField(db_index=True, help_text="Current owner's Discord user ID.")
    claimed_by_discord_id = models.BigIntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Discord user ID of the user who originally claimed this pack for free.",
    )
    purchased_by_discord_id = models.BigIntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Discord user ID of the user who purchased this pack. Does not change when gifted.",
    )
    source = models.CharField(
        max_length=16,
        choices=Source.choices,
        default=Source.CLAIM,
        help_text="How this pack instance was obtained.",
    )
    acquired_at = models.DateTimeField(auto_now_add=True, help_text="When this pack was obtained.")
    last_claim_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this pack was claimed for free, if applicable.",
    )
    opened_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this pack was opened, if applicable.",
    )
    is_opened = models.BooleanField(default=False, help_text="Whether this pack has already been opened.")

    class Meta:
        ordering = ("-acquired_at", "-pk")
        indexes = (
            models.Index(fields=("discord_id", "is_opened"), name="pack_owner_opened_idx"),
            models.Index(fields=("discord_id", "pack", "is_opened"), name="pack_owner_pack_opened_idx"),
            models.Index(
                fields=("claimed_by_discord_id", "pack", "-last_claim_date"),
                name="pack_claim_cooldown_idx",
            ),
        )

    def __str__(self) -> str:
        return f"{self.pack.type} - {self.discord_id}"
