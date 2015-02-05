# Copyright 2014 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test for :py:mod:`maasserver.clusterrpc.power`."""

from __future__ import (
    absolute_import,
    print_function,
    unicode_literals,
    )

str = None

__metaclass__ = type
__all__ = []

from maasserver.clusterrpc.power import (
    power_off_nodes,
    power_on_nodes,
    )
from maasserver.rpc.testing.fixtures import MockRegionToClusterRPCFixture
from maasserver.testing.eventloop import (
    RegionEventLoopFixture,
    RunningEventLoopFixture,
    )
from maasserver.testing.factory import factory
from maasserver.testing.testcase import MAASServerTestCase
from maastesting.matchers import (
    MockCalledOnceWith,
    MockCallsMatch,
    )
from mock import (
    ANY,
    call,
    )
from provisioningserver.rpc.cluster import (
    PowerOff,
    PowerOn,
    )
from provisioningserver.utils.twisted import reactor_sync
from testtools.deferredruntest import extract_result
from testtools.matchers import HasLength


class TestPowerNodes(MAASServerTestCase):
    """Tests for `power_on_nodes` and `power_off_nodes`."""

    scenarios = (
        ("PowerOn", {"power_func": power_on_nodes, "command": PowerOn}),
        ("PowerOff", {"power_func": power_off_nodes, "command": PowerOff}),
    )

    def test_does_nothing_when_there_are_no_nodes(self):
        self.power_func([])

    def prepare_rpc(self):
        self.useFixture(RegionEventLoopFixture("rpc"))
        self.useFixture(RunningEventLoopFixture())
        return self.useFixture(MockRegionToClusterRPCFixture())

    def test__powers_single_node(self):
        rpc_fixture = self.prepare_rpc()

        node = factory.make_Node()
        cluster, io = rpc_fixture.makeCluster(node.nodegroup, self.command)

        nodes_for_call = [
            (node.system_id, node.hostname, node.nodegroup.uuid,
             node.get_effective_power_info()),
        ]

        # We're not doing any IO via the reactor so we sync with it only so
        # that this becomes the IO thread, making @asynchronous transparent.
        with reactor_sync():
            deferreds = self.power_func(nodes_for_call)

        self.assertThat(deferreds, HasLength(1))
        io.flush()
        [d] = deferreds.viewvalues()
        self.assertEquals({}, extract_result(d))

        power_info = node.get_effective_power_info()
        self.assertThat(
            getattr(cluster, self.command.commandName),
            MockCalledOnceWith(
                ANY, system_id=node.system_id, hostname=node.hostname,
                power_type=power_info.power_type,
                context=power_info.power_parameters,
            ))

    def test__powers_multiple_nodes(self):
        nodegroup = factory.make_NodeGroup()
        nodes = [factory.make_Node(nodegroup=nodegroup) for _ in xrange(3)]
        nodes_for_call = list(  # Use list() to avoid namespace leaks.
            (node.system_id, node.hostname, node.nodegroup.uuid,
             node.get_effective_power_info())
            for node in nodes
        )

        rpc_fixture = self.prepare_rpc()
        cluster, io = rpc_fixture.makeCluster(nodegroup, self.command)

        # power_*_nodes() return a mapping of system IDs -> Deferred, which
        # crochet passes through unaltered (if it was a DeferredList it would
        # be waited on).
        deferreds = self.power_func(nodes_for_call)

        io.flush()  # Move IO until everything's done.

        # All the Deferreds have fired with empty dicts.
        self.assertEqual(
            [extract_result(d) for d in deferreds.viewvalues()],
            [{} for _ in nodes])

        # Three calls are made to the same cluster, requesting
        # PowerOn/PowerOff for each node.
        expected_calls = (
            call(
                ANY, system_id=system_id, hostname=hostname,
                power_type=power_info.power_type,
                context=power_info.power_parameters)
            for system_id, hostname, cluster_uuid, power_info in nodes_for_call
        )
        self.assertThat(
            getattr(cluster, self.command.commandName),
            MockCallsMatch(*expected_calls))

    def test__powers_multiple_nodes_in_different_clusters(self):
        rpc_fixture = self.prepare_rpc()

        nodes = {}
        for _ in xrange(3):
            node = factory.make_Node()
            cluster, io = rpc_fixture.makeCluster(node.nodegroup, self.command)
            nodes[node] = cluster, io

        nodes_for_call = list(  # Use list() to avoid namespace leaks.
            (node.system_id, node.hostname, node.nodegroup.uuid,
             node.get_effective_power_info())
            for node in nodes
        )

        # power_*_nodes() return a mapping of system IDs -> Deferred, which
        # crochet passes through unaltered (if it was a DeferredList it would
        # be waited on).
        deferreds = self.power_func(nodes_for_call)

        # One call is made to each of the three clusters, requesting
        # PowerOn/PowerOff for each node.
        for node, (cluster, io) in nodes.viewitems():
            d = deferreds[node.system_id]
            io.flush()  # Move IO until everything's done.
            self.assertEquals({}, extract_result(d))
            power_info = node.get_effective_power_info()
            self.assertThat(
                getattr(cluster, self.command.commandName),
                MockCalledOnceWith(
                    ANY, system_id=node.system_id, hostname=node.hostname,
                    power_type=power_info.power_type,
                    context=power_info.power_parameters,
                ))