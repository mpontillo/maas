# Copyright 2014-2017 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for `BootSourceForm`."""

__all__ = []

import random

from django.core.files.uploadedfile import SimpleUploadedFile
from maasserver import forms as forms_module
from maasserver.clusterrpc import osystems
from maasserver.enum import (
    BOOT_RESOURCE_FILE_TYPE,
    BOOT_RESOURCE_TYPE,
)
from maasserver.forms import BootResourceForm
from maasserver.models import BootResource
from maasserver.models.signals import bootsources
from maasserver.testing.architecture import make_usable_architecture
from maasserver.testing.factory import factory
from maasserver.testing.testcase import MAASServerTestCase
from maasserver.utils.orm import reload_object


class TestBootResourceForm(MAASServerTestCase):

    def setUp(self):
        super().setUp()
        self.addCleanup(bootsources.signals.enable)
        bootsources.signals.disable()

    def pick_filetype(self):
        filetypes = {
            'tgz': BOOT_RESOURCE_FILE_TYPE.ROOT_TGZ,
            'ddtgz': BOOT_RESOURCE_FILE_TYPE.ROOT_DDTGZ,
            'ddtar': BOOT_RESOURCE_FILE_TYPE.ROOT_DDTAR,
            'ddraw': BOOT_RESOURCE_FILE_TYPE.ROOT_DDRAW,
            'ddtbz': BOOT_RESOURCE_FILE_TYPE.ROOT_DDTBZ,
            'ddtxz': BOOT_RESOURCE_FILE_TYPE.ROOT_DDTXZ,
            'ddbz2': BOOT_RESOURCE_FILE_TYPE.ROOT_DDBZ2,
            'ddgz': BOOT_RESOURCE_FILE_TYPE.ROOT_DDGZ,
            'ddxz': BOOT_RESOURCE_FILE_TYPE.ROOT_DDXZ
        }

        return random.choice(list(filetypes.items()))

    def test_creates_boot_resource(self):
        name = factory.make_name('name')
        title = factory.make_name('title')
        architecture = make_usable_architecture(self)
        subarch = architecture.split('/')[1]
        upload_type, filetype = self.pick_filetype()
        size = random.randint(1024, 2048)
        content = factory.make_string(size).encode('utf-8')
        upload_name = factory.make_name('filename')
        uploaded_file = SimpleUploadedFile(content=content, name=upload_name)
        data = {
            'name': 'custom/' + name,
            'title': title,
            'architecture': architecture,
            'filetype': upload_type,
            }
        form = BootResourceForm(data=data, files={'content': uploaded_file})
        self.assertTrue(form.is_valid(), form._errors)
        form.save()
        resource = BootResource.objects.get(
            rtype=BOOT_RESOURCE_TYPE.UPLOADED,
            name=name, architecture=architecture)
        resource_set = resource.sets.first()
        rfile = resource_set.files.first()
        self.assertEqual(title, resource.extra['title'])
        self.assertEqual(subarch, resource.extra['subarches'])
        self.assertTrue(filetype, rfile.filetype)
        self.assertTrue(filetype, rfile.filename)
        self.assertTrue(size, rfile.largefile.total_size)
        with rfile.largefile.content.open('rb') as stream:
            written_content = stream.read()
        self.assertEqual(content, written_content)

    def test_prevents_reserved_name(self):
        bsc = factory.make_BootSourceCache()
        upload_type, filetype = self.pick_filetype()
        size = random.randint(1024, 2048)
        content = factory.make_string(size).encode('utf-8')
        upload_name = factory.make_name('filename')
        uploaded_file = SimpleUploadedFile(content=content, name=upload_name)
        data = {
            'name': '%s/%s' % (bsc.os, bsc.release),
            'title': factory.make_name('title'),
            'architecture': make_usable_architecture(self),
            'filetype': upload_type,
            }
        form = BootResourceForm(data=data, files={'content': uploaded_file})
        self.assertFalse(form.is_valid())

    def test_prevents_reserved_osystem(self):
        bsc = factory.make_BootSourceCache()
        upload_type, filetype = self.pick_filetype()
        size = random.randint(1024, 2048)
        content = factory.make_string(size).encode('utf-8')
        upload_name = factory.make_name('filename')
        uploaded_file = SimpleUploadedFile(content=content, name=upload_name)
        data = {
            'name': bsc.os,
            'title': factory.make_name('title'),
            'architecture': make_usable_architecture(self),
            'filetype': upload_type,
            }
        form = BootResourceForm(data=data, files={'content': uploaded_file})
        self.assertFalse(form.is_valid())

    def test_prevents_reserved_release(self):
        bsc = factory.make_BootSourceCache()
        upload_type, filetype = self.pick_filetype()
        size = random.randint(1024, 2048)
        content = factory.make_string(size).encode('utf-8')
        upload_name = factory.make_name('filename')
        uploaded_file = SimpleUploadedFile(content=content, name=upload_name)
        data = {
            'name': bsc.release,
            'title': factory.make_name('title'),
            'architecture': make_usable_architecture(self),
            'filetype': upload_type,
            }
        form = BootResourceForm(data=data, files={'content': uploaded_file})
        self.assertFalse(form.is_valid())

    def test_prevents_reversed_osystem_from_driver(self):
        reserved_name = factory.make_name('name')
        self.patch(
            forms_module, 'gen_all_known_operating_systems').return_value = [{
                'name': reserved_name}]
        upload_type, filetype = self.pick_filetype()
        size = random.randint(1024, 2048)
        content = factory.make_string(size).encode('utf-8')
        upload_name = factory.make_name('filename')
        uploaded_file = SimpleUploadedFile(content=content, name=upload_name)
        data = {
            'name': reserved_name,
            'title': factory.make_name('title'),
            'architecture': make_usable_architecture(self),
            'filetype': upload_type,
            }
        form = BootResourceForm(data=data, files={'content': uploaded_file})
        self.assertFalse(form.is_valid())

    def test_prevents_reserved_centos_names(self):
        reserved_name = 'centos%d' % random.randint(0, 99)
        upload_type, filetype = self.pick_filetype()
        size = random.randint(1024, 2048)
        content = factory.make_string(size).encode('utf-8')
        upload_name = factory.make_name('filename')
        uploaded_file = SimpleUploadedFile(content=content, name=upload_name)
        data = {
            'name': reserved_name,
            'title': factory.make_name('title'),
            'architecture': make_usable_architecture(self),
            'filetype': upload_type,
            }
        form = BootResourceForm(data=data, files={'content': uploaded_file})
        self.assertFalse(form.is_valid())

    def test_adds_boot_resource_set_to_existing_boot_resource(self):
        name = factory.make_name('name')
        architecture = make_usable_architecture(self)
        resource = factory.make_usable_boot_resource(
            rtype=BOOT_RESOURCE_TYPE.UPLOADED,
            name=name, architecture=architecture)
        upload_type, filetype = self.pick_filetype()
        size = random.randint(1024, 2048)
        content = factory.make_string(size).encode('utf-8')
        upload_name = factory.make_name('filename')
        uploaded_file = SimpleUploadedFile(content=content, name=upload_name)
        data = {
            'name': name,
            'architecture': architecture,
            'filetype': upload_type,
            }
        form = BootResourceForm(data=data, files={'content': uploaded_file})
        self.assertTrue(form.is_valid(), form._errors)
        form.save()
        resource = reload_object(resource)
        resource_set = resource.sets.order_by('id').last()
        rfile = resource_set.files.first()
        self.assertTrue(filetype, rfile.filetype)
        self.assertTrue(filetype, rfile.filename)
        self.assertTrue(size, rfile.largefile.total_size)
        with rfile.largefile.content.open('rb') as stream:
            written_content = stream.read()
        self.assertEqual(content, written_content)

    def test_creates_boot_resoures_with_uploaded_rtype(self):
        os = factory.make_name('os')
        self.patch(
            osystems, 'gen_all_known_operating_systems').return_value = [
                {'name': os}]
        series = factory.make_name('series')
        name = '%s/%s' % (os, series)
        architecture = make_usable_architecture(self)
        upload_type, filetype = self.pick_filetype()
        size = random.randint(1024, 2048)
        content = factory.make_string(size).encode('utf-8')
        upload_name = factory.make_name('filename')
        uploaded_file = SimpleUploadedFile(content=content, name=upload_name)
        data = {
            'name': name,
            'architecture': architecture,
            'filetype': upload_type,
            }
        form = BootResourceForm(data=data, files={'content': uploaded_file})
        self.assertTrue(form.is_valid(), form._errors)
        form.save()
        resource = BootResource.objects.get(
            rtype=BOOT_RESOURCE_TYPE.UPLOADED,
            name=name, architecture=architecture)
        resource_set = resource.sets.first()
        rfile = resource_set.files.first()
        self.assertTrue(filetype, rfile.filetype)
        self.assertTrue(filetype, rfile.filename)
        self.assertTrue(size, rfile.largefile.total_size)
        with rfile.largefile.content.open('rb') as stream:
            written_content = stream.read()
        self.assertEqual(content, written_content)

    def test_adds_boot_resource_set_to_existing_generated_boot_resource(self):
        os = factory.make_name('os')
        self.patch(
            osystems, 'gen_all_known_operating_systems').return_value = [
                {'name': os}]
        series = factory.make_name('series')
        name = '%s/%s' % (os, series)
        architecture = make_usable_architecture(self)
        resource = factory.make_usable_boot_resource(
            rtype=BOOT_RESOURCE_TYPE.GENERATED,
            name=name, architecture=architecture)
        upload_type, filetype = self.pick_filetype()
        size = random.randint(1024, 2048)
        content = factory.make_string(size).encode('utf-8')
        upload_name = factory.make_name('filename')
        uploaded_file = SimpleUploadedFile(content=content, name=upload_name)
        data = {
            'name': name,
            'architecture': architecture,
            'filetype': upload_type,
            }
        form = BootResourceForm(data=data, files={'content': uploaded_file})
        self.assertTrue(form.is_valid(), form._errors)
        form.save()
        resource = reload_object(resource)
        resource_set = resource.sets.order_by('id').last()
        rfile = resource_set.files.first()
        self.assertTrue(filetype, rfile.filetype)
        self.assertTrue(filetype, rfile.filename)
        self.assertTrue(size, rfile.largefile.total_size)
        with rfile.largefile.content.open('rb') as stream:
            written_content = stream.read()
        self.assertEqual(content, written_content)
        self.assertEqual(resource.rtype, BOOT_RESOURCE_TYPE.UPLOADED)

    def test_adds_boot_resource_set_to_existing_uploaded_boot_resource(self):
        os = factory.make_name('os')
        self.patch(
            osystems, 'gen_all_known_operating_systems').return_value = [
                {'name': os}]
        series = factory.make_name('series')
        name = '%s/%s' % (os, series)
        architecture = make_usable_architecture(self)
        resource = factory.make_usable_boot_resource(
            rtype=BOOT_RESOURCE_TYPE.UPLOADED,
            name=name, architecture=architecture)
        upload_type, filetype = self.pick_filetype()
        size = random.randint(1024, 2048)
        content = factory.make_string(size).encode('utf-8')
        upload_name = factory.make_name('filename')
        uploaded_file = SimpleUploadedFile(content=content, name=upload_name)
        data = {
            'name': name,
            'architecture': architecture,
            'filetype': upload_type,
            }
        form = BootResourceForm(data=data, files={'content': uploaded_file})
        self.assertTrue(form.is_valid(), form._errors)
        form.save()
        resource = reload_object(resource)
        resource_set = resource.sets.order_by('id').last()
        rfile = resource_set.files.first()
        self.assertTrue(filetype, rfile.filetype)
        self.assertTrue(filetype, rfile.filename)
        self.assertTrue(size, rfile.largefile.total_size)
        with rfile.largefile.content.open('rb') as stream:
            written_content = stream.read()
        self.assertEqual(content, written_content)
        self.assertEqual(resource.rtype, BOOT_RESOURCE_TYPE.UPLOADED)

    def test_requires_fields(self):
        form = BootResourceForm(data={})
        self.assertFalse(form.is_valid(), form.errors)
        self.assertItemsEqual([
            'name', 'architecture', 'filetype', 'content',
            ],
            form.errors.keys())
