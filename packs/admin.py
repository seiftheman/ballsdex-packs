from django.contrib import admin

from .models import Pack, PackInstance


@admin.register(Pack)
class PackAdmin(admin.ModelAdmin):
    pass

@admin.register(PackInstance)
class PackInstanceAdmin(admin.ModelAdmin):
    pass