from typing import TYPE_CHECKING
from packs.models import Pack
from .cog import PackCog
from .admin import PackAdmin

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot") -> None:
    await Pack.objects.aupdate_or_create(type="daily", defaults={"name": "Daily"})  
    await Pack.objects.aupdate_or_create(type="weekly", defaults={"name": "Weekly"})
    await bot.add_cog(PackCog(bot))
    await bot.add_cog(PackAdmin(bot))