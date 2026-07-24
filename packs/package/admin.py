from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from ballsdex.core.utils import checks
from packs.models import Pack, PackInstance
from .cog import type_autocomplete

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


class PackAdmin(commands.Cog):
    """Pack administration commands."""

    def __init__(self, bot: BallsDexBot):
        self.bot = bot

        admin_group = self.bot.get_command("admin")
        if admin_group:
            admin_group.add_command(self.pack)

    @commands.hybrid_group(name="pack")
    @checks.has_permissions("bd_models.add_ballinstance")
    async def pack(self, ctx: commands.Context[BallsDexBot]):
        """Pack administration commands."""
        await ctx.send_help(ctx.command)

    @pack.command(name="give")
    @checks.has_permissions("bd_models.add_ballinstance")
    @app_commands.autocomplete(type=type_autocomplete)
    @app_commands.describe(
        type="Type of the pack you want to give.",
        user="User you want to give packs to.",
        amount="Amount of packs you want to give.",
    )
    async def give(
        self,
        ctx: commands.Context[BallsDexBot],
        type: str,
        user: discord.User,
        amount: int = 1,
    ):
        """Give packs to a user."""
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
                pack=pack,
            )

        await ctx.send(
            f"{amount} {pack.type} pack{'s' if amount != 1 else ''} "
            f"have{' ' if amount != 1 else ' '}been given to {user.mention}.",
            ephemeral=True,
        )

    @pack.command(name="setrarity")
    @checks.has_permissions("bd_models.add_ballinstance")
    @app_commands.autocomplete(type=type_autocomplete)
    @app_commands.describe(
        type="Type of the pack to set rarity to.",
        min="Minimum rarity for balls from this pack.",
        max="Maximum rarity for balls from this pack.",
    )
    async def set_rarity(
        self,
        ctx: commands.Context[BallsDexBot],
        type: str,
        min: float,
        max: float,
    ):
        """Set the rarity range of balls dropped from a specific pack type."""
        if min < 0 or max < 0:
            await ctx.send("Sorry, rarity values must be 0 or greater.", ephemeral=True)
            return

        if min > max:
            await ctx.send(
                "Sorry, minimum rarity cannot be higher than maximum rarity.",
                ephemeral=True,
            )
            return

        updated = await Pack.objects.filter(type=type.lower()).aupdate(
            min_rarity=min,
            max_rarity=max,
        )

        if not updated:
            await ctx.send(f"Pack type `{type}` does not exist.", ephemeral=True)
            return

        await ctx.send(
            f"Done, I have updated the rarity range of the balls packed from the {type} pack to {min} - {max}.",
            ephemeral=True,
        )
