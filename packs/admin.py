from django.contrib import admin
from .models import Pack, PackInstance


@admin.register(Pack)
class PackAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "min_rarity", "max_rarity")


@admin.register(PackInstance)
class PackInstanceAdmin(admin.ModelAdmin):
    list_display = ("type", "discord_id", "is_opened", "last_claim_date")