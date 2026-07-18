from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("packs", "0005_pack_max_rarity_pack_min_rarity"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="Pack",
            new_name="PackInstance",
        ),
        migrations.AddField(
            model_name="packinstance",
            name="is_opened",
            field=models.BooleanField(default=False, help_text="Whether this pack has already been opened."),
        ),
        migrations.AlterField(
            model_name="packinstance",
            name="type",
            field=models.CharField(help_text="Type of the pack.", max_length=100),
        ),
        migrations.CreateModel(
            name="Pack",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("type", models.CharField(max_length=100, help_text="Type of the pack.", unique=True)),
                ("min_rarity", models.FloatField(null=True, help_text="Minimum rarity for balls in this pack.")),
                ("max_rarity", models.FloatField(null=True, help_text="Maximum rarity for balls in this pack.")),
            ],
        ),
    ]