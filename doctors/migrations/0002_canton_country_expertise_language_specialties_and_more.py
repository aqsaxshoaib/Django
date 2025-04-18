# Generated by Django 5.1.7 on 2025-04-14 11:38

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('doctors', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Canton',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('status', models.CharField(max_length=255)),
                ('created_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'db_table': 'cantons',
            },
        ),
        migrations.CreateModel(
            name='Country',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('status', models.SmallIntegerField()),
                ('created_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'db_table': 'countries',
            },
        ),
        migrations.CreateModel(
            name='Expertise',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('status', models.CharField(default='1', max_length=255)),
                ('created_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'db_table': 'expertises',
            },
        ),
        migrations.CreateModel(
            name='Language',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('code', models.CharField(blank=True, max_length=255, null=True)),
                ('translation_status', models.CharField(blank=True, max_length=255, null=True)),
                ('created_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'db_table': 'languages',
            },
        ),
        migrations.CreateModel(
            name='Specialties',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('status', models.CharField(default='1', max_length=255)),
                ('created_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'db_table': 'specialties',
            },
        ),
        migrations.AlterField(
            model_name='user',
            name='language',
            field=models.CharField(blank=True, db_column='language', max_length=255, null=True),
        ),
        migrations.RenameField(
            model_name='user',
            old_name='language',
            new_name='language_ids',
        ),
        migrations.CreateModel(
            name='City',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255)),
                ('status', models.CharField(max_length=255)),
                ('created_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(blank=True, null=True)),
                ('canton', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='doctors.canton')),
            ],
            options={
                'db_table': 'cities',
            },
        ),
        migrations.AlterField(
            model_name='user',
            name='city',
            field=models.ForeignKey(blank=True, db_column='city', null=True, on_delete=django.db.models.deletion.SET_NULL, to='doctors.city'),
        ),
        migrations.AlterField(
            model_name='user',
            name='country',
            field=models.ForeignKey(blank=True, db_column='country', null=True, on_delete=django.db.models.deletion.SET_NULL, to='doctors.country'),
        ),
        migrations.AlterField(
            model_name='user',
            name='experties',
            field=models.ForeignKey(blank=True, db_column='sxpertise', null=True, on_delete=django.db.models.deletion.SET_NULL, to='doctors.expertise'),
        ),
        migrations.CreateModel(
            name='Review',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('patient_name', models.CharField(max_length=255)),
                ('email', models.CharField(max_length=255)),
                ('rating', models.IntegerField()),
                ('comments', models.TextField()),
                ('status', models.CharField(choices=[('accepted', 'Accepted'), ('canceled', 'Canceled'), ('pending', 'Pending')], default='pending', max_length=20)),
                ('created_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(blank=True, null=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='doctors.user')),
            ],
            options={
                'db_table': 'reviews',
            },
        ),
        migrations.AlterField(
            model_name='user',
            name='reviews',
            field=models.ForeignKey(blank=True, db_column='reviwes', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reviewed_users', to='doctors.review'),
        ),
        migrations.AlterField(
            model_name='user',
            name='specialties',
            field=models.ForeignKey(blank=True, db_column='specialties', null=True, on_delete=django.db.models.deletion.SET_NULL, to='doctors.specialties'),
        ),
    ]
