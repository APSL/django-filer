# -*- coding: utf-8 -*-

from __future__ import absolute_import, unicode_literals

from .. import settings as filer_settings
from ..utils.compatibility import python_2_unicode_compatible
from ..utils.loader import load_object
from .abstract import BaseFile

from django.utils.translation import ugettext_lazy as _


if not filer_settings.FILER_FILE_MODEL:
    # This is the standard File model
    @python_2_unicode_compatible
    class File(BaseFile):
        """ Fixed the class as instanciable """

        class Meta(object):
            app_label = 'filer'
            verbose_name = _('file')
            verbose_name_plural = _('files')

else:
    # This is just an alias for the real model defined elsewhere
    # to let imports works transparently
    File = load_object(filer_settings.FILER_FILE_MODEL)



