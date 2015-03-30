import mock
import testtools

import volume_manager


class FakeServer(object):

    id = 'fake_serv_id'


class FakeVolume(object):

    id = 'fake_vol_id'
    attachments = [
        {
            'server_id': FakeServer.id,
            'device': 'fake_dev_path',
        },
    ]


class VolumeManagerTestCase(testtools.TestCase):

    RESOURCE_MAP = {
        'volumes': FakeVolume,
        'servers': FakeServer,
    }

    def setUp(self):
        super(VolumeManagerTestCase, self).setUp()
        nova_client_p = mock.patch.object(volume_manager.nova_client, 'Client')
        self.nova_client = nova_client_p.start()
        self.addCleanup(nova_client_p.stop)
        self.manager = volume_manager.VolumeManager(
            'fake_user', 'fake_password', 'fake_tenant', 'fake_auth_url')

    @mock.patch.object(volume_manager.os, 'system')
    def test_format_volume(self, mock_system):
        mock_system.return_value = 0
        find_fip_p = mock.patch.object(self.manager, '_find_floating_ip')
        find_resource_p = mock.patch.object(self.manager, '_find_resource')
        with find_resource_p as find_resource_mock:
            find_resource_mock.side_effect = (
                lambda resource, id: self.RESOURCE_MAP[resource]
            )
            with find_fip_p as find_fip_mock:
                find_fip_mock.return_value = 'fake_ip'
                self.manager.format_volume(
                    FakeVolume.id,
                    FakeServer.id,
                    'fake_user',
                    'fake_path'
                )
        find_resource_mock.assert_has_calls(
            [
                mock.call('servers', FakeServer.id),
                mock.call('volumes', FakeVolume.id),
            ]
        )
        find_fip_mock.assert_called_once()
        mock_system.assert_called_once()
