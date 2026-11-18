from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from asgiref.sync import sync_to_async
from ballsdex.core.discord import LayoutView
from ballsdex.core.utils.menus import Menu, TextFormatter, TextSource
from ballsdex.core.utils.utils import is_staff
from bd_models.models import Player
from discord import app_commands, ui
from discord.ext import commands
from django.db.models import Count, Q
from settings.models import settings

from packs.models import Pack
from packs.package.ui import PackShopView
from packs.services import (
    ClaimOutcome,
    NoBalls,
    NotEnoughPacks,
    OutOfStock,
    PackClaimDisabled,
    PackCooldown,
    PackError,
    PackNotFound,
    PackUnavailable,
    claim_pack,
    get_pool_preview,
    give_packs,
    open_packs,
)

from .utils import format_duration, format_pack_currency, pack_command_name

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.packs")


def _format_instance_id(value: int | None) -> str:
    return f"{value:0X}" if value is not None else "?"


async def _type_choices(
    current: str, *, claimable_only: bool = False
) -> list[app_commands.Choice[str]]:
    current = current.lower()
    query = Pack.objects.filter(enabled=True)
    if claimable_only:
        query = query.filter(cooldown_seconds__isnull=False)
    choices: list[app_commands.Choice[str]] = []
    async for pack in query.order_by("name"):
        if current not in pack.name.lower() and current not in pack.type.lower():
            continue
        label = pack.name if pack.name.lower() == pack.type.lower() else f"{pack.name} ({pack.type})"
        if pack.cooldown_seconds is None:
            label += " (shop)"
        choices.append(app_commands.Choice(name=label[:100], value=pack.type))
        if len(choices) >= 25:
            break
    return choices


async def type_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    return await _type_choices(current)


async def claim_type_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    return await _type_choices(current, claimable_only=True)


