from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('packs', '0007_alter_pack_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='pack',
            name='name',
            field=models.CharField(default='Unnamed Pack', help_text='Name of the pack.', max_length=100, unique=True),
        ),
    ]