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
                    "discord_id",
                    models.BigIntegerField(
                        unique=True,
                        help_text="Discord user ID",
                    ),
                ),
            ],
        ),
    ]
