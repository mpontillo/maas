# Copyright 2014 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the ssl key API."""

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
from maasserver.models import SSLKey
from maasserver.testing import get_data
from maasserver.testing.api import APITestCase
from maasserver.testing.factory import factory
from maasserver.utils.orm import get_one


class TestSSLKeyHandlers(APITestCase):

    def test_sslkeys_handler_path(self):
        self.assertEqual(
            '/api/1.0/account/prefs/sslkeys/', reverse('sslkeys_handler'))

    def test_sslkey_handler_path(self):
        self.assertEqual(
            '/api/1.0/account/prefs/sslkeys/key/',
            reverse('sslkey_handler', args=['key']))

    def test_list_works(self):
        _, keys = factory.make_user_with_ssl_keys(
            n_keys=2, user=self.logged_in_user)
        params = dict(op="list")
        response = self.client.get(
            reverse('sslkeys_handler'), params)
        self.assertEqual(httplib.OK, response.status_code, response)
        parsed_result = json.loads(response.content)
        parsed_result = [result['resource_uri'] for result in parsed_result]
        expected_result = [
            reverse('sslkey_handler', args=[keys[0].id]),
            reverse('sslkey_handler', args=[keys[1].id]),
            ]
        self.assertItemsEqual(expected_result, parsed_result)

    def test_list_sorts_output(self):
        _, keys = factory.make_user_with_ssl_keys(
            n_keys=2, user=self.logged_in_user)
        params = dict(op="list")
        response = self.client.get(
            reverse('sslkeys_handler'), params)
        self.assertEqual(httplib.OK, response.status_code, response)
        parsed_result = json.loads(response.content)
        parsed_result = [result['resource_uri'] for result in parsed_result]
        expected_result = [
            reverse('sslkey_handler', args=[keys[0].id]),
            reverse('sslkey_handler', args=[keys[1].id]),
            ]
        self.assertEqual(expected_result, parsed_result)

    def test_list_only_shows_user_keys(self):
        # other user
        factory.make_user_with_ssl_keys(n_keys=2)
        _, keys = factory.make_user_with_ssl_keys(
            n_keys=2, user=self.logged_in_user)
        params = dict(op="list")
        response = self.client.get(
            reverse('sslkeys_handler'), params)
        self.assertEqual(httplib.OK, response.status_code, response)
        parsed_result = json.loads(response.content)
        parsed_result = [result['resource_uri'] for result in parsed_result]
        expected_result = [
            reverse('sslkey_handler', args=[keys[0].id]),
            reverse('sslkey_handler', args=[keys[1].id]),
            ]
        self.assertItemsEqual(expected_result, parsed_result)

    def test_list_only_shows_user_keys_for_admin(self):
        # other user
        factory.make_user_with_ssl_keys(n_keys=2)
        _, keys = factory.make_user_with_ssl_keys(
            n_keys=2, user=self.logged_in_user)
        self.become_admin()
        params = dict(op="list")
        response = self.client.get(
            reverse('sslkeys_handler'), params)
        self.assertEqual(httplib.OK, response.status_code, response)
        parsed_result = json.loads(response.content)
        parsed_result = [result['resource_uri'] for result in parsed_result]
        expected_result = [
            reverse('sslkey_handler', args=[keys[0].id]),
            reverse('sslkey_handler', args=[keys[1].id]),
            ]
        self.assertItemsEqual(expected_result, parsed_result)

    def test_get_by_id_works(self):
        _, keys = factory.make_user_with_ssl_keys(
            n_keys=1, user=self.logged_in_user)
        key = keys[0]
        response = self.client.get(
            reverse('sslkey_handler', args=[key.id]))
        self.assertEqual(httplib.OK, response.status_code, response)
        parsed_result = json.loads(response.content)
        expected = dict(
            id=key.id,
            key=key.key,
            resource_uri=reverse('sslkey_handler', args=[key.id]),
            )
        self.assertEqual(expected, parsed_result)

    def test_get_by_id_fails_for_non_owner(self):
        _, keys = factory.make_user_with_ssl_keys(n_keys=1)
        factory.make_user_with_ssl_keys(
            n_keys=1, user=self.logged_in_user)
        key = keys[0]
        response = self.client.get(
            reverse('sslkey_handler', args=[key.id]))
        self.assertEqual(httplib.FORBIDDEN, response.status_code, response)

    def test_get_by_id_fails_for_non_owner_as_admin(self):
        _, keys = factory.make_user_with_ssl_keys(n_keys=1)
        factory.make_user_with_ssl_keys(
            n_keys=1, user=self.logged_in_user)
        self.become_admin()
        key = keys[0]
        response = self.client.get(
            reverse('sslkey_handler', args=[key.id]))
        self.assertEqual(httplib.FORBIDDEN, response.status_code, response)

    def test_delete_by_id_works(self):
        _, keys = factory.make_user_with_ssl_keys(
            n_keys=2, user=self.logged_in_user)
        response = self.client.delete(
            reverse('sslkey_handler', args=[keys[0].id]))
        self.assertEqual(httplib.NO_CONTENT, response.status_code, response)
        keys_after = SSLKey.objects.filter(user=self.logged_in_user)
        self.assertEqual(1, len(keys_after))
        self.assertEqual(keys[1].id, keys_after[0].id)

    def test_delete_fails_if_not_your_key(self):
        user, keys = factory.make_user_with_ssl_keys(n_keys=1)
        response = self.client.delete(
            reverse('sslkey_handler', args=[keys[0].id]))
        self.assertEqual(httplib.FORBIDDEN, response.status_code, response)
        self.assertEqual(1, len(SSLKey.objects.filter(user=user)))

    def test_adding_works(self):
        key_string = get_data('data/test_x509_0.pem')
        response = self.client.post(
            reverse('sslkeys_handler'),
            data=dict(op="new", key=key_string))
        self.assertEqual(httplib.CREATED, response.status_code)
        parsed_response = json.loads(response.content)
        self.assertEqual(key_string, parsed_response["key"])
        added_key = get_one(SSLKey.objects.filter(user=self.logged_in_user))
        self.assertEqual(key_string, added_key.key)

    def test_adding_catches_key_validation_errors(self):
        key_string = factory.getRandomString()
        response = self.client.post(
            reverse('sslkeys_handler'),
            data=dict(op='new', key=key_string))
        self.assertEqual(httplib.BAD_REQUEST, response.status_code, response)
        self.assertIn("Invalid", response.content)

    def test_adding_returns_badrequest_when_key_not_in_form(self):
        response = self.client.post(
            reverse('sslkeys_handler'),
            data=dict(op='new'))
        self.assertEqual(httplib.BAD_REQUEST, response.status_code, response)
        self.assertEqual(
            dict(key=["This field is required."]),
            json.loads(response.content))
