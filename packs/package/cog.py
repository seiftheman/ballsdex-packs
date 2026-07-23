from __future__ import annotations

import asyncio
import inspect
import logging
import random
from datetime import timedelta
from typing import TYPE_CHECKING, Any, List

import discord
from discord import app_commands
from discord.ext import commands
from django.utils import timezone

from ballsdex.core.utils import checks
from ballsdex.core.utils.utils import is_staff
from bd_models.models import Ball, BallInstance, Player
from packs.models import Pack, PackInstance
from settings.models import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.packs")


class PackCog(commands.GroupCog, name="pack"):
    """Pack commands."""

    def __init__(self, bot: BallsDexBot):
        self.bot = bot
        self._registered_claim_commands: list[str] = []

    async def cog_load(self) -> None:
        async for pack in Pack.objects.filter(enabled=True):
            cmd = self._make_pack_command(pack)
            self.app_command.add_command(cmd)
            self._registered_claim_commands.append(cmd.name)

    def cog_unload(self) -> None:
        for name in self._registered_claim_commands:
            self.app_command.remove_command(name)
        self._registered_claim_commands = []

    def _make_pack_command(self, pack: Pack) -> app_commands.Command:
        cog = self

        async def callback(interaction: discord.Interaction) -> None:
            can, rem = await cog._can_claim(interaction.user.id, pack)
            if not can:
                await interaction.response.send_message(
                    f"You have already claimed a {pack.type} pack. Try again in {cog._format_seconds(rem)}.",
                    ephemeral=True,
                )
                return

            await PackInstance.objects.acreate(
                discord_id=interaction.user.id,
                type=pack.type,
                last_claim_date=timezone.now(),
                min_rarity=pack.min_rarity,
                max_rarity=pack.max_rarity,
            )
            await interaction.response.send_message(f"You just claimed a {pack.type} pack!")

        cmd_name = pack.type.lower().replace(" ", "_")
        callback.__name__ = cmd_name

        return app_commands.Command(
            name=cmd_name,
            description=f"Obtain a {pack.type} pack that contains a random countryball.",
            callback=callback,
        )

    async def _can_claim(
        self, discord_id: int, pack: Pack
    ) -> tuple[bool, float]:
        cooldown = timedelta(seconds=getattr(pack, "cooldown_seconds", 86400))
        latest = (
            await PackInstance.objects.filter(
                discord_id=discord_id,
                type=pack.type,
                last_claim_date__isnull=False,
            )
            .order_by("-last_claim_date")
            .afirst()
        )
        if not latest or latest.last_claim_date is None:
            return True, 0.0
        delta = timezone.now() - latest.last_claim_date
        if delta >= cooldown:
            return True, 0.0
        remaining = (cooldown - delta).total_seconds()
        return False, remaining

    def _format_seconds(self, seconds: float) -> str:
        total = int(seconds)
        days, rem = divmod(total, 86400)
        hours, remainder = divmod(rem, 3600)
        minutes, secs = divmod(remainder, 60)

        parts = []
        if days:
            parts.append(f"{days} day{'s' if days != 1 else ''}")
        if hours:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes:
            parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")

        if len(parts) == 1:
            return parts[0]
        return " and ".join(", ".join(parts).rsplit(", ", 1))

    async def type_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        packs = [
            p
            async for p in Pack.objects.filter(enabled=True)
            if current.lower() in p.type.lower() or current.lower() in p.name.lower()
        ]
        return [
            app_commands.Choice(name=p.name, value=p.type)
            for p in packs[:25]
        ]

    @app_commands.command()
    async def list(self, interaction: discord.Interaction):
        """View a list of your owned packs."""
        daily_count = await PackInstance.objects.filter(
            discord_id=interaction.user.id, type="daily", is_opened=False
        ).acount()
        weekly_count = await PackInstance.objects.filter(
            discord_id=interaction.user.id, type="weekly", is_opened=False
        ).acount()
        if daily_count > 0 and weekly_count == 0:
            await interaction.response.send_message(f"Daily Packs: {daily_count}")
        elif weekly_count > 0 and daily_count == 0:
            await interaction.response.send_message(f"Weekly Packs: {weekly_count}")
        elif daily_count > 0 and weekly_count > 0:
            await interaction.response.send_message(
                f"Daily Packs: {daily_count}\nWeekly Packs: {weekly_count}"
            )
        else:
            await interaction.response.send_message("You don't have any packs yet.", ephemeral=True)

    @app_commands.command()
    @app_commands.autocomplete(type=type_autocomplete)
    @app_commands.describe(
        type="Type of the pack you want to open.", amount="Amount of packs you want to open."
    )
    async def open(
        self, interaction: discord.Interaction, type: str, amount: int = 1
    ):
        """Open any of your owned packs."""
        await interaction.response.defer()
        pack_objs = [
            pack
            async for pack in PackInstance.objects.filter(
                discord_id=interaction.user.id, type=type, is_opened=False
            ).order_by("last_claim_date")
        ]
        if not pack_objs:
            await interaction.followup.send("You do not have any packs yet.")
            return

        if amount > len(pack_objs):
            await interaction.followup.send(
                f"You only have {len(pack_objs)} {type} pack(s) to open."
            )
            return

        packs_to_consume = pack_objs[:amount]
        player, created = await Player.objects.aget_or_create(discord_id=interaction.user.id)

        results = []
        any_new = False
        new_balls = []
        for pack in packs_to_consume:
            balls_query = Ball.objects.filter(enabled=True)
            if pack.min_rarity is not None:
                balls_query = balls_query.filter(rarity__gte=pack.min_rarity)
            if pack.max_rarity is not None:
                balls_query = balls_query.filter(rarity__lte=pack.max_rarity)

            balls = [ball async for ball in balls_query]

            weights = [ball.rarity for ball in balls]
            ball = random.choices(balls, weights=weights, k=1)[0]
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

        await PackInstance.objects.filter(pk__in=[pack.pk for pack in packs_to_consume]).aupdate(
            is_opened=True
        )

        message = (
            f"**{type.capitalize()} Pack**\n"
            f"{interaction.user.mention} You packed {', '.join(results)}!"
        )
        if any_new:
            if len(new_balls) == 1:
                new_name = new_balls[0]
                message += (
                    f"\n\n{new_name} is a **new {settings.collectible_name}** "
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

    @app_commands.command()
    @app_commands.autocomplete(type=type_autocomplete)
    @app_commands.describe(
        type="Type of the pack you want to give.",
        user="User you want to give packs to.",
        amount="Amount of packs you want to give.",
    )
    async def give(
        self,
        interaction: discord.Interaction,
        type: str,
        user: discord.User,
        amount: int = 1,
    ):
        """Give packs to another user."""
        await interaction.response.defer()
        if user.bot:
            await interaction.followup.send("You cannot give packs to bots.")
            return

        if user.id == interaction.user.id:
            await interaction.followup.send("You cannot give packs to yourself.")
            return

        pack_qs = PackInstance.objects.filter(
            discord_id=interaction.user.id, type=type, is_opened=False
        )
        pack_count = await pack_qs.acount()
        if pack_count == 0:
            await interaction.followup.send("You don't have any packs yet.")
            return

        if amount > pack_count:
            await interaction.followup.send(
                f"You only have {pack_count} {type} pack(s) to give."
            )
            return

        staff = await is_staff(interaction)
        if user is not None:
            if user.id in self.bot.blacklist and not staff:
                await interaction.followup.send(
                    "You cannot view the inventory of a blacklisted user.", ephemeral=True
                )
                return

        all_pks = [
            pk async for pk in pack_qs.order_by("last_claim_date").values_list("pk", flat=True)
        ]
        packs_to_give = all_pks[:amount]

        await PackInstance.objects.filter(pk__in=packs_to_give).aupdate(discord_id=user.id)

        if amount == 1:
            await interaction.followup.send(
                f"You have given {amount} {type} pack to {user.mention}!"
            )
        else:
            await interaction.followup.send(
                f"You have given {amount} {type} packs to {user.mention}!"
            )