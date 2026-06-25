
from django.db import models

class Pack(models.Model):
    id = models.BigAutoField(primary_key=True)
    discord_id = models.BigIntegerField(unique=True, help_text="Discord user ID")
