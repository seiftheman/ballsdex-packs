from django.db import models

class Pack(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=100, default="Unnamed Pack", help_text="Name of the pack.")
    type = models.CharField(max_length=100, help_text="Type of the pack (in lowercase please).", unique=True)
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
    cooldown_seconds = models.IntegerField(
        default=86400,
        help_text="Cooldown between claims in seconds (e.g. 86400 for 1 day, 604800 for 1 week)."
    )
    enabled = models.BooleanField(default=True, help_text="Whether this pack is active.")

    def __str__(self):
        return f"{self.name} ({self.type})"

class PackInstance(models.Model):
    id = models.BigAutoField(primary_key=True)
    pack = models.ForeignKey(Pack, on_delete=models.CASCADE, related_name="instances", null=True)
    discord_id = models.BigIntegerField(help_text="Discord user ID.")
    last_claim_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this pack was claimed."
    )
    is_opened = models.BooleanField(
        default=False, 
        help_text="Whether this pack has already been opened."
    )

    def __str__(self):
        return f"{self.pack.type} - {self.discord_id}"
