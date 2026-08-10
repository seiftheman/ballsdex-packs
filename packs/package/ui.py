import discord
from django.utils import timezone
from bd_models.models import Player
from packs.models import Pack, PackInstance
from settings.models import settings

class BuyModal(discord.ui.Modal, title="Buy Packs"):
    amount = discord.ui.TextInput(
        label="Amount",
        placeholder="How many packs do you want to buy?",
        default="1",
        min_length=1,
        max_length=3,
        required=True,
    )

    def __init__(self, view: "PackShopView"):
        super().__init__()
        self.shop_view = view

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

        pack = self.shop_view.packs[self.shop_view.index]
        total_cost = pack.price * amount

        if self.shop_view.player.money < total_cost:
            currency_symbol = getattr(settings, "currency_symbol", "")
            currency_name = getattr(settings, "currency_plural_name", getattr(settings, "currency_name", "Currency") + "s")
            await interaction.response.send_message(
                f"You do not have enough {currency_name.lower()}.\n"
                f"You need **{currency_symbol}{total_cost}**, but you only have **{currency_symbol}{self.shop_view.player.money}**.",
                ephemeral=True
            )
            return

        self.shop_view.player.money -= total_cost
        await self.shop_view.player.asave()

        instances = [
            PackInstance(
                discord_id=interaction.user.id,
                pack=pack,
                last_claim_date=timezone.now(),
            )
            for _ in range(amount)
        ]
        await PackInstance.objects.abulk_create(instances)

        currency_symbol = getattr(settings, "currency_symbol", "")
        await interaction.response.send_message(
            f"You bought **{amount}x {pack.name}** for **{currency_symbol}{total_cost}**!",
            ephemeral=True
        )


class PrevButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary, label="◀", custom_id="prev")

    async def callback(self, interaction: discord.Interaction):
        view: "PackShopView" = self.view
        if interaction.user.id != view.player.discord_id:
            await interaction.response.send_message("You cannot interact with this shop.", ephemeral=True)
            return
        await view.handle_page_navigation(interaction, -1)


class NextButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary, label="▶", custom_id="next")

    async def callback(self, interaction: discord.Interaction):
        view: "PackShopView" = self.view
        if interaction.user.id != view.player.discord_id:
            await interaction.response.send_message("You cannot interact with this shop.", ephemeral=True)
            return
        await view.handle_page_navigation(interaction, 1)


class BuyButton(discord.ui.Button):
    def __init__(self, currency_symbol: str):
        super().__init__(
            style=discord.ButtonStyle.success,
            label="Buy Pack",
            custom_id="buy"
        )

    async def callback(self, interaction: discord.Interaction):
        view: "PackShopView" = self.view
        if interaction.user.id != view.player.discord_id:
            await interaction.response.send_message("You cannot buy items in someone else's shop.", ephemeral=True)
            return
        await interaction.response.send_modal(BuyModal(view))


class PackSelect(discord.ui.Select):
    def __init__(self, packs: list[Pack], page: int, page_size: int):
        options = []
        start = page * page_size
        end = min(start + page_size, len(packs))
        
        currency_symbol = getattr(settings, "currency_symbol", "")
        
        for idx, pack in enumerate(packs[start:end], start=start):
            options.append(
                discord.SelectOption(
                    label=pack.name,
                    description=f"Price: {currency_symbol}{pack.price}",
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
            await interaction.response.send_message("You cannot interact with this shop.", ephemeral=True)
            return
        view.index = int(self.values[0])
        view.page = view.index // view.page_size
        view.update_layout()
        await interaction.response.edit_message(view=view)


class PackShopView(discord.ui.LayoutView):
    def __init__(self, player: Player, packs: list[Pack], bot):
        super().__init__(timeout=180)
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

        header = f"## {pack.name}"
        cost_text = f"### {pack.price} {currency_name}"
        
        cooldown_str = self._format_seconds(pack.cooldown_seconds)

        layout = discord.ui.Container(
            discord.ui.TextDisplay(content=header),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.large),
            discord.ui.TextDisplay(content=f"**Price**\n{cost_text}"),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(content=f"**Cooldown (Free Claims)**\n`{cooldown_str}`"),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.large),
            discord.ui.TextDisplay(content=f"*Page {self.page + 1}/{self.total_pages()}*"),
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
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def handle_page_navigation(self, interaction: discord.Interaction, direction: int):
        if not self.packs:
            return
        self.page = (self.page + direction) % self.total_pages()
        self.index = self.page * self.page_size
        self.update_layout()
        await interaction.response.edit_message(view=self)
