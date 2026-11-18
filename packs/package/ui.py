from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from asgiref.sync import sync_to_async
from ballsdex.core.discord import LayoutView, Modal
from bd_models.models import Player
from discord import ui

from packs.models import Pack
from packs.services import (
    NotEnoughMoney,
    OutOfStock,
    PackUnavailable,
    PurchaseLimitReached,
    buy_packs,
)

from .utils import format_duration, format_pack_currency

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.packs")


class BuyModal(Modal, title="Buy Packs"):
    amount = ui.TextInput(
        label="Amount",
        placeholder="How many packs do you want to buy?",
        default="1",
        min_length=1,
        max_length=3,
        required=True,
    )

    def __init__(self, view: "PackShopView", pack: Pack):
        super().__init__()
        self.shop_view = view
        self.pack = pack

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount.value)
        except ValueError:
            await interaction.response.send_message("Please enter a valid number.", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("Amount must be greater than zero.", ephemeral=True)
            return
        if amount > 100:
            await interaction.response.send_message("You can only buy up to 100 packs at once.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            outcome = await sync_to_async(buy_packs)(interaction.user.id, self.pack.pk, amount)
        except NotEnoughMoney as exc:
            await interaction.followup.send(
                f"You do not have enough currency.\n"
                f"You need **{format_pack_currency(exc.total, bot=interaction.client)}**, but you only have "
                f"**{format_pack_currency(exc.balance, bot=interaction.client)}**.",
                ephemeral=True,
            )
            return
        except PurchaseLimitReached as exc:
            await interaction.followup.send(
                f"You can only purchase **{exc.limit}** {exc.pack.name} packs. "
                f"You have already purchased **{exc.purchased}**.",
                ephemeral=True,
            )
            return
        except OutOfStock as exc:
            await interaction.followup.send(f"**{exc.pack.name}** is out of stock.", ephemeral=True)
            return
        except PackUnavailable as exc:
            await interaction.followup.send(f"**{exc.pack.name}** is not currently available.", ephemeral=True)
            return
        except Exception:
            log.exception("Failed to purchase %s packs for %s", amount, interaction.user.id)
            await interaction.followup.send(
                "Something went wrong while purchasing your packs. Please try again.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"You bought **{outcome.bought}x {outcome.pack.name}** for "
            f"**{format_pack_currency(outcome.total_cost, bot=interaction.client)}**!\n"
            f"Your balance is now **{format_pack_currency(outcome.new_balance, bot=interaction.client)}**.",
            ephemeral=True,
        )
        log.info(
            "%s (%s) bought %s %s packs for %s",
            interaction.user,
            interaction.user.id,
            outcome.bought,
            outcome.pack.type,
            outcome.total_cost,
            extra={"webhook": True},
        )
        try:
            await self.shop_view.refresh()
        except Exception:
            log.exception("Failed to refresh the pack shop view")


class PrevButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary, label="◀", custom_id="pack_shop_prev")

    async def callback(self, interaction: discord.Interaction):
        view: PackShopView = self.view
        await view.handle_page_navigation(interaction, -1)


class NextButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary, label="▶", custom_id="pack_shop_next")

    async def callback(self, interaction: discord.Interaction):
        view: PackShopView = self.view
        await view.handle_page_navigation(interaction, 1)


class BuyButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.success, label="Buy Pack", custom_id="pack_shop_buy")

    async def callback(self, interaction: discord.Interaction):
        view: PackShopView = self.view
        if not view.packs:
            await interaction.response.send_message("There are no packs to buy.", ephemeral=True)
            return
        pack = view.packs[view.index]
        await interaction.response.send_modal(BuyModal(view, pack))


class PackSelect(ui.Select):
    def __init__(self, packs: list[Pack], page: int, page_size: int, bot: BallsDexBot):
        start = page * page_size
        end = min(start + page_size, len(packs))
        options = [
            discord.SelectOption(
                label=pack.name[:100],
                description=f"Price: {format_pack_currency(pack.price or 0, bot=bot)}"[:100],
                value=str(index),
            )
            for index, pack in enumerate(packs[start:end], start=start)
        ]
        super().__init__(
            placeholder="Select a pack to view...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="pack_shop_select",
        )

    async def callback(self, interaction: discord.Interaction):
        view: PackShopView = self.view
        view.index = int(self.values[0])
        view.page = view.index // view.page_size
        view.update_layout()
        await interaction.response.edit_message(view=view)


class PackShopView(LayoutView):
    def __init__(self, player: Player, packs: list[Pack], bot: BallsDexBot):
        super().__init__(timeout=180)
        self.bot = bot
        self.player = player
        self.packs = packs
        self.index = 0
        self.page_size = 20
        self.page = 0
        self.restrict_author(player.discord_id)
        self.update_layout()

    def total_pages(self) -> int:
        if not self.packs:
            return 1
        return (len(self.packs) - 1) // self.page_size + 1

    def clamp_state(self) -> None:
        if not self.packs:
            self.index = 0
            self.page = 0
            return
        self.index %= len(self.packs)
        self.page = max(0, min(self.page, self.total_pages() - 1))

    def update_layout(self) -> None:
        self.clear_items()
        if not self.packs:
            self.add_item(ui.Container(ui.TextDisplay("There are no packs available in the shop.")))
            return

        self.clamp_state()
        pack = self.packs[self.index]
        lines = [f"## {pack.name}"]
        if pack.description:
            lines.extend(["", pack.description])
        lines.extend(
            [
                "",
                f"**Price**\n{format_pack_currency(pack.price or 0, bot=self.bot)}",
                (
                    "**Free claims**\nDisabled"
                    if pack.cooldown_seconds is None
                    else f"**Free claim cooldown**\n`{format_duration(pack.cooldown_seconds)}`"
                ),
                f"**Your balance**\n{format_pack_currency(self.player.money, bot=self.bot)}",
            ]
        )
        if pack.stock is not None:
            lines.append(f"**Stock**\n{pack.stock}")
        if pack.purchase_limit is not None:
            lines.append(f"**Purchase limit**\n{pack.purchase_limit} per user")
        if not pack.available:
            lines.append("\n*This pack is not currently available.*")
        lines.extend(["", f"*Page {self.page + 1}/{self.total_pages()}*"])

        container = ui.Container(
            ui.TextDisplay("\n".join(lines)),
            accent_colour=discord.Colour.gold() if pack.available else discord.Colour.dark_grey(),
        )
        self.add_item(container)
        self.add_item(ui.ActionRow(PackSelect(self.packs, self.page, self.page_size, self.bot)))

        previous = PrevButton()
        buy = BuyButton()
        following = NextButton()
        previous.disabled = self.total_pages() <= 1
        following.disabled = self.total_pages() <= 1
        buy.disabled = not pack.available or pack.price is None
        self.add_item(ui.ActionRow(previous, buy, following))

    async def refresh(self) -> None:
        try:
            self.player = await Player.objects.aget(pk=self.player.pk)
        except Player.DoesNotExist:
            pass

        refreshed: list[Pack] = []
        for pack in self.packs:
            try:
                refreshed.append(await Pack.objects.aget(pk=pack.pk))
            except Pack.DoesNotExist:
                continue
        self.packs = refreshed
        self.update_layout()
        if self.original_message is not None:
            try:
                await self.original_message.edit(view=self)
            except discord.HTTPException:
                pass

    async def handle_page_navigation(self, interaction: discord.Interaction, direction: int) -> None:
        if not self.packs:
            return
        self.page = (self.page + direction) % self.total_pages()
        self.index = self.page * self.page_size
        self.update_layout()
        await interaction.response.edit_message(view=self)