class PackCog(commands.GroupCog, name="pack"):
    """Pack commands."""

    def __init__(self, bot: BallsDexBot):
        self.bot = bot
        self._registered_claim_commands: list[str] = []

    async def cog_load(self) -> None:
        self._registered_claim_commands.clear()
        seen: set[str] = set()
        max_dynamic = max(0, 25 - len(self.app_command.commands))
        async for pack in Pack.objects.filter(enabled=True, cooldown_seconds__isnull=False).order_by("name"):
            if len(self._registered_claim_commands) >= max_dynamic:
                log.warning("Skipping remaining pack claim commands: Discord's 25-command limit was reached.")
                break
            command_name = pack_command_name(pack.type)
            if command_name is None:
                log.warning(
                    "Skipping pack %r: %r is not a valid or available command name.",
                    pack.name,
                    pack.type,
                )
                continue
            if command_name in seen:
                log.warning(
                    "Skipping pack %r: command name %r is already registered.",
                    pack.name,
                    command_name,
                )
                continue
            seen.add(command_name)
            try:
                self.app_command.add_command(self._make_pack_command(pack, command_name))
            except Exception:
                log.exception("Failed to register claim command for pack %r.", pack.name)
                continue
            self._registered_claim_commands.append(command_name)

    def cog_unload(self) -> None:
        for name in self._registered_claim_commands:
            self.app_command.remove_command(name)
        self._registered_claim_commands.clear()

    def _make_pack_command(self, pack: Pack, command_name: str) -> app_commands.Command:
        @app_commands.checks.cooldown(1, 2, key=lambda i: i.user.id)
        async def callback(interaction: discord.Interaction) -> None:
            await self._claim_pack(interaction, pack)

        callback.__name__ = command_name
        return app_commands.Command(
            name=command_name,
            description=(f"Obtain a {pack.name} pack that contains a random collectible.")[:100],
            callback=callback,
        )

    async def _claim_pack(self, interaction: discord.Interaction, pack: Pack) -> None:
        # Claiming can briefly lock the pack row while another user claims the same
        # pack. Defer first so a slow database does not expire the interaction.
        await interaction.response.defer()
        try:
            outcome: ClaimOutcome = await sync_to_async(claim_pack)(interaction.user.id, pack.pk)
        except PackClaimDisabled as exc:
            await interaction.followup.send(
                f"Free claims are disabled for **{exc.pack.name}**. "
                "If it is sold in the shop, use `/pack shop` instead.",
                ephemeral=True,
            )
            return
        except PackCooldown as exc:
            await interaction.followup.send(
                f"You have already claimed a {exc.pack.name} pack. "
                f"Try again in {format_duration(exc.remaining)}.",
                ephemeral=True,
            )
            return
        except PackUnavailable as exc:
            await interaction.followup.send(
                f"**{exc.pack.name}** is not currently available.", ephemeral=True
            )
            return
        except OutOfStock as exc:
            await interaction.followup.send(f"**{exc.pack.name}** is out of stock.", ephemeral=True)
            return
        except PackError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        except Exception:
            log.exception("Failed to claim pack %s for %s", pack.pk, interaction.user.id)
            await interaction.followup.send(
                "Something went wrong while claiming your pack. Please try again.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"You just claimed a **{outcome.pack.name}** pack! "
            f"Use `/pack open {outcome.pack.type}` to open it."
        )
        log.info(
            "%s (%s) claimed a %s pack",
            interaction.user,
            interaction.user.id,
            outcome.pack.type,
            extra={"webhook": True},
        )

    def _paged_view(
        self, author_id: int, title: str, text: str
    ) -> tuple[LayoutView, Menu[str], ui.Container]:
        view = LayoutView(timeout=180)
        view.restrict_author(author_id)
        body = ui.TextDisplay("")
        container = ui.Container(
            ui.TextDisplay(f"## {title}"),
            ui.Separator(),
            body,
            accent_colour=discord.Colour.gold(),
        )
        view.add_item(container)
        menu = Menu(self.bot, view, TextSource(text), TextFormatter(body))
        return view, menu, container

    @app_commands.command()
    @app_commands.checks.cooldown(1, 5, key=lambda i: i.user.id)
    async def list(self, interaction: discord.Interaction):
        """View a list of your unopened packs."""
        packs = [
            pack
            async for pack in Pack.objects.annotate(
                unopened_count=Count(
                    "instances",
                    filter=Q(
                        instances__discord_id=interaction.user.id,
                        instances__is_opened=False,
                    ),
                )
            )
            .order_by("name")
        ]
        rows = [f"- **{pack.name}**: {pack.unopened_count}" for pack in packs if pack.unopened_count]
        if not rows:
            await interaction.response.send_message("You do not have any unopened packs.", ephemeral=True)
            return

        view, menu, container = self._paged_view(
            interaction.user.id, "Your packs", "\n".join(rows)
        )
        await menu.init(container=container)
        message = await interaction.response.send_message(view=view)
        view.original_message = message

    @app_commands.command()
    @app_commands.autocomplete(type=claim_type_autocomplete)
    @app_commands.describe(type="Type of the pack you want to claim.")
    async def claim(self, interaction: discord.Interaction, type: str):
        """Claim a free pack of the chosen type."""
        pack = await Pack.objects.filter(type=type.strip().lower()).afirst()
        if pack is None:
            await interaction.response.send_message(f"Pack type `{type}` does not exist.", ephemeral=True)
            return
        await self._claim_pack(interaction, pack)

    @app_commands.command()
    @app_commands.autocomplete(type=type_autocomplete)
    @app_commands.describe(
        type="Type of the pack you want to open.",
        amount="Amount of packs you want to open (1-100).",
    )
    @app_commands.checks.cooldown(1, 5, key=lambda i: i.user.id)
    async def open(
        self,
        interaction: discord.Interaction,
        type: str,
        amount: app_commands.Range[int, 1, 100] = 1,
    ):
        """Open any of your owned packs."""
        await interaction.response.defer()
        try:
            outcome = await sync_to_async(open_packs)(
                interaction.user.id,
                type,
                amount,
                server_id=interaction.guild_id,
            )
        except NotEnoughPacks as exc:
            await interaction.followup.send(
                f"You only have **{exc.available}** {exc.pack.name} pack(s) to open.",
                ephemeral=True,
            )
            return
        except NoBalls as exc:
            await interaction.followup.send(
                f"Sorry, there are no collectibles available for **{exc.pack.name}**.",
                ephemeral=True,
            )
            return
        except PackNotFound as exc:
            await interaction.followup.send(f"Pack type `{exc.pack_type}` does not exist.", ephemeral=True)
            return
        except PackError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        except Exception:
            log.exception("Failed to open %s %s packs for %s", amount, type, interaction.user.id)
            await interaction.followup.send(
                "Something went wrong while opening your packs. Please try again.",
                ephemeral=True,
            )
            return

        rows = [
            f"- **{ball.country}** "
            f"`({_format_instance_id(ball.instance_id)}, {ball.attack_bonus:+d}%/{ball.health_bonus:+d}%)`"
            + (f" {ball.special}" if ball.special else "")
            + (" **(new!)**" if ball.is_new else "")
            for ball in outcome.balls
        ]
        new_count = sum(1 for ball in outcome.balls if ball.is_new)
        text = "\n".join(rows)
        if new_count:
            text += f"\n\n**{new_count}** new collectible(s) added to your completion!"

        view, menu, container = self._paged_view(
            interaction.user.id,
            f"{outcome.pack.name} Pack",
            text,
        )
        await menu.init(container=container)
        message = await interaction.followup.send(view=view)
        view.original_message = message
        log.info(
            "%s (%s) opened %s %s packs",
            interaction.user,
            interaction.user.id,
            outcome.opened,
            outcome.pack.type,
            extra={"webhook": True},
        )

    @app_commands.command()
    @app_commands.autocomplete(type=type_autocomplete)
    @app_commands.describe(
        type="Type of the pack you want to give.",
        user="User you want to give packs to.",
        amount="Amount of packs you want to give (1-100).",
    )
    @app_commands.checks.cooldown(1, 5, key=lambda i: i.user.id)
    async def give(
        self,
        interaction: discord.Interaction,
        type: str,
        user: discord.User,
        amount: app_commands.Range[int, 1, 100] = 1,
    ):
        """Give packs to another user."""
        await interaction.response.defer()
        if user.bot:
            await interaction.followup.send("You cannot give packs to bots.", ephemeral=True)
            return
        if user.id == interaction.user.id:
            await interaction.followup.send("You cannot give packs to yourself.", ephemeral=True)
            return
        if user.id in self.bot.blacklist and not await is_staff(interaction):
            await interaction.followup.send("You cannot give packs to a blacklisted user.", ephemeral=True)
            return

        try:
            outcome = await sync_to_async(give_packs)(
                interaction.user.id, user.id, type, amount
            )
        except NotEnoughPacks as exc:
            await interaction.followup.send(
                f"You only have **{exc.available}** {exc.pack.name} pack(s) to give.",
                ephemeral=True,
            )
            return
        except PackNotFound as exc:
            await interaction.followup.send(f"Pack type `{exc.pack_type}` does not exist.", ephemeral=True)
            return
        except PackError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        except Exception:
            log.exception("Failed to give %s %s packs from %s", amount, type, interaction.user.id)
            await interaction.followup.send(
                "Something went wrong while giving your packs. Please try again.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"You have given **{outcome.given} {outcome.pack.name} pack"
            f"{'s' if outcome.given != 1 else ''}** to {user.mention}!"
        )
        log.info(
            "%s (%s) gave %s %s packs to %s (%s)",
            interaction.user,
            interaction.user.id,
            outcome.given,
            outcome.pack.type,
            user,
            user.id,
            extra={"webhook": True},
        )

    @app_commands.command()
    @app_commands.checks.cooldown(1, 5, key=lambda i: i.user.id)
    async def shop(self, interaction: discord.Interaction):
        """Browse and purchase packs from the store."""
        if not getattr(settings, "currency_enabled", False):
            await interaction.response.send_message(
                "Currency is not enabled in this bot.", ephemeral=True
            )
            return

        await interaction.response.defer()
        candidates = [
            pack
            async for pack in Pack.objects.filter(enabled=True, price__isnull=False).order_by(
                "price", "name"
            )
        ]
        packs = [pack for pack in candidates if pack.available]
        if not packs:
            await interaction.followup.send(
                "There are no packs available in the shop.", ephemeral=True
            )
            return

        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        view = PackShopView(player, packs, self.bot)
        message = await interaction.followup.send(view=view)
        view.original_message = message

    @app_commands.command()
    @app_commands.autocomplete(type=type_autocomplete)
    @app_commands.describe(type="Pack to inspect.")
    @app_commands.checks.cooldown(1, 5, key=lambda i: i.user.id)
    async def info(self, interaction: discord.Interaction, type: str):
        """Show the contents, odds and availability of a pack."""
        pack = await Pack.objects.filter(type=type.strip().lower()).afirst()
        if pack is None:
            await interaction.response.send_message(f"Pack type `{type}` does not exist.", ephemeral=True)
            return

        try:
            preview = await sync_to_async(get_pool_preview)(pack)
        except NoBalls:
            preview = None
        except Exception:
            log.exception("Failed to build pack preview for %s", pack.pk)
            preview = None

        lines = [f"## {pack.name}", f"`{pack.type}`"]
        if pack.description:
            lines.extend(["", pack.description])
        if pack.price is not None:
            lines.append(f"**Price:** {format_pack_currency(pack.price, bot=self.bot)}")
        cooldown = (
            "Disabled"
            if pack.cooldown_seconds is None
            else format_duration(pack.cooldown_seconds)
        )
        lines.append(f"**Free claim cooldown:** {cooldown}")
        lines.append(f"**Available:** {'Yes' if pack.available else 'No'}")
        if pack.stock is not None:
            lines.append(f"**Stock:** {pack.stock}")
        if pack.purchase_limit is not None:
            lines.append(f"**Purchase limit:** {pack.purchase_limit} per user")
        if pack.starts_at:
            lines.append(f"**Starts:** {discord.utils.format_dt(pack.starts_at, 'R')}")
        if pack.ends_at:
            lines.append(f"**Ends:** {discord.utils.format_dt(pack.ends_at, 'R')}")
        if preview is not None:
            lines.append(
                f"**Pool:** {preview.total_balls} collectible(s)"
                + (
                    f" (rarity {pack.min_rarity:g}-{pack.max_rarity:g})"
                    if pack.min_rarity is not None and pack.max_rarity is not None
                    else ""
                )
            )
            lines.append("**Top odds:**")
            lines.extend(
                f"- {ball.country}: {chance:.2%}" for ball, chance in preview.rows
            )
        else:
            lines.append("**Pool:** No collectibles are currently available.")

        view = LayoutView(timeout=180)
        view.add_item(
            ui.Container(
                ui.TextDisplay("\n".join(lines)),
                accent_colour=discord.Colour.gold() if pack.available else discord.Colour.dark_grey(),
            )
        )
        await interaction.response.send_message(view=view)
