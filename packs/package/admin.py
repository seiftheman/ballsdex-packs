from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from ballsdex.core.utils import checks
from discord import app_commands
from discord.ext import commands

from packs.models import Pack, PackInstance

from .cog import type_autocomplete

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.packs")


class PackAdmin(commands.Cog):
    """Pack administration commands."""

    def __init__(self, bot: BallsDexBot):
        self.bot = bot
        self._attached = False

    async def cog_load(self) -> None:
        self._attach_to_admin()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        # Package load order is not guaranteed; the core admin cog may only be
        # available once the bot has finished loading every package.
        self._attach_to_admin()

    def _attach_to_admin(self) -> None:
        if self._attached:
            return
        admin_group = self.bot.get_command("admin")
        if admin_group is None:
            return
        if admin_group.get_command(self.pack.name) is None:
            admin_group.add_command(self.pack)
        self._attached = True

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
        amount="Amount of packs you want to give (1-100).",
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
        if amount < 1 or amount > 100:
            await ctx.send("Sorry, amount must be between 1 and 100.", ephemeral=True)
            return

        pack = await Pack.objects.filter(type=type.strip().lower()).afirst()
        if not pack:
            await ctx.send(f"Pack type `{type}` does not exist.", ephemeral=True)
            return

        await PackInstance.objects.abulk_create(
            [
                PackInstance(
                    discord_id=user.id,
                    pack=pack,
                    source=PackInstance.Source.ADMIN,
                )
                for _ in range(amount)
            ]
        )

        await ctx.send(
            f"{amount} {pack.name} pack{'s' if amount != 1 else ''} "
            f"{'have' if amount != 1 else 'has'} been given to {user.mention}.",
            ephemeral=True,
        )
        log.info(
            "%s (%s) gave %s %s packs to %s (%s)",
            ctx.author,
            ctx.author.id,
            amount,
            pack.type,
            user,
            user.id,
            extra={"webhook": True},
        )

    @pack.command(name="setrarity")
    @checks.has_permissions("bd_models.add_ballinstance")
    @app_commands.autocomplete(type=type_autocomplete)
    @app_commands.describe(
        type="Type of the pack to set the rarity range for.",
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

        updated = await Pack.objects.filter(type=type.strip().lower()).aupdate(
            min_rarity=min,
            max_rarity=max,
        )
        if not updated:
            await ctx.send(f"Pack type `{type}` does not exist.", ephemeral=True)
            return

        await ctx.send(
            f"Updated the rarity range of {type} packs to {min:g} - {max:g}.",
            ephemeral=True,
        )
        log.info(
            "%s (%s) set the rarity range of %s packs to %s-%s",
            ctx.author,
            ctx.author.id,
            type,
            min,
            max,
            extra={"webhook": True},
        )

    @pack.command(name="list")
    @checks.has_permissions("bd_models.add_ballinstance")
    async def list_packs(self, ctx: commands.Context[BallsDexBot]):
        """List configured packs and their current availability."""
        packs = [pack async for pack in Pack.objects.order_by("name")]
        if not packs:
            await ctx.send("No packs are configured.", ephemeral=True)
            return

        paginator = commands.Paginator(prefix="", suffix="")
        for pack in packs:
            paginator.add_line(
                f"- **{pack.name}** (`{pack.type}`) — "
                f"{'available' if pack.available else 'unavailable'}, "
                f"{f'{pack.cooldown_seconds}s cooldown' if pack.cooldown_seconds is not None else 'free claims disabled'}, "
                f"price={pack.price if pack.price is not None else 'free-only'}"
            )
        for page in paginator.pages:
            await ctx.send(page, ephemeral=True)

    @commands.command(name="reloadpacks")
    @checks.has_permissions("bd_models.add_ballinstance")
    async def reloadpacks(self, ctx: commands.Context[BallsDexBot]):
        """Reload and sync pack slash commands."""
        pack_cog = self.bot.get_cog("pack")
        if not pack_cog:
            await ctx.send("Pack cog is not loaded.")
            return

        async with ctx.typing():
            try:
                pack_cog.cog_unload()
                await pack_cog.cog_load()
                await self.bot.tree.sync()
            except Exception:
                log.exception("Failed to reload pack commands.")
                await ctx.send(
                    "Failed to reload pack commands. Check the logs for details.",
                    ephemeral=True,
                )
                return

        await ctx.send("Pack commands have been synced.")
        log.info(
            "%s (%s) reloaded pack commands",
            ctx.author,
            ctx.author.id,
            extra={"webhook": True},
        )
