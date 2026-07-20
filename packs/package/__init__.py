from typing import TYPE_CHECKING

from .cog import PackCog
from packs.models import Pack, PackInstance

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot") -> None:
    await Pack.objects.aget_or_create(name="Daily", type="daily")
    await Pack.objects.aget_or_create(name="Weekly", type="weekly")
    await Pack.objects.aget_or_create(type="daily").aupdate(name="Daily")
    await Pack.objects.aget_or_create(type="weekly").aupdate(name="Weekly")
    await bot.add_cog(PackCog(bot))
