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
                    ADD COLUMN IF NOT EXISTS name varchar(100);
                    """,
                    reverse_sql="ALTER TABLE packs_pack DROP COLUMN IF EXISTS name;",
                ),
                migrations.RunSQL(
                    sql="""
                    UPDATE packs_pack 
                    SET name = INITCAP(type) || ' Pack' 
                    WHERE name IS NULL OR name = 'Unnamed Pack';
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    sql="""
                    ALTER TABLE packs_pack 
                    ADD CONSTRAINT packs_pack_name_key UNIQUE (name);
                    """,
                    reverse_sql="ALTER TABLE packs_pack DROP CONSTRAINT IF EXISTS packs_pack_name_key;",
                ),
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