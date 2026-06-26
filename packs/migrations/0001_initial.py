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
                    "kind",
                    models.CharField(
                        max_length=100,
                        help_text="Type of the pack.",
                    ),
                ),
                (
                    "discord_id",
                    models.BigIntegerField(
                        help_text="Discord user ID",
                    ),
                ),
            ],
        ),
    ]
