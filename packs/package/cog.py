from __future__ import annotations

import asyncio
import inspect
import logging
import random
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands
from discord.ext import commands
from bd_models.models import Ball, BallInstance, Player
from settings.models import settings
from ..models import Pack

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.packs")

class PackCog(commands.GroupCog, name="pack"):
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @app_commands.command()
    @app_commands.checks.cooldown(1, 86400, key=lambda i: i.user.id)
    async def daily(self, interaction: discord.Interaction):
        """Obtain a daily pack that contains a random countryball."""
        await interaction.response.defer()
        await Pack.objects.acreate(discord_id=interaction.user.id, kind="daily")
        await interaction.followup.send("You just claimed a daily pack!")

    @app_commands.command()
    @app_commands.checks.cooldown(1, 604800, key=lambda i: i.user.id)
    async def weekly(self, interaction: discord.Interaction):
        """Obtain a weekly pack that contains a random countryball."""
        await interaction.response.defer()
        await Pack.objects.acreate(discord_id=interaction.user.id, kind="weekly")
        await interaction.followup.send("You just claimed a weekly pack!")
    
class PackCog(commands.GroupCog, name="pack"):
    @app_commands.command()
    @app_commands.choices(
    pack=[
        app_commands.Choice(name="Daily", value="daily"),
        app_commands.Choice(name="Weekly", value="weekly"),
    ]
    )
    async def open(self, interaction: discord.Interaction, pack: app_commands.Choice[str], amount: int = 1):
        """Open a pack to obtain a random countryball."""
        await interaction.response.defer()
        pack_qs = Pack.objects.filter(discord_id=interaction.user.id, kind=pack.value)
        pack_count = await pack_qs.acount()
        if pack_count == 0:
             await interaction.followup.send("You don't have any packs to open!")
             return

        if amount > pack_count:
             await interaction.followup.send(
                 f"You only have {pack_count} {pack.value} pack(s) to open."
             )
             return

         pack_ids = [pid async for pid in pack_qs.values_list("id", flat=True)[:amount]]
         await Pack.objects.filter(id__in=pack_ids).adelete()

         player, created = await Player.objects.aget_or_create(discord_id=interaction.user.id)
         balls = [ball async for ball in Ball.objects.all()]
        
         results = []
         any_new = False
         for _ in range(amount):
             ball = random.choice(balls)
             is_new = not await BallInstance.objects.filter(player=player, ball=ball).aexists()
             if is_new:
                 any_new = True

             attack_bonus = random.randint(-settings.max_attack_bonus, settings.max_attack_bonus)
             health_bonus = random.randint(-settings.max_health_bonus, settings.max_health_bonus)

             instance = await BallInstance.objects.acreate(
                 ball=ball,
                 player=player,
                 attack_bonus=attack_bonus,
                 health_bonus=health_bonus,
             )

             results.append(
                 f"**{instance.ball.country}!** ``({instance.pk:0X}, {attack_bonus:+d}%/{health_bonus:+d}%)``"
             )

        message = (
            f"**{pack.value.capitalize()} Pack**\n"
            f"{interaction.user.mention} You packed {results}"
        )
        if any_new:
            message += f"{instance.ball.country} is a **new {settings.collectible_name}** that has been added to your completion!"
        
        await interaction.followup.send(message)
