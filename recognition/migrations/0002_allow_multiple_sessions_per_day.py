# Generated migration to allow multiple attendance sessions per day

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('recognition', '0001_initial'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='attendance',
            unique_together=set(),
        ),
    ]
