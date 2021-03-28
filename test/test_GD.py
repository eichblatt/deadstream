import unittest
import tempfile

import GD


class TestGD(unittest.TestCase):

    def test_create_set(self):
        set = GD.GDSet()
        self.assertGreater(len(set.set_data), 0)

    def test_create_async_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            GD.GDArchive(directory, sync=False)

    def test_create_sync_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            # slow: initializes a new archive synchronously
            GD.GDArchive(directory, sync=True)


if __name__ == '__main__':
    unittest.main()
