# -*- coding: utf-8 -*-
from __future__ import absolute_import

import json

from django.conf.urls import url
from django.contrib import admin
from django.forms.models import modelform_factory
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import View

from . import views
from .. import settings as filer_settings
from ..models import Clipboard, ClipboardItem, Folder, Image
from ..models.abstract import DJANGO_GTE_17
from ..utils.compatibility import LTE_DJANGO_1_4
from ..utils.files import (
    UploadException, handle_request_files_upload, handle_upload,
)
from ..utils.loader import load_object

NO_FOLDER_ERROR = "Can't find folder to upload. Please refresh and try again"
NO_PERMISSIONS_FOR_FOLDER = (
    "Can't use this folder, Permission Denied. Please select another folder."
)


# ModelAdmins
class ClipboardItemInline(admin.TabularInline):
    model = ClipboardItem


class ClipboardAdmin(admin.ModelAdmin):
    model = Clipboard
    inlines = [ClipboardItemInline]
    filter_horizontal = ('files',)
    raw_id_fields = ('user',)
    verbose_name = "DEBUG Clipboard"
    verbose_name_plural = "DEBUG Clipboards"

    def get_urls(self):
        return [
            url(r'^operations/paste_clipboard_to_folder/$',
                self.admin_site.admin_view(views.paste_clipboard_to_folder),
                name='filer-paste_clipboard_to_folder'),
            url(r'^operations/discard_clipboard/$',
                self.admin_site.admin_view(views.discard_clipboard),
                name='filer-discard_clipboard'),
            url(r'^operations/delete_clipboard/$',
                self.admin_site.admin_view(views.delete_clipboard),
                name='filer-delete_clipboard'),
            url(r'^operations/upload/(?P<folder_id>[0-9]+)/$',
                AjaxUploadView.as_view(),
                name='filer-ajax_upload'),
            url(r'^operations/upload/no_folder/$',
                AjaxUploadView.as_view(),
                name='filer-ajax_upload'),
        ] + super(ClipboardAdmin, self).get_urls()

    def get_model_perms(self, *args, **kwargs):
        """
        It seems this is only used for the list view. NICE :-)
        """
        return {
            'add': False,
            'change': False,
            'delete': False,
        }


class AjaxUploadView(View):
    folder = None

    @csrf_exempt
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        return self.ajax_upload()

    def post(self, request, *args, **kwargs):
        return self.ajax_upload()

    def ajax_upload(self):
        try:
            form = self.get_form()
            if form.is_valid():
                context = self.form_valid(form)
                context.pop('instance', None)
            else:
                context = self.form_invalid(form)
        except (UploadException, Exception) as ue:
            context = {'data': {'error': str(ue)}}
        except Exception as e:
            context = {'data': {'error': str(e)}}

        finally:

            return HttpResponse(context.pop('data', ''), **context)

    @property
    def response_params(self):
        mimetype = "application/json" if self.request.is_ajax() else "text/html"
        content_type_key = 'mimetype' if LTE_DJANGO_1_4 else 'content_type'
        return {content_type_key: mimetype}

    def get_folder(self):
        folder_id = self.kwargs.get('folder_id')
        if folder_id:
            try:
                # Get folder
                folder = Folder.objects.get(pk=folder_id)
            except Folder.DoesNotExist:
                raise UploadException(NO_FOLDER_ERROR)

        # check permissions
        if folder and not folder.has_add_children_permission(self.request):
            raise UploadException(NO_PERMISSIONS_FOR_FOLDER)

        return folder

    def get_form(self):
        try:
            if len(self.request.FILES) == 1:
                # dont check if request is ajax or not, just grab the file
                upload, filename, is_raw = handle_request_files_upload(
                    self.request
                )
            else:
                # else process the request as usual
                upload, filename, is_raw = handle_upload(self.request)

            # find the file type
            for filer_class in filer_settings.FILER_FILE_MODELS:
                FileSubClass = load_object(filer_class)
                if FileSubClass.matches_file_type(
                        filename, upload, self.request):
                    FileForm = modelform_factory(
                        model=FileSubClass,
                        fields=('original_filename', 'owner', 'file')
                    )
                    break

            return FileForm(
                {'original_filename': filename,
                 'owner': self.request.user.pk},
                {'file': upload}
            )

        except Exception as e:
            raise UploadException(str(e))

    def form_valid(self, form):
        folder = self.get_folder()
        file_obj = form.save(commit=False)
        # Enforce the FILER_IS_PUBLIC_DEFAULT
        file_obj.is_public = filer_settings.FILER_IS_PUBLIC_DEFAULT
        file_obj.folder = folder
        file_obj.save()

        # TODO: Deprecated/refactor
        # clipboard_item = ClipboardItem(
        #     clipboard=clipboard, file=file_obj)
        # clipboard_item.save()

        # Try to generate thumbnails.
        if not file_obj.icons:
            # There is no point to continue, as we can't generate
            # thumbnails for this file. Usual reasons: bad format or
            # filename.
            file_obj.delete()
            # This would be logged in BaseImage._generate_thumbnails()
            # if FILER_ENABLE_LOGGING is on.
            context = {
                'data': {'error': 'failed to generate icons for file'},
                'status': 500
            }
            context.update(**self.response_params)
            return context

        thumbnail = None
        # Backwards compatibility: try to get specific icon size (32px)
        # first. Then try medium icon size (they are already sorted),
        # fallback to the first (smallest) configured icon.
        for size in (['32'] +
                     filer_settings.FILER_ADMIN_ICON_SIZES[1::-1]):
            try:
                thumbnail = file_obj.icons[size]
                break
            except KeyError:
                continue

        json_response = {
            'thumbnail': thumbnail,
            'alt_text': '',
            'label': str(file_obj),
            'file_id': file_obj.pk,
        }
        # prepare preview thumbnail
        if type(file_obj) == Image:
            thumbnail_180_options = {
                'size': (180, 180),
                'crop': True,
                'upscale': True,
            }
            thumbnail_180 = file_obj.file.get_thumbnail(
                thumbnail_180_options)
            json_response['thumbnail_180'] = thumbnail_180.url
            json_response['original_image'] = file_obj.url

        context = {
            'data': json.dumps(json_response),
            'instance': file_obj
        }
        context.update(**self.response_params)
        return context

    def form_invalid(self, form):
        form_errors = '; '.join(
            ['%s: %s' % (field, ', '.join(errors)) for field, errors in list(
                form.errors.items())]
        )
        raise UploadException(
            "AJAX request not valid: form invalid '{}'".format(form_errors)
        )
