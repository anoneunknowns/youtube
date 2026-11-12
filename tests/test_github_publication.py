import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location('publication', Path(__file__).resolve().parents[1] / 'tools/verify_github_publication.py')
publication = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publication)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = sorted([publication.PROFILE, publication.RECEIPT, 'assets/current-v001.png'])
        self.write('assets/current-v001.png', b'adopted artwork')
        self.freeze()

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def freeze(self):
        self.write(publication.PROFILE, json.dumps({'schema_version': 1,
                   'scope': 'current-only-nonvideo', 'files': self.paths}).encode())
        entries = []
        for name in self.paths:
            if name != publication.RECEIPT:
                data = (self.root / name).read_bytes()
                entries.append({'path': name, 'bytes': len(data),
                                'sha256': publication.hashlib.sha256(data).hexdigest()})
        self.write(publication.RECEIPT, json.dumps({'files': entries}).encode())

    def test_selected_original_is_verified_and_corruption_is_rejected(self):
        self.write('assets/unused-v999.png', b'local unselected candidate')
        self.assertEqual(publication.verify(self.root)['files'], 3)
        self.write('assets/current-v001.png', b'changed artwork')
        with self.assertRaisesRegex(ValueError, 'differs from its frozen receipt'):
            publication.verify(self.root)

    def test_video_and_lfs_pointer_are_rejected(self):
        self.write('assets/current-v001.png', b'version https://git-lfs.github.com/spec/v1\noid sha256:fixture\n')
        self.freeze()
        with self.assertRaisesRegex(ValueError, 'Fetch the LFS file content'):
            publication.verify(self.root)
        self.write('assets/current-v001.png', b'adopted artwork')
        self.paths = sorted(self.paths + ['output/history.MP4'])
        self.write('output/history.MP4', b'local movie')
        self.freeze()
        with self.assertRaisesRegex(ValueError, 'Video file is outside'):
            publication.verify(self.root)

    @unittest.skipUnless(shutil.which('git'), 'Git required')
    def test_git_index_rejects_an_added_obsolete_file(self):
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True)
        subprocess.run(['git', 'add', '.'], cwd=self.root, check=True)
        self.assertTrue(publication.verify(self.root, check_git=True)['git_index_checked'])
        self.write('assets/unused-v999.png', b'old revision')
        subprocess.run(['git', 'add', '.'], cwd=self.root, check=True)
        with self.assertRaisesRegex(ValueError, 'Git index does not match'):
            publication.verify(self.root, check_git=True)


if __name__ == '__main__':
    unittest.main()
