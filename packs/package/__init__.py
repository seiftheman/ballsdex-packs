from typing import TYPE_CHECKING

from .cog import PackCog
from packs.models import Pack, PackInstance

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot") -> None:
    await Pack.objects.aget_or_create(type="daily")
    await Pack.objects.aget_or_create(type="weekly")
    await bot.add_cog(PackCog(bot))
