from __future__ import annotations

import asyncio
import inspect
import logging
import random
from datetime import timedelta
from typing import TYPE_CHECKING, Any

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
        admin_group = self.bot.get_command("admin")
        if admin_group:
            admin_group.add_command(self.pack_admin)

    def admin_permissions_check():
        """Custom permission check for admin commands that works with interactions."""

        async def check(interaction: discord.Interaction[BallsDexBot]) -> bool:
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

    async def _can_claim(
        self, discord_id: int, type: str, cooldown: timedelta
    ) -> tuple[bool, float]:
        latest = (
            await PackInstance.objects.filter(
                discord_id=discord_id,
                type=type,
                last_claim_date__isnull=False,
            )
            .order_by("-last_claim_date")
            .afirst()
        )
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

    @commands.hybrid_group(name="pack")
    @checks.has_permissions("bd_models.add_ballinstance")
    async def pack_admin(self, ctx: commands.Context[BallsDexBot]):
        """
        Pack administration commands.
        """
        await ctx.send_help(ctx.command)

    @pack_admin.command(name="give")
    @checks.has_permissions("bd_models.add_ballinstance")
    @app_commands.describe(
        type="Type of the pack you want to open.",
        user="User you want to give packs to.",
        amount="Amount of packs you want to open.",
    )
    async def pack_give(
        self,
        ctx: commands.Context[BallsDexBot],
        type: str,
        user: discord.User,
        amount: int = 1,
    ):
        """Give packs to another user."""
        if user.bot:
            await ctx.send("Sorry, you cannot give packs to bots.", ephemeral=True)
            return

        if amount <= 0:
            await ctx.send("Sorry, amount must be greater than 0.", ephemeral=True)
            return

        pack = await Pack.objects.filter(type=type.lower()).afirst()
        if not pack:
            await ctx.send(f"Pack type `{type}` does not exist.", ephemeral=True)
            return

        for _ in range(amount):
            await PackInstance.objects.acreate(
                discord_id=user.id,
                type=pack.type,
                min_rarity=pack.min_rarity,
                max_rarity=pack.max_rarity,
            )

        if amount == 1:
            await ctx.send(
                f"1 {pack.type} pack has been given to {user.mention}.",
                ephemeral=True,
            )
        else:
            await ctx.send(
                f"{amount} {pack.type} packs have been given to {user.mention}.",
                ephemeral=True,
            )

    @pack_admin.command(name="setrarity")
    @checks.has_permissions("bd_models.add_ballinstance")
    @app_commands.describe(
        pack_type="Type of the pack to set rarity for.",
        min_rarity="Minimum rarity threshold.",
        max_rarity="Maximum rarity threshold.",
    )
    async def pack_set_rarity(
        self,
        ctx: commands.Context[BallsDexBot],
        pack_type: str,
        min_rarity: float,
        max_rarity: float,
    ):
        """Set the rarity range of balls dropped from a specific pack type."""
        if min_rarity < 0 or max_rarity < 0:
            await ctx.send("Sorry, rarity values must be 0 or greater.", ephemeral=True)
            return

        if min_rarity > max_rarity:
            await ctx.send(
                "Sorry, minimum rarity cannot be higher than maximum rarity.", ephemeral=True
            )
            return

        updated = await Pack.objects.filter(type=pack_type.lower()).aupdate(
            min_rarity=min_rarity, max_rarity=max_rarity
        )

        if not updated:
            await ctx.send(f"Pack type `{pack_type}` does not exist.", ephemeral=True)
            return

        await ctx.send(
            f"Done, I have updated the rarity range of the balls packed from the {pack_type} pack to {min_rarity} - {max_rarity}.",
            ephemeral=True,
        )

    @app_commands.command()
    async def daily(self, interaction: discord.Interaction):
        """Obtain a daily pack that contains a random countryball."""
        can, rem = await self._can_claim(interaction.user.id, "daily", timedelta(days=1))
        if not can:
            await interaction.response.send_message(
                f"You have already claimed a daily pack. Try again in {self._format_seconds(rem)}.",
                ephemeral=True,
            )
            return
        daily_pack = await Pack.objects.filter(type="daily").afirst()
        await PackInstance.objects.acreate(
            discord_id=interaction.user.id,
            type=daily_pack.type,
            last_claim_date=timezone.now(),
            min_rarity=daily_pack.min_rarity,
            max_rarity=daily_pack.max_rarity,
        )
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
        weekly_pack = await Pack.objects.filter(type="weekly").afirst()
        await PackInstance.objects.acreate(
            discord_id=interaction.user.id,
            type="weekly",
            last_claim_date=timezone.now(),
            min_rarity=weekly_pack.min_rarity,
            max_rarity=weekly_pack.max_rarity,
        )
        await interaction.response.send_message("You just claimed a weekly pack!")

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
    @app_commands.choices(
        type=[
            app_commands.Choice(name="Daily", value="daily"),
            app_commands.Choice(name="Weekly", value="weekly"),
        ]
    )
    @app_commands.describe(
        type="Type of the pack you want to open.", amount="Amount of packs you want to open."
    )
    async def open(
        self, interaction: discord.Interaction, type: app_commands.Choice[str], amount: int = 1
    ):
        """Open any of your owned packs."""
        await interaction.response.defer()
        pack_objs = [
            pack
            async for pack in PackInstance.objects.filter(
                discord_id=interaction.user.id, type=type.value, is_opened=False
            ).order_by("last_claim_date")
        ]
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

        await PackInstance.objects.filter(pk__in=[pack.pk for pack in packs_to_consume]).aupdate(
            is_opened=True
        )

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
        amount="Amount of packs you want to open.",
    )
    async def give(
        self,
        interaction: discord.Interaction,
        type: app_commands.Choice[str],
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
            discord_id=interaction.user.id, type=type.value, is_opened=False
        )
        pack_count = await pack_qs.acount()
        if pack_count == 0:
            await interaction.followup.send("You don't have any packs yet.")
            return

        if amount > pack_count:
            await interaction.followup.send(
                f"You only have {pack_count} {type.value} pack(s) to give."
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
                f"You have given {amount} {type.value} pack to {user.mention}!"
            )
        else:
            await interaction.followup.send(
                f"You have given {amount} {type.value} packs to {user.mention}!"
            )


async def setup(bot: BallsDexBot) -> None:
    await Pack.objects.aupdate_or_create(type="daily", defaults={"name": "Daily"})
    await Pack.objects.aupdate_or_create(type="weekly", defaults={"name": "Weekly"})
    await bot.add_cog(PackCog(bot))