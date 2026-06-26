
from django.db import models

class Pack(models.Model):
    id = models.BigAutoField(primary_key=True)
    kind = models.CharField(max_length=100, help_text="Type of the pack.")
    discord_id = models.BigIntegerField(unique=True, help_text="Discord user ID")
