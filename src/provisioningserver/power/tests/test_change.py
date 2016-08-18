# Copyright 2015-2016 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for :py:module:`~provisioningserver.power.change`."""

__all__ = []

import random
from unittest.mock import (
    ANY,
    sentinel,
)

from maastesting.factory import factory
from maastesting.matchers import MockCalledOnceWith
from maastesting.testcase import (
    MAASTestCase,
    MAASTwistedRunTest,
)
from maastesting.twisted import (
    always_succeed_with,
    extract_result,
    TwistedLoggerFixture,
)
from provisioningserver import power
from provisioningserver.drivers.power import (
    get_error_message as get_driver_error_message,
    power_drivers_by_name,
    PowerDriverRegistry,
    PowerError,
)
from provisioningserver.events import EVENT_TYPES
from provisioningserver.rpc import (
    exceptions,
    region,
)
from provisioningserver.rpc.testing import (
    MockClusterToRegionRPCFixture,
    MockLiveClusterToRegionRPCFixture,
)
from provisioningserver.testing.events import EventTypesAllRegistered
from testtools import ExpectedException
from testtools.matchers import (
    Equals,
    IsInstance,
)
from twisted.internet import reactor
from twisted.internet.defer import (
    Deferred,
    fail,
    inlineCallbacks,
    returnValue,
    succeed,
)
from twisted.internet.task import Clock


class TestPowerHelpers(MAASTestCase):

    run_tests_with = MAASTwistedRunTest.make_factory(timeout=5)

    def setUp(self):
        super(TestPowerHelpers, self).setUp()
        self.useFixture(EventTypesAllRegistered())

    def patch_rpc_methods(self):
        fixture = self.useFixture(MockClusterToRegionRPCFixture())
        protocol, io = fixture.makeEventLoop(
            region.MarkNodeFailed, region.UpdateNodePowerState,
            region.SendEvent)
        return protocol, io

    def test_power_change_success_emits_event(self):
        system_id = factory.make_name('system_id')
        hostname = factory.make_name('hostname')
        power_change = 'on'
        protocol, io = self.patch_rpc_methods()
        d = power.change.power_change_success(
            system_id, hostname, power_change)
        io.flush()
        self.assertThat(
            protocol.UpdateNodePowerState,
            MockCalledOnceWith(
                ANY,
                system_id=system_id,
                power_state=power_change)
        )
        self.assertThat(
            protocol.SendEvent,
            MockCalledOnceWith(
                ANY,
                type_name=EVENT_TYPES.NODE_POWERED_ON,
                system_id=system_id,
                description='')
        )
        self.assertIsNone(extract_result(d))

    def test_power_change_starting_emits_event(self):
        system_id = factory.make_name('system_id')
        hostname = factory.make_name('hostname')
        power_change = 'on'
        protocol, io = self.patch_rpc_methods()
        d = power.change.power_change_starting(
            system_id, hostname, power_change)
        io.flush()
        self.assertThat(
            protocol.SendEvent,
            MockCalledOnceWith(
                ANY,
                type_name=EVENT_TYPES.NODE_POWER_ON_STARTING,
                system_id=system_id,
                description='')
        )
        self.assertIsNone(extract_result(d))

    def test_power_change_failure_emits_event(self):
        system_id = factory.make_name('system_id')
        hostname = factory.make_name('hostname')
        message = factory.make_name('message')
        power_change = 'on'
        protocol, io = self.patch_rpc_methods()
        d = power.change.power_change_failure(
            system_id, hostname, power_change, message)
        io.flush()
        self.assertThat(
            protocol.SendEvent,
            MockCalledOnceWith(
                ANY,
                type_name=EVENT_TYPES.NODE_POWER_ON_FAILED,
                system_id=system_id,
                description=message)
        )
        self.assertIsNone(extract_result(d))


