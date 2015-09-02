# Copyright 2014-2015 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the `Boot Sources` API."""

from __future__ import (
    absolute_import,
    print_function,
    unicode_literals,
    )

str = None

__metaclass__ = type
__all__ = []

import httplib
import json

from django.core.urlresolvers import reverse
from maasserver.api.boot_sources import DISPLAYED_BOOTSOURCE_FIELDS
from maasserver.models import BootSource
from maasserver.models.testing import UpdateBootSourceCacheDisconnected
from maasserver.testing.api import APITestCase
from maasserver.testing.factory import factory
from maasserver.testing.orm import reload_object
from maastesting.utils import sample_binary_data
from testtools.matchers import MatchesStructure


def get_boot_source_uri(boot_source):
    """Return a boot source's URI on the API."""
    return reverse(
        'boot_source_handler',
        args=[boot_source.id])


def get_boot_source_backward_uri(boot_source, nodegroup=None):
    if nodegroup is None:
        nodegroup = factory.make_NodeGroup()
    return reverse(
        'boot_source_backward_handler',
        args=[nodegroup.uuid, boot_source.id])


class TestBootSourceAPI(APITestCase):

    def setUp(self):
        super(TestBootSourceAPI, self).setUp()
        self.useFixture(UpdateBootSourceCacheDisconnected())

    def test_handler_path(self):
        self.assertEqual(
            '/api/1.0/boot-sources/3/',
            reverse('boot_source_handler', args=['3']))

    def test_GET_returns_boot_source(self):
        self.become_admin()
        boot_source = factory.make_BootSource()
        response = self.client.get(get_boot_source_uri(boot_source))
        self.assertEqual(httplib.OK, response.status_code)
        returned_boot_source = json.loads(response.content)
        # The returned object contains a 'resource_uri' field.
        self.assertEqual(
            reverse(
                'boot_source_handler',
                args=[boot_source.id]
            ),
            returned_boot_source['resource_uri'])
        # The other fields are the boot source's fields.
        del returned_boot_source['resource_uri']
        # All the fields are present.
        self.assertItemsEqual(
            DISPLAYED_BOOTSOURCE_FIELDS, returned_boot_source.keys())
        self.assertThat(
            boot_source,
            MatchesStructure.byEquality(**returned_boot_source))

    def test_GET_requires_admin(self):
        boot_source = factory.make_BootSource()
        response = self.client.get(get_boot_source_uri(boot_source))
        self.assertEqual(httplib.FORBIDDEN, response.status_code)

    def test_DELETE_deletes_boot_source(self):
        self.become_admin()
        boot_source = factory.make_BootSource()
        response = self.client.delete(get_boot_source_uri(boot_source))
        self.assertEqual(httplib.NO_CONTENT, response.status_code)
        self.assertIsNone(reload_object(boot_source))

    def test_DELETE_requires_admin(self):
        boot_source = factory.make_BootSource()
        response = self.client.delete(get_boot_source_uri(boot_source))
        self.assertEqual(httplib.FORBIDDEN, response.status_code)

    def test_PUT_updates_boot_source(self):
        self.become_admin()
        boot_source = factory.make_BootSource()
        new_values = {
            'url': 'http://example.com/',
            'keyring_filename': factory.make_name('filename'),
        }
        response = self.client.put(
            get_boot_source_uri(boot_source), new_values)
        self.assertEqual(httplib.OK, response.status_code)
        boot_source = reload_object(boot_source)
        self.assertAttributes(boot_source, new_values)

    def test_PUT_requires_admin(self):
        boot_source = factory.make_BootSource()
        new_values = {
            'url': 'http://example.com/',
            'keyring_filename': factory.make_name('filename'),
        }
        response = self.client.put(
            get_boot_source_uri(boot_source), new_values)
        self.assertEqual(httplib.FORBIDDEN, response.status_code)


