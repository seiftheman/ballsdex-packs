from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("packs", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="Pack",
            name="last_claim_date",
            field=models.DateTimeField(
                null=True,
                blank=True,
                help_text="When this pack was claimed (used for cooldown tracking).",
            ),
        ),
    ]