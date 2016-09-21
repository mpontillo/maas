# Copyright 2016 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""The Discovery handler for the WebSocket connection."""

__all__ = [
    "DiscoveryHandler",
    ]

from maasserver.models import Discovery
from maasserver.websockets.base import dehydrate_datetime
from maasserver.websockets.handlers.viewmodel import ViewModelHandler
from provisioningserver.logger import get_maas_logger


maaslog = get_maas_logger("websockets.discovery")


class DiscoveryHandler(ViewModelHandler):

    class Meta:
        queryset = (
            Discovery.objects.by_unknown_ip_and_mac()
        )
        # This batch key isn't guaranteed to be stable, since newly-discovered
        # items can come in as the new first-items in the query. But that's why
        # we're also going to poll. But using row_number() seems to be a good
        # compromise for now.
        batch_key = 'first_seen'
        pk = 'discovery_id'
        allowed_methods = [
            'list',
            'get',
        ]

    def dehydrate(self, obj, data, for_list=False):
        """Add extra fields to `data`."""
        data["mac_organization"] = obj.mac_organization
        return data

    def dehydrate_last_seen(self, datetime):
        return dehydrate_datetime(datetime)

    def dehydrate_first_seen(self, datetime):
        return dehydrate_datetime(datetime)