class TestChangePowerState(MAASTestCase):

    run_tests_with = MAASTwistedRunTest.make_factory(timeout=5)

    def setUp(self):
        super(TestChangePowerState, self).setUp()
        self.useFixture(EventTypesAllRegistered())

    @inlineCallbacks
    def patch_rpc_methods(self, return_value={}, side_effect=None):
        fixture = self.useFixture(MockLiveClusterToRegionRPCFixture())
        protocol, connecting = fixture.makeEventLoop(
            region.MarkNodeFailed, region.UpdateNodePowerState,
            region.SendEvent)
        protocol.MarkNodeFailed.return_value = return_value
        protocol.MarkNodeFailed.side_effect = side_effect
        self.addCleanup((yield connecting))
        returnValue(protocol.MarkNodeFailed)

    def test_change_power_state_calls_power_change_starting_early_on(self):
        # The first, or one of the first, things that change_power_state()
        # does is write to the node event log via power_change_starting().

        class ArbitraryException(Exception):
            """This allows us to return early from a function."""

        # Raise this exception when power_change_starting() is called, to
        # return early from change_power_state(). This lets us avoid set-up
        # for parts of the function that we're presently not interested in.
        pcs = self.patch_autospec(power.change, "power_change_starting")
        pcs.return_value = fail(ArbitraryException())

        d = power.change.change_power_state(
            sentinel.system_id, sentinel.hostname, sentinel.power_type,
            sentinel.power_change, sentinel.context)
        self.assertRaises(ArbitraryException, extract_result, d)
        self.assertThat(
            power.change.power_change_starting, MockCalledOnceWith(
                sentinel.system_id, sentinel.hostname, sentinel.power_change))

    @inlineCallbacks
    def test___handles_power_driver_power_types(self):
        system_id = factory.make_name('system_id')
        hostname = factory.make_name('hostname')
        power_type = random.choice(power.QUERY_POWER_TYPES)
        power_change = random.choice(['on', 'off'])
        context = {
            factory.make_name('context-key'): factory.make_name('context-val')
        }
        self.patch(power, 'is_driver_available').return_value = True
        perform_power_driver_change = self.patch_autospec(
            power.change, 'perform_power_driver_change')
        perform_power_driver_query = self.patch_autospec(
            power.query, 'perform_power_driver_query')
        perform_power_driver_query.return_value = succeed(power_change)
        power_change_success = self.patch_autospec(
            power.change, 'power_change_success')
        yield self.patch_rpc_methods()

        yield power.change.change_power_state(
            system_id, hostname, power_type, power_change, context)

        self.expectThat(
            perform_power_driver_change, MockCalledOnceWith(
                system_id, hostname, power_type, power_change, context))
        self.expectThat(
            perform_power_driver_query, MockCalledOnceWith(
                system_id, hostname, power_type, context))
        self.expectThat(
            power_change_success, MockCalledOnceWith(
                system_id, hostname, power_change))

    @inlineCallbacks
    def test__calls_power_driver_on_for_power_driver(self):
        system_id = factory.make_name('system_id')
        hostname = factory.make_name('hostname')
        power_type = random.choice(power.QUERY_POWER_TYPES)
        power_change = 'on'
        context = {
            factory.make_name('context-key'): factory.make_name('context-val')
        }
        self.patch(power, 'is_driver_available').return_value = True
        get_item = self.patch(PowerDriverRegistry, 'get_item')
        perform_power_driver_query = self.patch(
            power.query, 'perform_power_driver_query')
        perform_power_driver_query.return_value = succeed(power_change)
        self.patch(power.change, 'power_change_success')
        yield self.patch_rpc_methods()

        result = yield power.change.change_power_state(
            system_id, hostname, power_type, power_change, context)

        self.expectThat(get_item, MockCalledOnceWith(power_type))
        self.expectThat(
            perform_power_driver_query, MockCalledOnceWith(
                system_id, hostname, power_type, context))
        self.expectThat(
            power.change.power_change_success, MockCalledOnceWith(
                system_id, hostname, power_change))
        self.expectThat(result, Equals('on'))

    @inlineCallbacks
    def test__calls_power_driver_off_for_power_driver(self):
        system_id = factory.make_name('system_id')
        hostname = factory.make_name('hostname')
        power_type = random.choice(power.QUERY_POWER_TYPES)
        power_change = 'off'
        context = {
            factory.make_name('context-key'): factory.make_name('context-val')
        }
        self.patch(power, 'is_driver_available').return_value = True
        get_item = self.patch(PowerDriverRegistry, 'get_item')
        perform_power_driver_query = self.patch(
            power.query, 'perform_power_driver_query')
        perform_power_driver_query.return_value = succeed(power_change)
        self.patch(power.change, 'power_change_success')
        yield self.patch_rpc_methods()

        result = yield power.change.change_power_state(
            system_id, hostname, power_type, power_change, context)

        self.expectThat(get_item, MockCalledOnceWith(power_type))
        self.expectThat(
            perform_power_driver_query, MockCalledOnceWith(
                system_id, hostname, power_type, context))
        self.expectThat(
            power.change.power_change_success, MockCalledOnceWith(
                system_id, hostname, power_change))
        self.expectThat(result, Equals('off'))

    @inlineCallbacks
    def test__calls_power_driver_cycle_for_power_driver(self):
        system_id = factory.make_name('system_id')
        hostname = factory.make_name('hostname')
        power_type = random.choice(power.QUERY_POWER_TYPES)
        power_change = 'cycle'
        context = {
            factory.make_name('context-key'): factory.make_name('context-val')
        }
        self.patch(power, 'is_driver_available').return_value = True
        get_item = self.patch(PowerDriverRegistry, 'get_item')
        perform_power_driver_query = self.patch(
            power.query, 'perform_power_driver_query')
        perform_power_driver_query.return_value = succeed('on')
        self.patch(power.change, 'power_change_success')
        yield self.patch_rpc_methods()

        result = yield power.change.change_power_state(
            system_id, hostname, power_type, power_change, context)

        self.expectThat(get_item, MockCalledOnceWith(power_type))
        self.expectThat(
            perform_power_driver_query, MockCalledOnceWith(
                system_id, hostname, power_type, context))
        self.expectThat(
            power.change.power_change_success, MockCalledOnceWith(
                system_id, hostname, 'on'))
        self.expectThat(result, Equals('on'))

    @inlineCallbacks
    def test__marks_the_node_broken_if_exception_for_power_driver(self):
        system_id = factory.make_name('system_id')
        hostname = factory.make_name('hostname')
        power_type = random.choice(power.QUERY_POWER_TYPES)
        power_change = 'on'
        context = {
            factory.make_name('context-key'): factory.make_name('context-val'),
            'system_id': system_id
        }
        self.patch(power, 'is_driver_available').return_value = True
        exception = PowerError(factory.make_string())
        get_item = self.patch(PowerDriverRegistry, 'get_item')
        power_driver = get_item.return_value
        power_driver.on.return_value = fail(exception)

        markNodeBroken = yield self.patch_rpc_methods()

        with ExpectedException(PowerError):
            yield power.change.change_power_state(
                system_id, hostname, power_type, power_change, context)

        error_message = "Power on for the node failed: %s" % (
            get_driver_error_message(exception))
        self.expectThat(
            markNodeBroken, MockCalledOnceWith(
                ANY, system_id=system_id, error_description=error_message))


