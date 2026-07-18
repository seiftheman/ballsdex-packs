from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("packs", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name='PackInstance',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('type', models.CharField(help_text='Type of the pack.', max_length=100)),
                ('discord_id', models.BigIntegerField(help_text='Discord user ID.')),
                ('last_claim_date', models.DateTimeField(blank=True, help_text='When this pack was claimed (used for cooldown tracking).', null=True)),
                ('min_rarity', models.FloatField(help_text='Minimum rarity for balls in this pack.', null=True)),
                ('max_rarity', models.FloatField(help_text='Maximum rarity for balls in this pack.', null=True)),
                ('is_opened', models.BooleanField(default=False, help_text='Whether this pack has already been opened.')),
            ],
        ),
        migrations.RenameModel(
            old_name="Pack",
            new_name="PackInstance",
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