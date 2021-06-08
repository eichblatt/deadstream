import unittest
import tempfile

from timemachine import GD


class TestGD(unittest.TestCase):

    def test_create_set(self):
        set = GD.GDSet()
        self.assertGreater(len(set.set_data), 0)

    def test_create_async_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            GD.GDArchive(directory, sync=False)

    """
    def test_create_sync_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            # slow: initializes a new archive synchronously
            GD.GDArchive(directory, sync=True)
    """

    def _test_tape_downloader(self, downloader):
        tapes = downloader.get_tapes([1970])
        frac_id = len([x for x in tapes if "identifier" in x]) / len(tapes)
        self.assertGreaterEqual(len(tapes), 200, msg="1970 has many tapes")
        self.assertEquals(frac_id, 1.0, msg="All tapes have an identifier")

    """
    def test_sync_tape_downloader(self):
       downloader = GD.TapeDownloader()
        self._test_tape_downloader(downloader)
    """

    def test_async_tape_downloader(self):
        downloader = GD.AsyncTapeDownloader()
        self._test_tape_downloader(downloader)


if __name__ == '__main__':
    unittest.main()
