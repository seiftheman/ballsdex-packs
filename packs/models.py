from django.db import models

class Pack(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=100, default="Unnamed Pack", help_text="Name of the pack.", unique=True)
    type = models.CharField(max_length=100, help_text="Type of the pack.", unique=True)
    min_rarity = models.FloatField(
        null=True,
        blank=True,
        help_text="Minimum rarity for balls in this pack."
    )
    max_rarity = models.FloatField(
        null=True,
        blank=True,
        help_text="Maximum rarity for balls in this pack."
    )
    def __str__(self):
        return self.name

class PackInstance(models.Model):
    id = models.BigAutoField(primary_key=True)
    type = models.CharField(max_length=100, help_text="Type of the pack.")
    discord_id = models.BigIntegerField(help_text="Discord user ID.")
    last_claim_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this pack was claimed (used for cooldown tracking)."
    )
    min_rarity = models.FloatField(
        null=True,
        help_text="Minimum rarity for balls in this pack."
    )
    max_rarity = models.FloatField(
        null=True,
        help_text="Maximum rarity for balls in this pack."
    )
    is_opened = models.BooleanField(
        default=False, 
        help_text="Whether this pack has already been opened."
    )
    def __str__(self):
        return f"{self.type} ({self.discord_id})"
