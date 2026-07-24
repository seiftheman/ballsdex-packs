import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('packs', '0011_populate_packinstance_pack'),
    ]

    operations = [
        migrations.AlterField(
            model_name='packinstance',
            name='pack',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='instances',
                to='packs.pack'
            ),
        ),
    ]
