from __future__ import annotations

import asyncio
import inspect
import logging
import random
from datetime import timedelta
from django.utils import timezone
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

    async def _can_claim(self, discord_id: int, type: str, cooldown: timedelta) -> tuple[bool, float]:
        """
        Returns (can_claim, seconds_remaining)
        """
        latest = await Pack.objects.filter(discord_id=discord_id, type=type, last_claim_date__isnull=False,).order_by("-last_claim_date").afirst()
        if not latest:
            return True, 0.0
        delta = timezone.now() - latest.last_claim_date
        if delta >= cooldown:
            return True, 0.0
        remaining = (cooldown - delta).total_seconds()
        return False, remaining
    
    @app_commands.command()
    async def daily(self, interaction: discord.Interaction):
        """Obtain a daily pack that contains a random countryball."""
        await interaction.response.defer()
        can, rem = await self._can_claim(interaction.user.id, "daily", timedelta(days=1))
        if not can:
            await interaction.followup.send(f"You've already claimed a daily pack. Try again in {int(rem)}s.", ephemeral=True)
            return
        await Pack.objects.acreate(discord_id=interaction.user.id, type="daily", last_claim_date=timezone.now())
        await interaction.followup.send("You just claimed a daily pack!")

    @app_commands.command()
    async def weekly(self, interaction: discord.Interaction):
        """Obtain a weekly pack that contains a random countryball."""
        await interaction.response.defer()
        can, rem = await self._can_claim(interaction.user.id, "weekly", timedelta(days=7))
        if not can:
            await interaction.followup.send(
                f"You've already claimed a weekly pack. Try again in {int(rem)}s.",
                ephemeral=True,
            )
            return
        await Pack.objects.acreate(
            discord_id=interaction.user.id,
            type="weekly",
            last_claim_date=timezone.now(),
        )
        await interaction.followup.send("You just claimed a weekly pack!")
    
    @app_commands.command()
    async def list(self, interaction: discord.Interaction):
        """View a list of your owned packs."""
        await interaction.response.defer()
        daily_count = await Pack.objects.filter(discord_id=interaction.user.id, type="daily").acount()
        weekly_count = await Pack.objects.filter(discord_id=interaction.user.id, type="weekly").acount()
        if daily_count > 0 and weekly_count == 0:
            await interaction.followup.send(f"Daily Packs: {daily_count}")   
        elif weekly_count > 0 and daily_count == 0:
            await interaction.followup.send(f"Weekly Packs: {weekly_count}")  
        elif daily_count > 0 and weekly_count > 0:
            await interaction.followup.send(f"Daily Packs: {daily_count}, Weekly Packs: {weekly_count}")
        else:
            await interaction.followup.send("You don't have any packs yet.")
    
    @app_commands.command()
    @app_commands.choices(
        type=[
            app_commands.Choice(name="Daily", value="daily"),
            app_commands.Choice(name="Weekly", value="weekly"),
        ]
    )
    @app_commands.describe(
        type="Type of the pack you want to open.",
        amount="Amount of packs you want to open."
    )
    async def open(self, interaction: discord.Interaction, type: app_commands.Choice[str], amount: int = 1):
        """Open any of your owned packs."""
        await interaction.response.defer()
        pack_qs = Pack.objects.filter(discord_id=interaction.user.id, type=type.value)
        pack_count = await pack_qs.acount()
        if pack_count == 0:
            await interaction.followup.send("You don't have any packs yet.", ephemeral=True)
            return

        if amount > pack_count:
            await interaction.followup.send(
                f"You only have {pack_count} {type.value} pack(s) to open.",
                ephemeral=True
            )
            return

        pack_ids = [pid async for pid in pack_qs.values_list("id", flat=True)[:amount]]
        await Pack.objects.filter(id__in=pack_ids).adelete()

        player, created = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        balls = [ball async for ball in Ball.objects.all()]

        results = []
        any_new = False
        new_balls = []
        for _ in range(amount):
            ball = random.choice(balls)
            is_new = not await BallInstance.objects.filter(player=player, ball=ball).aexists()
            if is_new:
                any_new = True
                new_balls.append(ball.country)

            attack_bonus = random.randint(-settings.max_attack_bonus, settings.max_attack_bonus)
            health_bonus = random.randint(-settings.max_health_bonus, settings.max_health_bonus)

            instance = await BallInstance.objects.acreate(
                ball=ball,
                player=player,
                attack_bonus=attack_bonus,
                health_bonus=health_bonus,
            )

            results.append(
                f"**{instance.ball.country}** ``({instance.pk:0X}, {attack_bonus:+d}%/{health_bonus:+d}%)``"
            )
        
        message = (
            f"**{type.value.capitalize()} Pack**\n"
            f"{interaction.user.mention} You packed {', '.join(results)}!"
        )
        if any_new:
                if len(new_balls) == 1:
                    new_names = new_balls[0]
                    message += (
                        f"\n\nThis is a **new {settings.collectible_name}** "
                        "that has been added to your completion!"
                    )
                elif len(new_balls) == 2:
                    new_names = f"{new_balls[0]} and {new_balls[1]}"
                    message += (
                        f"\n\n{new_names} are new "
                        f"{settings.plural_collectible_name} that have been added to your completion!"
                    )
                else:
                    new_names = ", ".join(new_balls[:-1]) + f", and {new_balls[-1]}"
                    message += (
                        f"\n\n{new_names} are new "
                        f"{settings.plural_collectible_name} that have been added to your completion!"
                    )

        await interaction.followup.send(message)