class TestMaybeChangePowerState(MAASTestCase):

    run_tests_with = MAASTwistedRunTest.make_factory(timeout=5)

    def setUp(self):
        super(TestMaybeChangePowerState, self).setUp()
        self.patch(power, 'power_action_registry', {})
        for power_driver in power_drivers_by_name.values():
            self.patch(
                power_driver, "detect_missing_packages").return_value = []
        self.useFixture(EventTypesAllRegistered())

    def patch_methods_using_rpc(self):
        pcs = self.patch_autospec(power.change, 'power_change_starting')
        pcs.return_value = always_succeed_with(None)
        cps = self.patch_autospec(power.change, 'change_power_state')
        cps.return_value = always_succeed_with(None)

    def test_always_returns_deferred(self):
        clock = Clock()
        power_type = random.choice(power.QUERY_POWER_TYPES)
        d = power.change.maybe_change_power_state(
            sentinel.system_id, sentinel.hostname, power_type,
            random.choice(("on", "off")), sentinel.context, clock=clock)
        self.assertThat(d, IsInstance(Deferred))

    @inlineCallbacks
    def test_adds_action_to_registry(self):
        self.patch_methods_using_rpc()

        system_id = factory.make_name('system_id')
        hostname = factory.make_name('hostname')
        power_type = random.choice(power.QUERY_POWER_TYPES)
        power_change = random.choice(['on', 'off', 'cycle'])
        context = {
            factory.make_name('context-key'): factory.make_name('context-val')
        }

        yield power.change.maybe_change_power_state(
            system_id, hostname, power_type, power_change, context)
        self.assertEqual(
            {system_id: (power_change, ANY)},
            power.power_action_registry)
        reactor.runUntilCurrent()  # Run all delayed calls.
        self.assertEqual({}, power.power_action_registry)

    @inlineCallbacks
    def test_checks_missing_packages(self):
        self.patch_methods_using_rpc()

        system_id = factory.make_name('system_id')
        hostname = factory.make_name('hostname')
        power_type = random.choice(power.QUERY_POWER_TYPES)
        power_change = random.choice(['on', 'off', 'cycle'])
        context = {
            factory.make_name('context-key'): factory.make_name('context-val')
        }
        power_driver = power_drivers_by_name.get(power_type)
        yield power.change.maybe_change_power_state(
            system_id, hostname, power_type, power_change, context)
        reactor.runUntilCurrent()  # Run all delayed calls.
        self.assertThat(
            power_driver.detect_missing_packages, MockCalledOnceWith())

    @inlineCallbacks
    def test_errors_when_missing_packages(self):
        self.patch_methods_using_rpc()

        system_id = factory.make_name('system_id')
        hostname = factory.make_name('hostname')
        power_type = random.choice(power.QUERY_POWER_TYPES)
        power_change = random.choice(['on', 'off', 'cycle'])
        context = {
            factory.make_name('context-key'): factory.make_name('context-val')
        }
        power_driver = power_drivers_by_name.get(power_type)
        power_driver.detect_missing_packages.return_value = ['gone']
        with ExpectedException(exceptions.PowerActionFail):
            yield power.change.maybe_change_power_state(
                system_id, hostname, power_type, power_change, context)
        self.assertThat(
            power_driver.detect_missing_packages, MockCalledOnceWith())

    @inlineCallbacks
    def test_errors_when_change_conflicts_with_in_progress_change(self):
        system_id = factory.make_name('system_id')
        hostname = factory.make_name('hostname')
        power_type = random.choice(power.QUERY_POWER_TYPES)
        power_changes = ['on', 'off']
        random.shuffle(power_changes)
        current_power_change, power_change = power_changes
        context = {
            factory.make_name('context-key'): factory.make_name('context-val')
        }
        power.power_action_registry[system_id] = (
            current_power_change, sentinel.d)
        with ExpectedException(exceptions.PowerActionAlreadyInProgress):
            yield power.change.maybe_change_power_state(
                system_id, hostname, power_type, power_change, context)

    @inlineCallbacks
    def test_does_nothing_when_change_matches_in_progress_change(self):
        system_id = factory.make_name('system_id')
        hostname = factory.make_name('hostname')
        power_type = random.choice(power.QUERY_POWER_TYPES)
        current_power_change = power_change = (
            random.choice(['on', 'off', 'cycle']))
        context = {
            factory.make_name('context-key'): factory.make_name('context-val')
        }
        power.power_action_registry[system_id] = (
            current_power_change, sentinel.d)
        yield power.change.maybe_change_power_state(
            system_id, hostname, power_type, power_change, context)
        self.assertThat(power.power_action_registry, Equals(
            {system_id: (power_change, sentinel.d)}))

    @inlineCallbacks
    def test_calls_change_power_state_later(self):
        self.patch_methods_using_rpc()

        system_id = factory.make_name('system_id')
        hostname = factory.make_name('hostname')
        power_type = random.choice(power.QUERY_POWER_TYPES)
        power_change = random.choice(['on', 'off', 'cycle'])
        context = {
            factory.make_name('context-key'): factory.make_name('context-val')
        }

        yield power.change.maybe_change_power_state(
            system_id, hostname, power_type, power_change, context)
        reactor.runUntilCurrent()  # Run all delayed calls.
        self.assertThat(
            power.change.change_power_state,
            MockCalledOnceWith(
                system_id, hostname, power_type, power_change, context,
                power.change.reactor))

    @inlineCallbacks
    def test_clears_lock_if_change_power_state_success(self):
        self.patch_methods_using_rpc()

        system_id = factory.make_name('system_id')
        hostname = factory.make_name('hostname')
        power_type = random.choice(power.QUERY_POWER_TYPES)
        power_change = random.choice(['on', 'off', 'cycle'])
        context = {
            factory.make_name('context-key'): factory.make_name('context-val')
        }

        yield power.change.maybe_change_power_state(
            system_id, hostname, power_type, power_change, context)
        reactor.runUntilCurrent()  # Run all delayed calls.
        self.assertNotIn(system_id, power.power_action_registry)

    @inlineCallbacks
    def test_clears_lock_if_change_power_state_fails(self):

        class TestException(Exception):
            pass

        pcs = self.patch_autospec(power.change, 'power_change_starting')
        pcs.return_value = fail(TestException('boom'))

        system_id = factory.make_name('system_id')
        hostname = factory.make_hostname()
        power_type = random.choice(power.QUERY_POWER_TYPES)
        power_change = random.choice(['on', 'off', 'cycle'])
        context = sentinel.context

        logger = self.useFixture(TwistedLoggerFixture())

        yield power.change.maybe_change_power_state(
            system_id, hostname, power_type, power_change, context)
        reactor.runUntilCurrent()  # Run all delayed calls.
        self.assertNotIn(system_id, power.power_action_registry)
        self.assertDocTestMatches(
            """\
            %s: Power %s failed.
            Traceback (most recent call last):
            ...
            %s.TestException: boom
            """ % (hostname, power_change, __name__),
            logger.dump())

    @inlineCallbacks
    def test_clears_lock_if_change_power_state_is_cancelled(self):
        # Patch in an unfired Deferred here. This will pause the call so that
        # we can grab the delayed call from the registry in time to cancel it.
        self.patch_autospec(power.change, 'change_power_state')
        power.change.change_power_state.return_value = Deferred()
        self.patch_autospec(power.change, 'power_change_failure')

        system_id = factory.make_name('system_id')
        hostname = factory.make_hostname()
        power_type = random.choice(power.QUERY_POWER_TYPES)
        power_change = random.choice(['on', 'off', 'cycle'])
        context = sentinel.context

        logger = self.useFixture(TwistedLoggerFixture())

        yield power.change.maybe_change_power_state(
            system_id, hostname, power_type, power_change, context)

        # Get the Deferred from the registry and cancel it.
        _, d = power.power_action_registry[system_id]
        d.cancel()
        yield d

        self.assertNotIn(system_id, power.power_action_registry)
        self.assertDocTestMatches(
            """\
            %s: Power could not be set to %s; timed out.
            """ % (hostname, power_change),
            logger.dump())
        self.assertThat(
            power.change.power_change_failure, MockCalledOnceWith(
                system_id, hostname, power_change, "Timed out"))

    @inlineCallbacks
    def test__calls_change_power_state_with_timeout(self):
        self.patch_methods_using_rpc()
        defer_with_timeout = self.patch(power.change, 'deferWithTimeout')

        system_id = factory.make_name('system_id')
        hostname = factory.make_name('hostname')
        power_type = random.choice(power.QUERY_POWER_TYPES)
        power_change = random.choice(['on', 'off', 'cycle'])
        context = {
            factory.make_name('context-key'): factory.make_name('context-val')
        }

        yield power.change.maybe_change_power_state(
            system_id, hostname, power_type, power_change, context)
        reactor.runUntilCurrent()  # Run all delayed calls.
        self.assertThat(
            defer_with_timeout, MockCalledOnceWith(
                power.change.CHANGE_POWER_STATE_TIMEOUT,
                power.change.change_power_state, system_id, hostname,
                power_type, power_change, context, power.change.reactor))
