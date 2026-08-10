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
from django.db.models import Count, Q
from django.utils import timezone

from ballsdex.core.utils import checks
from ballsdex.core.utils.utils import is_staff
from bd_models.models import Ball, BallInstance, Player
from packs.models import Pack, PackInstance
from settings.models import settings

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.packs")

async def type_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    choices = []
    async for pack in Pack.objects.filter(enabled=True):
        if current.lower() in pack.name.lower():
            choices.append(app_commands.Choice(name=pack.name, value=pack.type))
    return choices[:25]

class PrevButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary, label="←", custom_id="prev")

    async def callback(self, interaction: discord.Interaction):
        view: "PackShopView" = self.view
        if interaction.user.id != view.player.discord_id:
            await interaction.response.send_message("You're not allowed to browse someone else's shop.", ephemeral=True)
            return
        await view.handle_page_navigation(interaction, -1)

class NextButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary, label="→", custom_id="next")

    async def callback(self, interaction: discord.Interaction):
        view: "PackShopView" = self.view
        if interaction.user.id != view.player.discord_id:
            await interaction.response.send_message("You're not allowed to browse someone else's shop.", ephemeral=True)
            return
        await view.handle_page_navigation(interaction, 1)

class BuyButton(discord.ui.Button):
    def __init__(self, currency_symbol: str):
        super().__init__(
            style=discord.ButtonStyle.success,
            label=f"{currency_symbol} Buy",
            custom_id="buy"
        )

    async def callback(self, interaction: discord.Interaction):
        view: "PackShopView" = self.view
        if interaction.user.id != view.player.discord_id:
            await interaction.response.send_message("You're not allowed to buy items in someone else's shop.", ephemeral=True)
            return
        await view.handle_purchase(interaction)

class PackSelect(discord.ui.Select):
    def __init__(self, packs: list[Pack], page: int, page_size: int):
        options = []
        start = page * page_size
        end = min(start + page_size, len(packs))
        for idx, pack in enumerate(packs[start:end], start=start):
            options.append(
                discord.SelectOption(
                    label=pack.name,
                    description=f"Cost: {pack.price}",
                    value=str(idx),
                )
            )
        super().__init__(
            placeholder="Select a pack to view...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="pack_select"
        )

    async def callback(self, interaction: discord.Interaction):
        view: "PackShopView" = self.view
        if interaction.user.id != view.player.discord_id:
            await interaction.response.send_message("You're not allowed to browse someone else's shop.", ephemeral=True)
            return
        view.index = int(self.values[0])
        view.page = view.index // view.page_size
        view.update_layout()
        await interaction.response.edit_message(view=view)

