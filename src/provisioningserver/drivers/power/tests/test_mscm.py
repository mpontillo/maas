# Copyright 2015 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for `provisioningserver.drivers.power.mscm`."""

from __future__ import (
    absolute_import,
    print_function,
    unicode_literals,
    )

str = None

__metaclass__ = type
__all__ = []

from maastesting.factory import factory
from maastesting.matchers import MockCalledOnceWith
from maastesting.testcase import MAASTestCase
from provisioningserver.drivers.hardware.tests.test_mscm import make_node_id
from provisioningserver.drivers.power import mscm as mscm_module
from provisioningserver.drivers.power.mscm import (
    extract_mscm_parameters,
    MSCMPowerDriver,
)
from testtools.matchers import Equals


class TestMSCMPowerDriver(MAASTestCase):

    def make_parameters(self):
        system_id = factory.make_name('system_id')
        host = factory.make_name('power_address')
        username = factory.make_name('power_user')
        password = factory.make_name('power_pass')
        node_id = make_node_id()
        return system_id, host, username, password, node_id

    def test_extract_mscm_parameters_extracts_parameters(self):
        system_id, host, username, password, node_id = self.make_parameters()
        params = {
            'system_id': system_id,
            'power_address': host,
            'power_user': username,
            'power_pass': password,
            'node_id': node_id,
        }

        self.assertItemsEqual(
            (host, username, password, node_id),
            extract_mscm_parameters(params))

    def test_power_on_calls_power_control_mscm(self):
        system_id, host, username, password, node_id = self.make_parameters()
        params = {
            'system_id': system_id,
            'power_address': host,
            'power_user': username,
            'power_pass': password,
            'node_id': node_id,
        }
        mscm_power_driver = MSCMPowerDriver()
        power_control_mscm = self.patch(
            mscm_module, 'power_control_mscm')
        mscm_power_driver.power_on(**params)

        self.assertThat(
            power_control_mscm, MockCalledOnceWith(
                host, username, password, node_id, power_change='on'))

    def test_power_off_calls_power_control_mscm(self):
        system_id, host, username, password, node_id = self.make_parameters()
        params = {
            'system_id': system_id,
            'power_address': host,
            'power_user': username,
            'power_pass': password,
            'node_id': node_id,
        }
        mscm_power_driver = MSCMPowerDriver()
        power_control_mscm = self.patch(
            mscm_module, 'power_control_mscm')
        mscm_power_driver.power_off(**params)

        self.assertThat(
            power_control_mscm, MockCalledOnceWith(
                host, username, password, node_id, power_change='off'))

    def test_power_query_calls_power_state_mscm(self):
        system_id, host, username, password, node_id = self.make_parameters()
        params = {
            'system_id': system_id,
            'power_address': host,
            'power_user': username,
            'power_pass': password,
            'node_id': node_id,
        }
        mscm_power_driver = MSCMPowerDriver()
        power_state_mscm = self.patch(
            mscm_module, 'power_state_mscm')
        power_state_mscm.return_value = 'off'
        expected_result = mscm_power_driver.power_query(**params)

        self.expectThat(
            power_state_mscm, MockCalledOnceWith(
                host, username, password, node_id))
        self.expectThat(expected_result, Equals('off'))