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
from packs.models import Pack

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.packs")

class PackCog(commands.GroupCog, name="pack"):
    """Pack commands."""
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    admin = app_commands.Group(name="admin", description="Pack administration commands.")

    DEFAULT_PACK_RARITY: dict[str, tuple[float | None, float | None]] = {}

    def admin_permissions_check():
        """Custom permission check for admin commands that works with interactions."""
        async def check(interaction: discord.Interaction["BallsDexBot"]) -> bool:
            from users.utils import get_user_model
            
            try:
                user_model = get_user_model()
                dj_user = await user_model.objects.filter(discord_id=interaction.user.id).aget()
                if not dj_user.is_active:
                    return False
                # Since packs give collectibles, you gonna need "Add BallInstance" permission.
                return await dj_user.ahas_perms(["bd_models.add_ballinstance"])
            except user_model.DoesNotExist:
                return False
        return app_commands.check(check)
    
    def _default_pack_rarity(self, pack_type: str) -> tuple[float | None, float | None]:
        return self.DEFAULT_PACK_RARITY.get(pack_type, (None, None))

    async def _create_pack(self, discord_id: int, type: str, last_claim_date=None) -> Pack:
        min_rarity, max_rarity = self._default_pack_rarity(type)
        return await Pack.objects.acreate(
            discord_id=discord_id,
            type=type,
            last_claim_date=last_claim_date,
            min_rarity=min_rarity,
            max_rarity=max_rarity,
        )
    
    async def _can_claim(self, discord_id: int, type: str, cooldown: timedelta) -> tuple[bool, float]:
        latest = await Pack.objects.filter(discord_id=discord_id, type=type, last_claim_date__isnull=False,).order_by("-last_claim_date").afirst()
        if not latest:
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
    
    @app_commands.command()
    async def daily(self, interaction: discord.Interaction):
        """Obtain a daily pack that contains a random countryball."""
        can, rem = await self._can_claim(interaction.user.id, "daily", timedelta(days=1))
        if not can:
            await interaction.response.send_message(f"You have already claimed a daily pack. Try again in {self._format_seconds(rem)}.", ephemeral=True)
            return
        await self._create_pack(interaction.user.id, "daily", last_claim_date=timezone.now())
        await interaction.response.send_message("You just claimed a daily pack!")

    @app_commands.command()
    async def weekly(self, interaction: discord.Interaction):
        """Obtain a weekly pack that contains a random countryball."""
        can, rem = await self._can_claim(interaction.user.id, "weekly", timedelta(days=7))
        if not can:
            await interaction.response.send_message(
                f"You have already claimed a weekly pack. Try again in {self._format_seconds(rem)}.",
                ephemeral=True,
            )
            return
        await self._create_pack(interaction.user.id, "weekly", last_claim_date=timezone.now())
        await interaction.response.send_message("You just claimed a weekly pack!")
    
    @app_commands.command()
    async def list(self, interaction: discord.Interaction):
        """View a list of your owned packs."""
        daily_count = await Pack.objects.filter(discord_id=interaction.user.id, type="daily", is_opened=False).acount()
        weekly_count = await Pack.objects.filter(discord_id=interaction.user.id, type="weekly", is_opened=False).acount()
        if daily_count > 0 and weekly_count == 0:
            await interaction.response.send_message(f"Daily Packs: {daily_count}")   
        elif weekly_count > 0 and daily_count == 0:
            await interaction.response.send_message(f"Weekly Packs: {weekly_count}")  
        elif daily_count > 0 and weekly_count > 0:
            await interaction.response.send_message(f"Daily Packs: {daily_count}\nWeekly Packs: {weekly_count}")
        else:
            await interaction.response.send_message("You don't have any packs yet.", ephemeral=True)
    
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
        pack_objs = [pack async for pack in Pack.objects.filter(discord_id=interaction.user.id, type=type.value, is_opened=False).order_by("last_claim_date")]
        if not pack_objs:
            await interaction.followup.send("You do not have any packs yet.")
            return

        if amount > len(pack_objs):
            await interaction.followup.send(
                f"You only have {len(pack_objs)} {type.value} pack(s) to open."
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
        
        await Pack.objects.filter(pk__in=[pack.pk for pack in packs_to_consume]).aupdate(is_opened=True)
        
        message = (
            f"**{type.value.capitalize()} Pack**\n"
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
    @app_commands.choices(
        type=[
            app_commands.Choice(name="Daily", value="daily"),
            app_commands.Choice(name="Weekly", value="weekly"),
        ]
    )
    @app_commands.describe(
        type="Type of the pack you want to open.",
        user="User you want to give packs to.",
        amount="Amount of packs you want to open."
    )
    async def give(self, interaction: discord.Interaction, type: app_commands.Choice[str], user: discord.User, amount: int = 1):
        """Give packs to another user."""
        await interaction.response.defer()
        if user.bot:
            await interaction.followup.send("You cannot give packs to bots.")
            return

        if user.id == interaction.user.id:
            await interaction.followup.send("You cannot give packs to yourself.")
            return

        pack_qs = Pack.objects.filter(discord_id=interaction.user.id, type=type.value, is_opened=False)
        pack_count = await pack_qs.acount()
        if pack_count == 0:
            await interaction.followup.send("You don't have any packs yet.")
            return

        if amount > pack_count:
            await interaction.followup.send(
                f"You only have {pack_count} {type.value} pack(s) to give."
            )
            return

        all_pks = [pk async for pk in pack_qs.order_by("last_claim_date").values_list('pk', flat=True)]
        packs_to_give = all_pks[:amount]
        
        await Pack.objects.filter(pk__in=packs_to_give).aupdate(discord_id=user.id)

        if amount == 1:
            await interaction.followup.send(
                f"You have given {amount} {type.value} pack to {user.mention}!"
            )
        else:
            await interaction.followup.send(
                f"You have given {amount} {type.value} packs to {user.mention}!"
            )

    @admin.command()
    @admin_permissions_check()
    @app_commands.describe(
        type="Type of the pack you want to give.",
        user="User you want to give packs to.",
        amount="Amount of packs you want to give."
    )
    @app_commands.choices(
        type=[
            app_commands.Choice(name="Daily", value="daily"),
            app_commands.Choice(name="Weekly", value="weekly"),
        ]
    )
    async def give(self, interaction: discord.Interaction, type: app_commands.Choice[str], user: discord.User, amount: int = 1):
        """Give packs to a user."""
        await interaction.response.defer(ephemeral=True)
        if user.bot:
            await interaction.followup.send("Sorry, you cannot give packs to bots.")
            return

        if amount <= 0:
            await interaction.followup.send("Sorry, amount must be greater than 0.")
            return

        for _ in range(amount):
            # I don't think last_claim_date should be added since the pack(s) is(are) admin-given, should it?
            await Pack.objects.acreate(discord_id=user.id, type=type.value)

        if amount == 1:
            await interaction.followup.send(
                f"{amount} {type.value} pack has been given to {user.mention}."
            )
        else:
            await interaction.followup.send(
                f"{amount} {type.value} packs have been given to {user.mention}."
            )

    @admin.command()
    @admin_permissions_check()
    @app_commands.describe(
        type="Type of the pack to set rarity to.",
        min="Minimum rarity for balls from this pack.",
        max="Maximum rarity for balls from this pack."
    )
    @app_commands.choices(
        type=[
            app_commands.Choice(name="Daily", value="daily"),
            app_commands.Choice(name="Weekly", value="weekly"),
        ]
    )
    async def set_rarity(self, interaction: discord.Interaction, type: app_commands.Choice[str], min: float, max: float):
        """Set rarity range of the balls packed from a pack."""
        await interaction.response.defer(ephemeral=True)

        if min < 0 or max < 0:
            await interaction.followup.send("Sorry, rarity values must be 0 or greater.")
            return

        if min > max:
            await interaction.followup.send("Sorry, minimum rarity cannot be higher than maximum rarity.")
            return

        self.DEFAULT_PACK_RARITY[type.value] = (min, max)
        await Pack.objects.filter(type=type.value, is_opened=False).aupdate(
            min_rarity=min, max_rarity=max
        )

        await interaction.followup.send(
            f" Done, I have updated the rarity range of the balls packed from the {type.value} pack to {min} to {max}."
        )
