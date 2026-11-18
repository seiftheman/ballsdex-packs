from typing import TYPE_CHECKING

from packs.models import Pack

from .admin import PackAdmin
from .cog import PackCog

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot") -> None:
    # Use get_or_create rather than update_or_create: admins are allowed to rename packs,
    # and a bot restart must not overwrite their configuration.
    await Pack.objects.aget_or_create(
        type="daily",
        defaults={"name": "Daily", "cooldown_seconds": 86400},
    )
    await Pack.objects.aget_or_create(
        type="weekly",
        defaults={"name": "Weekly", "cooldown_seconds": 604800},
    )
    await bot.add_cog(PackCog(bot))
    await bot.add_cog(PackAdmin(bot))
