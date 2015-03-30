import os

from novaclient import utils as novaclient_utils
from novaclient.v2 import client as nova_client


def _ssh_exec(path_to_key, user, ip, cmd):
    opts = '-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'
    cmd = 'ssh {0} -i {1} {2}@{3} {4}'.format(
        opts, path_to_key, user, ip, cmd
    )
    return os.system(cmd)


def _translate_volume(vol):
    """Maps keys for volumes summary view."""

    d = {}
    d['id'] = vol.id
    d['status'] = vol.status
    d['size'] = vol.size
    d['created_at'] = vol.created_at
    d['attach_time'] = ""
    d['mountpoint'] = ""
    if vol.attachments:
        att = vol.attachments[0]
        d['attach_status'] = 'attached'
        d['server_id'] = att['server_id']
        d['mountpoint'] = att['device']
    else:
        d['attach_status'] = 'detached'
    d['name'] = vol.display_name
    d['description'] = vol.display_description
    return d


class VolumeManager(object):
    """Volume manager for Cinder volumes manipulating.

    :param string username: Username for authentication.
    :param string password: Password for authentication.
    :param string tenant_name: Tenant name.
    :param string auth_url: Keystone service endpoint for authorization.

    Example::

        >>> import volume_manager
        >>> vol_mgr = volume_manager.VolumeManager(
        >>>     username=USER,
        >>>     password=PASS,
        >>>     tenant_name=TENANT_NAME,
        >>>     auth_url=KEYSTONE_URL
        >>> )

        >>> volume = vol_mgr.get_volume(VOLUME_NAME_OR_ID)
    ...
    """

    def __init__(self, username, password, tenant_name, auth_url):
        self.client = nova_client.Client(
            username, password, tenant_name, auth_url)
        self.client.authenticate()

    def _find_resource(self, resource, name_or_id):
        return novaclient_utils.find_resource(
            getattr(self.client, resource), name_or_id)

    def get_volume(self, volume_id):
        """Gets volume by id.

        :param string volume_id: UUID of Cinder Volume.

        :returns: Dict that contains volume information.

        :raises: NotFound
        """

        return _translate_volume(self.client.volumes.get(volume_id))

    def create_volume(self, size, name=None, description=None):
        """Creates volume.

        :param integer size: Size of volume in GB.
        :param string name: Name of volume.
        :param string description: Description of volume.

        :returns: Dict that contains volume information.
        """

        return _translate_volume(self.client.volumes.create(
            size, display_name=name, display_description=description
        ))

    def delete_volume(self, volume_name_or_id):
        """Deletes volume by its name or id.

        :param string volume_name_or_id: UUID or name of Cinder Volume.

        :returns: None

        :raises: NotFound, NoUniqueMatch
        """

        return self._find_resource('volumes', volume_name_or_id).delete()

    def lookup_by_name(self, volume_name):
        """Returns a list of volumes that have appropriate name.

        :param string volume_name: Name of Cinder Volume.

        :returns: List of dicts that contain volumes information.
        """

        return [_translate_volume(volume) for volume in
                self.client.volumes.findall(display_name=volume_name)]

    def attach_volume(self, volume_name_or_id, server_name_or_id):
        """Attaches volume to instance.

        :param string volume_name_or_id: Name or UUID of Cinder Volume.
        :param string server_name_or_id: Name or UUID of Nova Instance.

        :returns: Dict that contains volume information.

        :raises: NotFound, NoUniqueMatch, BadRequest
        """

        server = self._find_resource('servers', server_name_or_id)
        volume = self._find_resource('volumes', volume_name_or_id)
        return _translate_volume(self.client.volumes.create_server_volume(
            server.id, volume.id, None))

    def detach_volume(self, volume_name_or_id, server_name_or_id):
        """Detaches volume.

        :param string volume_name_or_id: Name or UUID of Cinder Volume.
        :param string server_name_or_id: Name or UUID of Nova Instance.

        :returns: Dict that contains volume information.

        :raises: NotFound, NoUniqueMatch, BadRequest
        """

        server = self._find_resource('servers', server_name_or_id)
        volume = self._find_resource('volumes', volume_name_or_id)
        return self.client.volumes.delete_server_volume(
            server.id, volume.id)

    def format_volume(self, volume_name_or_id, server_name_or_id,
                      user, path_to_key, floating_ip=None, filesystem='ext4'):
        """Formats volume attached to given instance.

        Server must be accessible via floating ip.

        :param string volume_name_or_id: Name or UUID of Cinder Volume.
        :param string server_name_or_id: Name or UUID of Nova Instance.
        :param string user: Name of server user.
        :param string path_to_key: Path to key for ssh access.
        :param string floating_ip: Server floating_ip.
        :param string filesystem: Filesystem to format volume.

        :returns: None

        :raises: NotFound, NoUniqueMatch, BadRequest, Exception
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
        if _ssh_exec(path_to_key, user, floating_ip, format_cmd):
            raise Exception("Failed to format device.")

    @staticmethod
    def _find_floating_ip(server):
        for net_name, addresses in server.addresses.iteritems():
            for addr in addresses:
                if addr['OS-EXT-IPS:type'] == 'floating':
                    return addr['addr']
