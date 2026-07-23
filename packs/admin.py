from django.contrib import admin
from .models import Pack, PackInstance


@admin.register(Pack)
class PackAdmin(admin.ModelAdmin):
    list_display = ("name", "type", "min_rarity", "max_rarity")
    search_fields = ("name", "type")


@admin.register(PackInstance)
class PackInstanceAdmin(admin.ModelAdmin):
    autocomplete_fields = ("pack",)
    list_display = ("pack", "discord_id", "is_opened", "last_claim_date")