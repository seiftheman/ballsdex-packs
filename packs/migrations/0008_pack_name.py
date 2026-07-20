from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('packs', '0007_alter_pack_type'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="""
                    ALTER TABLE packs_pack 
                    ADD COLUMN IF NOT EXISTS name varchar(100) DEFAULT 'Unnamed Pack' UNIQUE;
                    """,
                    reverse_sql="ALTER TABLE packs_pack DROP COLUMN IF EXISTS name;",
                )
            ],
            state_operations=[
                migrations.AddField(
                    model_name='pack',
                    name='name',
                    field=models.CharField(
                        default='Unnamed Pack',
                        help_text='Name of the pack.',
                        max_length=100,
                        unique=True,
                    ),
                ),
            ],
        )
    ]