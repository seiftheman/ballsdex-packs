from __future__ import annotations

import asyncio
import inspect
import logging
from typing import TYPE_CHECKING, Any

import discord
from asgiref.sync import sync_to_async
from discord import app_commands
from discord.ext import commands
from 

from ..models import Pack
from settings.models import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.packs")

class Packs(commands.GroupCog):
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @app_commands.command()
    @app_commands.checks.cooldown(1, 20, key=lambda i: i.user.id)
    async def daily(self, interaction: discord.Interaction):
        """Obtain a daily pack that contains a random countryball."""
        await interaction.response.defer()
        
        try:
            pack, created = await sync_to_async(Pack.objects.get_or_create)(
                discord_id=interaction.user.id
            )
            await interaction.followup.send(content="You just claimed a ** Daily Pack**!")
        except Exception as e:
            log.error(f"Error in daily command: {e}", exc_info=True)
            await interaction.followup.send(
                "An error occurred while processing your daily pack.",
                ephemeral=True
            )
        