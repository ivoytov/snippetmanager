# Generated by Django 4.0.3 on 2024-03-14 01:19

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='project',
            name='user',
        ),
    ]
