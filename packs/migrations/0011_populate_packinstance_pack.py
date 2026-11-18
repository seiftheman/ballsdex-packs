from django.db import migrations


def populate_pack_instances(apps, schema_editor):
    Pack = apps.get_model("packs", "Pack")
    PackInstance = apps.get_model("packs", "PackInstance")

    default_pack = Pack.objects.filter(type="daily").first() or Pack.objects.first()
    if default_pack is None:
        # Older installations could reach this migration with no Pack rows at all.
        # 0012 makes pack_id non-null, so a fallback row is required to upgrade safely.
        default_pack = Pack.objects.create(type="daily", name="Daily")

    PackInstance.objects.filter(pack__isnull=True).update(pack=default_pack)

class Migration(migrations.Migration):

    dependencies = [
        ('packs', '0010_remove_packinstance_max_rarity_and_more'),
    ]

    operations = [
        migrations.RunPython(populate_pack_instances, reverse_code=migrations.RunPython.noop),
    ]
