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

PAGE_SIZE = 20
MAX_QUANTITY = 100


def _shorten(value: str, limit: int) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return f"{value[: limit - 1].rstrip()}…"


def _format_price(pack: Pack, bot: BallsDexBot) -> str:
    if pack.price is None:
        return "Not for sale"
    return format_pack_currency(pack.price, bot=bot)


def _stock_text(pack: Pack) -> str:
    if pack.stock is None:
        return "Unlimited"
    if pack.stock <= 0:
        return "Out of stock"
    return f"{pack.stock:,} available"


def _status_text(pack: Pack) -> str:
    if not pack.available:
        return "🔴 Unavailable"
    if pack.stock is not None and pack.stock <= 5:
        return "🟠 Low stock"
    return "🟢 Available"


def _accent_colour(pack: Pack) -> discord.Colour:
    if not pack.available:
        return discord.Colour.dark_grey()
    if pack.stock is not None and pack.stock <= 5:
        return discord.Colour.orange()
    return discord.Colour.brand_green()


def _claim_text(pack: Pack) -> str:
    if pack.cooldown_seconds is None:
        return "Shop only"
    if pack.cooldown_seconds == 0:
        return "No cooldown"
    return f"Every {format_duration(pack.cooldown_seconds)}"


def _option_description(pack: Pack, bot: BallsDexBot) -> str:
    parts = [_format_price(pack, bot)]
    if pack.stock is None:
        parts.append("Unlimited stock")
    elif pack.stock <= 0:
        parts.append("Out of stock")
    else:
        parts.append(f"{pack.stock:,} in stock")
    if pack.purchase_limit is not None:
        parts.append(f"Limit {pack.purchase_limit:,}")
    return _shorten(" • ".join(parts), 100)


class BuyModal(Modal):
    amount = ui.TextInput(
        label="Quantity",
        placeholder="How many packs? (1–100)",
        default="1",
        min_length=1,
        max_length=3,
        required=True,
    )

    def __init__(self, view: "PackShopView", pack: Pack):
        super().__init__(title=_shorten(f"Buy {pack.name}", 45))
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
        if amount > MAX_QUANTITY:
            await interaction.response.send_message(
                f"You can only buy up to {MAX_QUANTITY} packs at once.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        try:
            outcome = await sync_to_async(buy_packs)(interaction.user.id, self.pack.pk, amount)
        except NotEnoughMoney as exc:
            await interaction.followup.send(
                "You do not have enough currency.\n"
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
            await self._refresh_shop()
            return
        except PackUnavailable as exc:
            await interaction.followup.send(f"**{exc.pack.name}** is not currently available.", ephemeral=True)
            await self._refresh_shop()
            return
        except Exception:
            log.exception("Failed to purchase %s packs for %s", amount, interaction.user.id)
            await interaction.followup.send(
                "Something went wrong while purchasing your packs. Please try again.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"✅ You bought **{outcome.bought}x {outcome.pack.name}** for "
            f"**{format_pack_currency(outcome.total_cost, bot=interaction.client)}**.\n"
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
        await self._refresh_shop()

    async def _refresh_shop(self) -> None:
        try:
            await self.shop_view.refresh()
        except Exception:
            log.exception("Failed to refresh the pack shop view")


class PrevButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary, label="Previous", custom_id="pack_shop_prev")

    async def callback(self, interaction: discord.Interaction):
        view: PackShopView = self.view
        await view.handle_page_navigation(interaction, -1)


class NextButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary, label="Next", custom_id="pack_shop_next")

    async def callback(self, interaction: discord.Interaction):
        view: PackShopView = self.view
        await view.handle_page_navigation(interaction, 1)


class BuyButton(ui.Button):
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.success,
            label="Buy Pack",
            emoji="🛒",
            custom_id="pack_shop_buy",
        )

    async def callback(self, interaction: discord.Interaction):
        view: PackShopView = self.view
        if not view.packs:
            await interaction.response.send_message("There are no packs to buy.", ephemeral=True)
            return
        pack = view.packs[view.index]
        await interaction.response.send_modal(BuyModal(view, pack))


