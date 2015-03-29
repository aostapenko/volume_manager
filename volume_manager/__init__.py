import os

from novaclient import utils as novaclient_utils
from novaclient.v2 import client as nova_client


class VolumeManager(object):

    def __init__(self, username, password, tenant_name, auth_url):
        super(VolumeManager, self).__init__()
        self.client = nova_client.Client(
            username, password, tenant_name, auth_url)
        self.client.authenticate()

    def _find_resource(self, resource, name_or_id):
        return novaclient_utils.find_resource(
            getattr(self.client, resource), name_or_id)

    def get_volume(self, volume_id):
        """Creates volume."""

        return self.client.volumes.get(id)

    def create_volume(self, size, name=None, description=None):
        """Creates volume."""

        self.client.volumes.create(
            size, display_name=name, display_description=description
        )

    def delete_volume(self, volume_name_or_id):
        """Deletes volume by its name or id."""

        return self._find_resource('volumes', volume_name_or_id).delete()

    def lookup_by_name(self, volume_name):
        """Returns a list of volumes that have appropriate name."""

        return self.client.volumes.findall(display_name=volume_name)

    def attach_volume(self, server_name_or_id, volume_name_or_id,
                      mountpoint):
        """Attaches volume to instance."""

        server = self._find_resource('servers', server_name_or_id)
        volume = self._find_resource('volumes', volume_name_or_id)
        return self.client.volumes.create_server_volume(
            server.id, volume.id, mountpoint)

    def detach_volume(self, server_name_or_id, volume_name_or_id):
        """Detaches volume."""

        server = self._find_resource('servers', server_name_or_id)
        volume = self._find_resource('volumes', volume_name_or_id)
        return self.client.volumes.delete_server_volume(
            server.id, volume.id)

    def format_volume(self, server_name_or_id, volume_name_or_id,
                      user, path_to_key, floating_ip=None, filesystem='ext4'):
        """Formats volume attached to given instance.

        Server must be accessible via floating ip.
        """

        server = self._find_resource('servers', server_name_or_id)
        volume = self._find_resource('volumes', volume_name_or_id)
        attachments = volume.attachments
        if not attachments or attachments[0]['server_id'] != server.id:
            msg = "Volume {0} is not attached to instance {1}"
            raise Exception(msg.format(volume.id, server.id))
        if not floating_ip:
            floating_ip = self._find_floating_ip(server)
            if floating_ip is None:
                msg = "Can not perform an operation. No access to server."
                raise Exception(msg)
        device = attachments[0]['device']
        format_cmd = 'sudo mkfs.{0} {1}'.format(filesystem, device)
        cmd = 'ssh -i {0} {1}@{2} {3}'.format(
            path_to_key, user, floating_ip, format_cmd
        )
        os.system(cmd)

    @staticmethod
    def _find_floating_ip(server):
        for net_name, addresses in server.addresses.iteritems():
            for addr in addresses:
                if addr['OS-EXT-IPS:type'] == 'floating':
                    return addr['addr']
