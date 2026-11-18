from django.contrib import admin
from django.utils.html import format_html

from .models import Pack, PackClaim, PackEntry, PackInstance


class PackEntryInline(admin.TabularInline):
    model = PackEntry
    extra = 0
    autocomplete_fields = ("ball",)
    fields = ("ball", "weight")
    ordering = ("-weight", "ball__country")


@admin.register(Pack)
class PackAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "type",
        "min_rarity",
        "max_rarity",
        "price",
        "stock",
        "cooldown_seconds",
        "available",
        "enabled",
    )
    list_filter = ("enabled", "allow_specials")
    search_fields = ("name", "type", "description")
    list_editable = ("enabled",)
    inlines = (PackEntryInline,)
    save_on_top = True
    fieldsets = (
        (None, {"fields": ("name", "type", "description", "enabled", "allow_specials")}),
        (
            "Drops",
            {
                "description": (
                    "If this pack has entries, they replace the rarity range below. "
                    "Otherwise balls are drawn from enabled balls within the rarity range, "
                    "weighted by their rarity."
                ),
                "fields": ("min_rarity", "max_rarity"),
            },
        ),
        (
            "Availability",
            {
                "fields": (
                    "cooldown_seconds",
                    "price",
                    "stock",
                    "purchase_limit",
                    "starts_at",
                    "ends_at",
                )
            },
        ),
    )

    @admin.display(boolean=True, description="Available")
    def available(self, obj: Pack) -> bool:
        return obj.available


@admin.register(PackEntry)
class PackEntryAdmin(admin.ModelAdmin):
    list_display = ("pack", "ball", "weight")
    list_filter = ("pack",)
    search_fields = ("pack__name", "pack__type", "ball__country")
    autocomplete_fields = ("pack", "ball")


@admin.register(PackInstance)
class PackInstanceAdmin(admin.ModelAdmin):
    autocomplete_fields = ("pack",)
    list_display = (
        "pack",
        "owner",
        "claimed_by_discord_id",
        "purchased_by_discord_id",
        "source",
        "is_opened",
        "acquired_at",
        "last_claim_date",
    )
    list_filter = ("is_opened", "source", "pack")
    search_fields = (
        "discord_id",
        "claimed_by_discord_id",
        "purchased_by_discord_id",
        "pack__name",
        "pack__type",
    )
    date_hierarchy = "acquired_at"
    readonly_fields = ("acquired_at", "opened_at")

    @admin.display(description="Owner")
    def owner(self, obj: PackInstance) -> str:
        return format_html("<code>{}</code>", obj.discord_id)


@admin.register(PackClaim)
class PackClaimAdmin(admin.ModelAdmin):
    autocomplete_fields = ("pack",)
    list_display = ("pack", "discord_id", "last_claim_date")
    list_filter = ("pack",)
    search_fields = ("discord_id", "pack__name", "pack__type")
    date_hierarchy = "last_claim_date"
    readonly_fields = ("last_claim_date",)

    def has_add_permission(self, request):
        return False