class TestBootSourceBackwardAPI(APITestCase):

    def setUp(self):
        super(TestBootSourceBackwardAPI, self).setUp()
        self.useFixture(UpdateBootSourceCacheDisconnected())

    def test_handler_path(self):
        self.assertEqual(
            '/api/1.0/nodegroups/uuid/boot-sources/3/',
            reverse('boot_source_backward_handler', args=['uuid', '3']))

    def test_GET_returns_boot_source(self):
        self.become_admin()
        boot_source = factory.make_BootSource()
        response = self.client.get(get_boot_source_backward_uri(boot_source))
        self.assertEqual(httplib.OK, response.status_code)
        returned_boot_source = json.loads(response.content)
        # The returned object contains a 'resource_uri' field.
        self.assertEqual(
            reverse(
                'boot_source_handler',
                args=[boot_source.id]
            ),
            returned_boot_source['resource_uri'])
        # The other fields are the boot source's fields.
        del returned_boot_source['resource_uri']
        # All the fields are present.
        self.assertItemsEqual(
            DISPLAYED_BOOTSOURCE_FIELDS, returned_boot_source.keys())
        self.assertThat(
            boot_source,
            MatchesStructure.byEquality(**returned_boot_source))

    def test_GET_returns_same_boot_source_no_matter_the_nodegroup(self):
        self.become_admin()
        boot_source = factory.make_BootSource()
        for _ in range(3):
            nodegroup = factory.make_NodeGroup()
            response = self.client.get(
                get_boot_source_backward_uri(boot_source, nodegroup))
            self.assertEqual(httplib.OK, response.status_code)
            returned_boot_source = json.loads(response.content)
            del returned_boot_source['resource_uri']
            self.assertThat(
                boot_source,
                MatchesStructure.byEquality(**returned_boot_source))

    def test_GET_requires_admin(self):
        boot_source = factory.make_BootSource()
        response = self.client.get(get_boot_source_backward_uri(boot_source))
        self.assertEqual(httplib.FORBIDDEN, response.status_code)

    def test_DELETE_deletes_boot_source(self):
        self.become_admin()
        boot_source = factory.make_BootSource()
        response = self.client.delete(
            get_boot_source_backward_uri(boot_source))
        self.assertEqual(httplib.NO_CONTENT, response.status_code)
        self.assertIsNone(reload_object(boot_source))

    def test_DELETE_requires_admin(self):
        boot_source = factory.make_BootSource()
        response = self.client.delete(
            get_boot_source_backward_uri(boot_source))
        self.assertEqual(httplib.FORBIDDEN, response.status_code)

    def test_PUT_updates_boot_source(self):
        self.become_admin()
        boot_source = factory.make_BootSource()
        new_values = {
            'url': 'http://example.com/',
            'keyring_filename': factory.make_name('filename'),
        }
        response = self.client.put(
            get_boot_source_backward_uri(boot_source), new_values)
        self.assertEqual(httplib.OK, response.status_code)
        boot_source = reload_object(boot_source)
        self.assertAttributes(boot_source, new_values)

    def test_PUT_requires_admin(self):
        boot_source = factory.make_BootSource()
        new_values = {
            'url': 'http://example.com/',
            'keyring_filename': factory.make_name('filename'),
        }
        response = self.client.put(
            get_boot_source_backward_uri(boot_source), new_values)
        self.assertEqual(httplib.FORBIDDEN, response.status_code)


class TestBootSourcesAPI(APITestCase):
    """Test the the boot source API."""

    def setUp(self):
        super(TestBootSourcesAPI, self).setUp()
        self.useFixture(UpdateBootSourceCacheDisconnected())

    def test_handler_path(self):
        self.assertEqual(
            '/api/1.0/boot-sources/',
            reverse('boot_sources_handler'))

    def test_GET_returns_boot_source_list(self):
        self.become_admin()
        sources = [
            factory.make_BootSource() for _ in range(3)]
        response = self.client.get(
            reverse('boot_sources_handler'))
        self.assertEqual(httplib.OK, response.status_code, response.content)
        parsed_result = json.loads(response.content)
        self.assertItemsEqual(
            [boot_source.id for boot_source in sources],
            [boot_source.get('id') for boot_source in parsed_result])

    def test_GET_requires_admin(self):
        response = self.client.get(
            reverse('boot_sources_handler'))
        self.assertEqual(httplib.FORBIDDEN, response.status_code)

    def test_POST_creates_boot_source_with_keyring_filename(self):
        self.become_admin()

        params = {
            'url': 'http://example.com/',
            'keyring_filename': factory.make_name('filename'),
            'keyring_data': '',
        }
        response = self.client.post(
            reverse('boot_sources_handler'), params)
        self.assertEqual(httplib.CREATED, response.status_code)
        parsed_result = json.loads(response.content)

        boot_source = BootSource.objects.get(id=parsed_result['id'])
        # boot_source.keyring_data is returned as a read-only buffer, test
        # it separately from the rest of the attributes.
        self.assertEqual('', bytes(boot_source.keyring_data))
        del params['keyring_data']
        self.assertAttributes(boot_source, params)

    def test_POST_creates_boot_source_with_keyring_data(self):
        self.become_admin()

        params = {
            'url': 'http://example.com/',
            'keyring_filename': '',
            'keyring_data': (
                factory.make_file_upload(content=sample_binary_data)),
        }
        response = self.client.post(
            reverse('boot_sources_handler'), params)
        self.assertEqual(httplib.CREATED, response.status_code)
        parsed_result = json.loads(response.content)

        boot_source = BootSource.objects.get(id=parsed_result['id'])
        # boot_source.keyring_data is returned as a read-only buffer, test
        # it separately from the rest of the attributes.
        self.assertEqual(sample_binary_data, bytes(boot_source.keyring_data))
        del params['keyring_data']
        self.assertAttributes(boot_source, params)

    def test_POST_validates_boot_source(self):
        self.become_admin()

        params = {
            'url': 'http://example.com/',
        }
        response = self.client.post(
            reverse('boot_sources_handler'), params)
        self.assertEqual(httplib.BAD_REQUEST, response.status_code)

    def test_POST_requires_admin(self):
        params = {
            'url': 'http://example.com/',
            'keyring_filename': '',
            'keyring_data': (
                factory.make_file_upload(content=sample_binary_data)),
        }
        response = self.client.post(
            reverse('boot_sources_handler'), params)
        self.assertEqual(httplib.FORBIDDEN, response.status_code)


