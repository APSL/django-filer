# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from filer.settings import FILER_FILE_MODEL


class Migration(migrations.Migration):

    dependencies = [
        ('filer', '0001_initial'),
    ]

    if not FILER_FILE_MODEL:
        operations = [
            migrations.AlterField(
                model_name='file',
                name='polymorphic_ctype',
                field=models.ForeignKey(related_name='polymorphic_filer.file_set+', editable=False, to='contenttypes.ContentType', null=True),
                preserve_default=True,
            ),
        ]
