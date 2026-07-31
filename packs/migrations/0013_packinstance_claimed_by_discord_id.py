from django.db import migrations, models


def populate_claimed_by_discord_id(apps, schema_editor):
    PackInstance = apps.get_model("packs", "PackInstance")
    PackInstance.objects.filter(claimed_by_discord_id__isnull=True).update(
        claimed_by_discord_id=models.F("discord_id")
    )


class Migration(migrations.Migration):

    dependencies = [
        ("packs", "0012_alter_packinstance_pack"),
    ]

    operations = [
        migrations.AddField(
            model_name="packinstance",
            name="claimed_by_discord_id",
            field=models.BigIntegerField(
                blank=True,
                help_text="Discord user ID of the user who claimed this pack.",
                null=True,
            ),
        ),
        migrations.RunPython(
            populate_claimed_by_discord_id,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