class TestBootSourcesBackwardAPI(APITestCase):
    """Test the the boot source API."""

    def setUp(self):
        super(TestBootSourcesBackwardAPI, self).setUp()
        self.useFixture(UpdateBootSourceCacheDisconnected())

    def get_uri(self, nodegroup=None):
        if nodegroup is None:
            nodegroup = factory.make_NodeGroup()
        return reverse(
            'boot_sources_backward_handler', args=[nodegroup.uuid])

    def test_handler_path(self):
        self.assertEqual(
            '/api/1.0/nodegroups/uuid/boot-sources/',
            reverse('boot_sources_backward_handler', args=['uuid']))

    def test_GET_returns_boot_source_list(self):
        self.become_admin()
        sources = [
            factory.make_BootSource() for _ in range(3)]
        response = self.client.get(self.get_uri())
        self.assertEqual(httplib.OK, response.status_code, response.content)
        parsed_result = json.loads(response.content)
        self.assertItemsEqual(
            [boot_source.id for boot_source in sources],
            [boot_source.get('id') for boot_source in parsed_result])

    def test_GET_returns_same_list_for_different_node_groups(self):
        self.become_admin()
        sources = [
            factory.make_BootSource() for _ in range(3)]
        for _ in range(3):
            nodegroup = factory.make_NodeGroup()
            response = self.client.get(self.get_uri(nodegroup))
            self.assertEqual(
                httplib.OK, response.status_code, response.content)
            parsed_result = json.loads(response.content)
            self.assertItemsEqual(
                [boot_source.id for boot_source in sources],
                [boot_source.get('id') for boot_source in parsed_result])

    def test_GET_requires_admin(self):
        response = self.client.get(self.get_uri())
        self.assertEqual(httplib.FORBIDDEN, response.status_code)

    def test_POST_creates_boot_source_with_keyring_filename(self):
        self.become_admin()

        params = {
            'url': 'http://example.com/',
            'keyring_filename': factory.make_name('filename'),
            'keyring_data': '',
        }
        response = self.client.post(self.get_uri(), params)
        self.assertEqual(httplib.CREATED, response.status_code)
        parsed_result = json.loads(response.content)

        boot_source = BootSource.objects.get(id=parsed_result['id'])
        # boot_source.keyring_data is returned as a read-only buffer, test
        # it separately from the rest of the attributes.
        self.assertEqual('', bytes(boot_source.keyring_data))
        del params['keyring_data']
        self.assertAttributes(boot_source, params)

    def test_POST_creates_boot_source_with_keyring_data(self):
        self.become_admin()

        params = {
            'url': 'http://example.com/',
            'keyring_filename': '',
            'keyring_data': (
                factory.make_file_upload(content=sample_binary_data)),
        }
        response = self.client.post(self.get_uri(), params)
        self.assertEqual(httplib.CREATED, response.status_code)
        parsed_result = json.loads(response.content)

        boot_source = BootSource.objects.get(id=parsed_result['id'])
        # boot_source.keyring_data is returned as a read-only buffer, test
        # it separately from the rest of the attributes.
        self.assertEqual(sample_binary_data, bytes(boot_source.keyring_data))
        del params['keyring_data']
        self.assertAttributes(boot_source, params)

    def test_POST_validates_boot_source(self):
        self.become_admin()

        params = {
            'url': 'http://example.com/',
        }
        response = self.client.post(self.get_uri(), params)
        self.assertEqual(httplib.BAD_REQUEST, response.status_code)

    def test_POST_requires_admin(self):
        params = {
            'url': 'http://example.com/',
            'keyring_filename': '',
            'keyring_data': (
                factory.make_file_upload(content=sample_binary_data)),
        }
        response = self.client.post(self.get_uri(), params)
        self.assertEqual(httplib.FORBIDDEN, response.status_code)