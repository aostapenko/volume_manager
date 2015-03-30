import os
import time

from novaclient import exceptions
from oslo_config import cfg
import testtools

import volume_manager


config_file = os.path.join(os.path.dirname(__file__), 'test.conf')
cfg.CONF([], project='volume-manager-tests',
         default_config_files=[config_file])

CONF = cfg.CONF

identity_test_opts = [
    cfg.StrOpt('test_tenant',
               required=True,
               help='Tenant name for testing.'),
    cfg.StrOpt('test_user',
               required=True,
               help='Username that have privileges in test_tenant'),
    cfg.StrOpt('password',
               required=True,
               help='Password for test_user.'),
    cfg.StrOpt('auth_url',
               required=True,
               help='Keystone url'),
]


functional_test_opts = [
    cfg.StrOpt('test_instance',
               required=True,
               help='Prepared instance for testing.'),
    cfg.StrOpt('path_to_key',
               required=True,
               help='Path to private key to access to test instance.'),
    cfg.StrOpt('instance_user',
               required=True,
               help='Username in test instance'),
]


functional_tests = cfg.OptGroup(name='functional_tests',
                                title='Functional tests group')

CONF.register_group(functional_tests)
CONF.register_opts(identity_test_opts, group=functional_tests)
CONF.register_opts(functional_test_opts, group=functional_tests)


VOLUME_STATUS_CREATING = 'creating'
VOLUME_STATUS_DELETING = 'deleting'
VOLUME_STATUS_ACTIVE = 'available'
VOLUME_STATUS_ATTACHING = 'attaching'
VOLUME_STATUS_ATTACHED = 'in-use'
VOLUME_STATUS_DETACHING = 'detaching'
VOLUME_STATUS_ERROR = 'error'
VOLUME_STATUS_ERROR_DELETING = 'error_deleting'


class BaseVolumeManagerTestCase(testtools.TestCase):

    @classmethod
    def setUpClass(cls):
        super(BaseVolumeManagerTestCase, cls).setUpClass()
        cls.cfg = CONF.functional_tests
        cls.manager = volume_manager.VolumeManager(
            cls.cfg.test_user,
            cls.cfg.password,
            cls.cfg.test_tenant,
            cls.cfg.auth_url
        )

    @classmethod
    def _wait_for_status(cls, volume_id, status, timeout=120, interval=1):
        def check():
            volume = cls.manager.get_volume(volume_id)
            if volume['status'] == VOLUME_STATUS_ERROR:
                raise Exception("Volume status became error while waiting "
                                "for '{0}' status.".format(status))
            return volume['status'] == status
        return call_until_true(check, timeout, interval)

    @classmethod
    def _wait_for_deleted(cls, volume_id, timeout=120, interval=1):
        def check():
            try:
                volume = cls.manager.get_volume(volume_id)
                if volume['status'] == VOLUME_STATUS_ERROR_DELETING:
                    raise Exception("Error occured while deleting volume.")
            except exceptions.NotFound:
                return True
        return call_until_true(check, timeout, interval)

    @classmethod
    def _delete_volume(cls, volume_id):
        cls.manager.delete_volume(volume_id)
        if cls._wait_for_deleted(volume_id):
            return True
        else:
            raise Exception("Volume delete timeout.")

    @classmethod
    def _detach_volume(cls, volume_id, server_id):
        cls.manager.detach_volume(volume_id, server_id)
        if cls._wait_for_status(volume_id, VOLUME_STATUS_ACTIVE):
            return True
        else:
            raise Exception("Volume detach timeout.")

    def _create_volume(self, *args, **kwargs):
        cleanup = kwargs.pop('cleanup', True)
        volume = self.manager.create_volume(*args, **kwargs)
        if cleanup:
            self.addCleanup(self._delete_volume, volume['id'])
        if self._wait_for_status(volume['id'], VOLUME_STATUS_ACTIVE):
            volume = self.manager.get_volume(volume['id'])
            return volume
        else:
            raise Exception("Volume create timeout.")

    def _attach_volume(self, volume_id, server_id, cleanup=True):
        volume = self.manager.attach_volume(volume_id, server_id)
        if self._wait_for_status(volume['id'], VOLUME_STATUS_ATTACHED):
            if cleanup:
                self.addCleanup(self._detach_volume, volume_id,
                                server_id)
            volume = self.manager.get_volume(volume['id'])
            return volume
        else:
            raise Exception("Volume attach timeout.")


class VolumeManagerTestCase(BaseVolumeManagerTestCase):

    def test_create_volume(self):
        name = 'test_volume'
        description = 'This is test volume'
        size = 1
        volume = self.manager.create_volume(size, name, description)
        self.addCleanup(self._delete_volume, volume['id'])
        self.assertEqual(name, volume['name'])
        self.assertEqual(description, volume['description'])
        self.assertEqual(size, volume['size'])
        self.assertEqual(VOLUME_STATUS_CREATING, volume['status'])
        self.assertTrue(self._wait_for_status(volume['id'],
                                              VOLUME_STATUS_ACTIVE))

    def test_delete_volume(self):
        volume = self._create_volume(1)
        self._cleanups.pop()
        self.manager.delete_volume(volume['id'])
        volume = self.manager.get_volume(volume['id'])
        self.assertEqual(VOLUME_STATUS_DELETING, volume['status'])
        self.assertTrue(self._wait_for_deleted(volume['id']))

    def test_attach_volume(self):
        volume = self._create_volume(1)
        volume = self.manager.attach_volume(
            volume['id'], self.cfg.test_instance)
        self.addCleanup(
            self._detach_volume, volume['id'], self.cfg.test_instance)
        self.assertEqual(VOLUME_STATUS_ATTACHING, volume['status'])
        self.assertTrue(
            self._wait_for_status(volume['id'], VOLUME_STATUS_ATTACHED)
        )

    def test_detach_volume(self):
        volume = self._create_volume(1)
        volume = self._attach_volume(volume['id'], self.cfg.test_instance,
                                     cleanup=False)
        self.manager.detach_volume(volume['id'], self.cfg.test_instance)
        volume = self.manager.get_volume(volume['id'])
        self.assertEqual(VOLUME_STATUS_DETACHING, volume['status'])
        self.assertTrue(
            self._wait_for_status(volume['id'], VOLUME_STATUS_ACTIVE)
        )

    def test_format_volume(self):
        volume = self._create_volume(1)
        volume = self._attach_volume(volume['id'], self.cfg.test_instance)
        result = self.manager.format_volume(
            volume['id'],
            self.cfg.test_instance,
            self.cfg.instance_user,
            self.cfg.path_to_key
        )
        self.assertIsNone(result)


def call_until_true(func, duration, sleep_for):

    now = time.time()
    timeout = now + duration
    while now < timeout:
        if func():
            return True
        time.sleep(sleep_for)
        now = time.time()
    return False
