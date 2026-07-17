from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("packs", "0006_packinstance_remove_pack_discord_id_and_more"),
    ]

    operations = [
        migrations.DeleteModel(
            name="PackInstance",
        ),
        migrations.AddField(
            model_name="pack",
            name="discord_id",
            field=models.BigIntegerField(null=True),
        ),
        migrations.AddField(
            model_name="pack",
            name="is_opened",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="pack",
            name="last_claim_date",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RenameModel(
            old_name="Pack",
            new_name="PackInstance",
        ),
        migrations.CreateModel(
            name="Pack",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("type", models.CharField(max_length=100, help_text="Type of the pack."), unique=True),
                ("min_rarity", models.FloatField(null=True, help_text="Minimum rarity for balls in this pack.")),
                ("max_rarity", models.FloatField(null=True, help_text="Maximum rarity for balls in this pack.")),
            ],
        ),
    ]