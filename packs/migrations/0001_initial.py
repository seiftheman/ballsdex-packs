from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Pack",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "type",
                    models.CharField(
                        max_length=100,
                        help_text="Type of the pack.",
                    ),
                ),
                # (
                #     "last_claim_date",
                #     models.DateTimeField(
                #         null=True,
                #         blank=True,
                #         help_text="When this pack was claimed (used for cooldown tracking).",
                #     ),
                # ),
                (
                    "discord_id",
                    models.BigIntegerField(
                        help_text="Discord user ID.",
                    ),
                ),
            ],
        ),
    ]