class PackShopView(discord.ui.LayoutView):
    def __init__(self, player: Player, packs: list[Pack], bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.player = player
        self.packs = packs
        self.index = 0
        self.page_size = 20
        self.page = 0
        self.message: discord.Message | None = None
        self.update_layout()

    def total_pages(self) -> int:
        if not self.packs:
            return 1
        return (len(self.packs) - 1) // self.page_size + 1

    def clamp_state(self):
        if not self.packs:
            self.index = 0
            self.page = 0
            return
        self.index %= len(self.packs)
        self.page = max(0, min(self.page, self.total_pages() - 1))

    def update_layout(self):
        self.clear_items()
        if not self.packs:
            return
        self.clamp_state()
        pack = self.packs[self.index]
        
        currency_name = getattr(settings, "currency_name", "Currency")
        currency_symbol = getattr(settings, "currency_symbol", "")

        header = f"**{pack.name}**"
        cost_text = f"{currency_symbol} **{pack.price}**"
        
        cooldown_str = self._format_seconds(pack.cooldown_seconds)

        layout = discord.ui.Container(
            discord.ui.TextDisplay(content=f"The Pack Store! Page {self.page + 1}/{self.total_pages()}"),
            discord.ui.TextDisplay(content=header),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.large),
            discord.ui.TextDisplay(content=f"**__Cost__**\n{cost_text}"),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(content=f"**__Cooldown__**\n{cooldown_str}"),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.large),
            accent_colour=discord.Colour.gold()
        )

        self.add_item(layout)
        self.add_item(discord.ui.ActionRow(PackSelect(self.packs, self.page, self.page_size)))
        self.add_item(discord.ui.ActionRow(PrevButton(), BuyButton(currency_symbol), NextButton()))

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
        if len(parts) == 0:
            return "0 minutes"
        return " and ".join(", ".join(parts).rsplit(", ", 1))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.player.discord_id

    async def on_timeout(self):
        self.clear_items()
        if self.message:
            await self.message.edit(view=self)

    async def handle_page_navigation(self, interaction: discord.Interaction, direction: int):
        if not self.packs:
            return
        self.page = (self.page + direction) % self.total_pages()
        self.index = self.page * self.page_size
        self.update_layout()
        await interaction.response.edit_message(view=self)

    async def handle_purchase(self, interaction: discord.Interaction):
        if not self.packs:
            await interaction.response.send_message("There are no items available to purchase.", ephemeral=True)
            return
        pack = self.packs[self.index]
        
        total_cost = pack.price
        
        if self.player.money < total_cost:
            currency_symbol = getattr(settings, "currency_symbol", "")
            currency_name = getattr(settings, "currency_plural_name", getattr(settings, "currency_name", "Currency") + "s")
            await interaction.response.send_message(
                f"You do not have enough {currency_name.lower()}. "
                f"You need **{currency_symbol}{total_cost}**, but you only have **{currency_symbol}{self.player.money}**.",
                ephemeral=True
            )
            return
            
        self.player.money -= total_cost
        await self.player.asave()
        
        await PackInstance.objects.acreate(
            discord_id=interaction.user.id,
            pack=pack,
            last_claim_date=timezone.now(),
        )
        
        currency_symbol = getattr(settings, "currency_symbol", "")
        await interaction.response.send_message(
            f"Successfully purchased the **{pack.name}** for **{currency_symbol}{total_cost}**!",
            ephemeral=True
        )

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

        if not getattr(settings, "currency_name", None):
            self.app_command.remove_command("shop")

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
                claimed_by_discord_id=interaction.user.id,
                pack=pack,
                last_claim_date=timezone.now(),
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
                claimed_by_discord_id=discord_id,
                pack=pack,
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

    @app_commands.command()
    async def list(self, interaction: discord.Interaction):
        """View a list of your owned packs."""
        packs = [
            pack
            async for pack in Pack.objects.filter(enabled=True)
            .annotate(
                unopened_count=Count(
                    "instances",
                    filter=Q(
                        instances__discord_id=interaction.user.id,
                        instances__is_opened=False,
                    ),
                )
            )
            .order_by("type")
        ]

        message = "\n".join(
            f"{pack.name} Packs: {pack.unopened_count}" for pack in packs
        )
        await interaction.response.send_message(message)

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
                discord_id=interaction.user.id, pack__type=type, is_opened=False
            )
            .select_related("pack")
            .order_by("last_claim_date")
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
        for pack_instance in packs_to_consume:
            balls_query = Ball.objects.filter(enabled=True)
            if pack_instance.pack.min_rarity is not None:
                balls_query = balls_query.filter(rarity__gte=pack_instance.pack.min_rarity)
            if pack_instance.pack.max_rarity is not None:
                balls_query = balls_query.filter(rarity__lte=pack_instance.pack.max_rarity)

            balls = [ball async for ball in balls_query]

            if not balls:
                await interaction.followup.send(
                    f"Sorry, there are no collectibles available for the {type.lower()} pack."
                )
                return

            weights = [ball.rarity for ball in balls]
            if sum(weights) <= 0:
                ball = random.choice(balls)
            else:
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
            discord_id=interaction.user.id, pack__type=type, is_opened=False
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
                    "You cannot give packs to a blacklisted user.", ephemeral=True
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

    @app_commands.command()
    async def shop(self, interaction: discord.Interaction):
        """Browse and purchase packs from the store."""
        await interaction.response.defer()
        
        if not getattr(settings, "currency_name", None):
            await interaction.followup.send("Currency is not enabled in this bot.", ephemeral=True)
            return

        packs = [pack async for pack in Pack.objects.filter(enabled=True, price__isnull=False).order_by("price")]
        if not packs:
            await interaction.followup.send("There are no packs available in the shop.", ephemeral=True)
            return

        player, _ = await Player.objects.aget_or_create(discord_id=interaction.user.id)
        
        view = PackShopView(player, packs, self.bot)
        message = await interaction.followup.send(view=view)
        view.message = message
