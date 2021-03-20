import unittest
import tempfile

import GD

class TestGD(unittest.TestCase):

    def test_create_set(self):
        set = GD.GDSet()
        self.assertGreater(len(set.set_data), 0)
    
    def test_create_archive(self):
        # This unit test is slow because it initializes a new archive
        with tempfile.TemporaryDirectory() as directory:
            archive = GD.GDArchive(directory)

if __name__ == '__main__':
    unittest.main()