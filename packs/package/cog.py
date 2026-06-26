from __future__ import annotations

import asyncio
import inspect
import logging
from random import random
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands
from discord.ext import commands
from bd_models.models import Ball, BallInstance, Player
from .models import Pack

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.packs")

class Packs(commands.GroupCog):
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    @app_commands.command()
    @app_commands.checks.cooldown(1, 86400, key=lambda i: i.user.id)
    async def daily(self, interaction: discord.Interaction):
        """Obtain a daily pack that contains a random countryball."""
        await interaction.response.defer()
        await Pack.create(discord_id=interaction.user.id, kind="daily")
        await interaction.followup.send("You just claimed a daily pack!")

    @app_commands.command()
    @app_commands.checks.cooldown(1, 604800, key=lambda i: i.user.id)
    async def weekly(self, interaction: discord.Interaction):
        """Obtain a weekly pack that contains a random countryball."""
        await interaction.response.defer()
        await Pack.create(discord_id=interaction.user.id, kind="weekly")
        await interaction.followup.send("You just claimed a weekly pack!")
    
    @app_commands.command()
    @app_commands.choices(
    pack=[
        app_commands.Choice(name="Daily", value="daily"),
        app_commands.Choice(name="Weekly", value="weekly"),
    ]
    )
    async def open(self, interaction: discord.Interaction, pack: app_commands.Choice[str]):
        """Open a pack to obtain a random countryball."""
        await interaction.response.defer()
        if pack.value == "daily":
            pack = await Pack.filter(discord_id=interaction.user.id, kind="daily").afirst()
        elif pack.value == "weekly":
            pack = await Pack.filter(discord_id=interaction.user.id, kind="weekly").afirst()
        if not pack:
            await interaction.followup.send("You don't have any packs to open!")
            return
        await interaction.response.defer()

        player, created = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        balls = await Ball.objects.all()

        ball = random.choice(list(balls))
        attack_bonus = random.randint(-settings.max_attack_bonus, settings.max_attack_bonus)
        health_bonus = random.randint(-settings.max_health_bonus, settings.max_health_bonus)

        instance = await BallInstance.objects.acreate(
            ball=ball,
            player=player,
            attack_bonus=attack_bonus,
            health_bonus=health_bonus,
            special=False,
        )

        if pack.value == "daily":
            await interaction.followup.send(
                "**Daily Pack**\n"
                f"{interaction.user.mention} You packed **{ball.country}!** "
                f"``({instance.pk:0X}, {attack_bonus:+d}%/{health_bonus:+d}%)``\n\n"
                f"This is a **new {settings.collectible_name}** that has been added to your completion!"
            )
        elif pack.value == "weekly":
            await interaction.followup.send(
                "**Weekly Pack**\n"
                f"{interaction.user.mention} You packed **{ball.country}!** "
                f"``({instance.pk:0X}, {attack_bonus:+d}%/{health_bonus:+d}%)``\n\n"
                f"This is a **new {settings.collectible_name}** that has been added to your completion!"
            )
