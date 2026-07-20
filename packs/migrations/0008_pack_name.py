from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('packs', '0007_alter_pack_type'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                # 1. Add column without UNIQUE constraint first
                migrations.RunSQL(
                    sql="""
                    ALTER TABLE packs_pack 
                    ADD COLUMN IF NOT EXISTS name varchar(100);
                    """,
                    reverse_sql="ALTER TABLE packs_pack DROP COLUMN IF EXISTS name;",
                ),
                # 2. Backfill existing rows using their 'type' column (e.g. 'daily' -> 'Daily Pack')
                migrations.RunSQL(
                    sql="""
                    UPDATE packs_pack 
                    SET name = INITCAP(type) || ' Pack' 
                    WHERE name IS NULL OR name = 'Unnamed Pack';
                    """,
                    reverse_sql=migrations.RunSQL.noop,
                ),
                # 3. Add the UNIQUE constraint now that values are distinct
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