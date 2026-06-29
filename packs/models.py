
from django.db import models

class Pack(models.Model):
    id = models.BigAutoField(primary_key=True)
    kind = models.CharField(max_length=100, help_text="Type of the pack.")
    discord_id = models.BigIntegerField(help_text="Discord user ID.")
    last_claim_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this pack was claimed (used for cooldown tracking)."
    )