class PackSelect(ui.Select):
    def __init__(
        self,
        packs: list[Pack],
        page: int,
        page_size: int,
        bot: BallsDexBot,
        selected_index: int,
    ):
        start = page * page_size
        end = min(start + page_size, len(packs))
        options = [
            discord.SelectOption(
                label=_shorten(pack.name, 100),
                description=_option_description(pack, bot),
                value=str(index),
                default=index == selected_index,
            )
            for index, pack in enumerate(packs[start:end], start=start)
        ]
        super().__init__(
            placeholder="Choose a pack...",
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
        self.page_size = PAGE_SIZE
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
        self.index = max(0, min(self.index, len(self.packs) - 1))
        self.page = self.index // self.page_size

    def page_summary(self) -> str:
        count = len(self.packs)
        label = f"{count} pack{'s' if count != 1 else ''} available"
        return f"-# Page {self.page + 1} of {self.total_pages()} • {label}"

    def update_layout(self) -> None:
        self.clear_items()
        if not self.packs:
            self.add_item(
                ui.Container(
                    ui.TextDisplay("## 🛒 Pack Shop\nThere are no packs available right now."),
                    accent_colour=discord.Colour.dark_grey(),
                )
            )
            return

        self.clamp_state()
        pack = self.packs[self.index]

        header = "## 🛒 Pack Shop\n-# Browse the shop and purchase packs with your balance."
        title = f"### {pack.name}"
        if pack.description:
            title = f"{title}\n{_shorten(pack.description, 1200)}"

        details = [
            f"**Status** — {_status_text(pack)}",
            f"**Price** — {_format_price(pack, self.bot)}",
            f"**Stock** — {_stock_text(pack)}",
            f"**Free claims** — {_claim_text(pack)}",
        ]
        if pack.purchase_limit is not None:
            details.append(f"**Purchase limit** — {pack.purchase_limit:,} per user")
        if pack.ends_at is not None:
            details.append(f"**Available until** — <t:{int(pack.ends_at.timestamp())}:R>")
        if not pack.available:
            details.extend(["", "> This pack is not currently available for purchase."])

        footer = (
            f"**Your balance** — {format_pack_currency(self.player.money, bot=self.bot)}\n"
            f"{self.page_summary()}"
        )

        self.add_item(
            ui.Container(
                ui.TextDisplay(header),
                ui.Separator(),
                ui.TextDisplay(title),
                ui.Separator(spacing=discord.SeparatorSpacing.small),
                ui.TextDisplay("\n".join(details)),
                ui.Separator(),
                ui.TextDisplay(footer),
                accent_colour=_accent_colour(pack),
            )
        )
        self.add_item(ui.ActionRow(PackSelect(self.packs, self.page, self.page_size, self.bot, self.index)))

        previous = PrevButton()
        buy = BuyButton()
        following = NextButton()
        previous.disabled = self.page <= 0
        following.disabled = self.page >= self.total_pages() - 1
        buy.disabled = not pack.available or pack.price is None
        self.add_item(ui.ActionRow(previous, buy, following))

    async def refresh(self) -> None:
        try:
            self.player = await Player.objects.aget(pk=self.player.pk)
        except Player.DoesNotExist:
            pass

        if self.packs:
            pack_ids = [pack.pk for pack in self.packs]
            refreshed = {
                pack.pk: pack
                async for pack in Pack.objects.filter(pk__in=pack_ids)
            }
            self.packs = [refreshed[pack.pk] for pack in self.packs if pack.pk in refreshed]

        self.update_layout()
        if self.original_message is not None:
            try:
                await self.original_message.edit(view=self)
            except discord.HTTPException:
                pass

    async def handle_page_navigation(self, interaction: discord.Interaction, direction: int) -> None:
        if not self.packs:
            return
        new_page = self.page + direction
        if not 0 <= new_page < self.total_pages():
            await interaction.response.defer()
            return
        self.page = new_page
        self.index = self.page * self.page_size
        self.update_layout()
        await interaction.response.edit_message(view=self)
