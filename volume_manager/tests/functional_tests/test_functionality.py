import time

from novaclient import exceptions
import testtools
import volume_manager


VOLUME_STATUS_CREATING = 'creating'
VOLUME_STATUS_DELETING = 'deleting'
VOLUME_STATUS_ACTIVE = 'available'
VOLUME_STATUS_ATTACHING = 'attaching'
VOLUME_STATUS_ATTACHED = 'in-use'
VOLUME_STATUS_DETACHING = 'detaching'


class VolumeManagerTestCase(testtools.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.manager = volume_manager.VolumeManager(
            'admin', '1', 'demo', 'http://192.168.122.100:5000/v2.0'
        )

    @classmethod
    def _wait_for_status(cls, volume_id, status, timeout=120, interval=1):
        def check():
            volume = cls.manager.get_volume(volume_id)
            return volume.status == status
        return call_until_true(check, timeout, interval)

    @classmethod
    def _wait_for_deleted(cls, volume_id, timeout=120, interval=1):
        def check():
            try:
                cls.manager.get_volume(volume_id)
            except exceptions.NotFound:
                return True
        return call_until_true(check, timeout, interval)

    @classmethod
    def _delete_volume(cls, volume_id):
        cls.manager.delete_volume(volume_id)
        if cls._wait_for_deleted(volume_id):
            return True
        else:
            raise Exception("Volume deleting timeout.")

    @classmethod
    def _detach_volume(cls, volume_id, server_id):
        cls.manager.detach_volume(volume_id, server_id)
        if cls._wait_for_status(volume_id, VOLUME_STATUS_ACTIVE):
            return True
        else:
            raise Exception("Volume detaching timeout.")

    def test_create_volume(self):
        name = 'test_volume'
        description = 'This is test volume'
        size = 1
        volume = self.manager.create_volume(size, name, description)
        self.addCleanup(self._delete_volume, volume.id)
        self.assertEqual(name, volume.display_name)
        self.assertEqual(description, volume.display_description)
        self.assertEqual(size, volume.size)
        self.assertEqual(VOLUME_STATUS_CREATING, volume.status)
        self.assertTrue(self._wait_for_status(volume.id, VOLUME_STATUS_ACTIVE))

    def test_delete_volume(self):
        volume = self.manager.create_volume(1)
        self._wait_for_status(volume.id, VOLUME_STATUS_ACTIVE)
        self.manager.delete_volume(volume.id)
        volume = self.manager.get_volume(volume.id)
        self.assertEqual(VOLUME_STATUS_DELETING, volume.status)
        self.assertTrue(self._wait_for_deleted(volume.id))

    def test_attach_volume(self):
        mountpoint = '/dev/vde'
        volume = self.manager.create_volume(1)
        self.addCleanup(self._delete_volume, volume.id)
        self._wait_for_status(volume.id, VOLUME_STATUS_ACTIVE)
        volume = self.manager.attach_volume(
            volume.id, 'test_instance', mountpoint)
        self.addCleanup(self._detach_volume, volume.id, 'test_instance')
        self.assertEqual(VOLUME_STATUS_ATTACHING, volume.status)
        self.assertTrue(
            self._wait_for_status(volume.id, VOLUME_STATUS_ATTACHED)
        )

    def test_detach_volume(self):
        mountpoint = '/dev/vde'
        volume = self.manager.create_volume(1)
        self.addCleanup(self._delete_volume, volume.id)
        self._wait_for_status(volume.id, VOLUME_STATUS_ACTIVE)
        volume = self.manager.attach_volume(
            volume.id, 'test_instance', mountpoint)
        self._wait_for_status(volume.id, VOLUME_STATUS_ATTACHED)
        self.manager.detach_volume(volume.id, 'test_instance')
        volume = self.manager.get_volume(volume.id)
        self.assertEqual(VOLUME_STATUS_DETACHING, volume.status)
        self.assertTrue(
            self._wait_for_status(volume.id, VOLUME_STATUS_ACTIVE)
        )


def call_until_true(func, duration, sleep_for):

    now = time.time()
    timeout = now + duration
    while now < timeout:
        if func():
            return True
        time.sleep(sleep_for)
        now = time.time()
    return False
