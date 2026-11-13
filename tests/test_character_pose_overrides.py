"""A reviewed anatomy fix replaces two app poses while retaining all other choices."""
from copy import deepcopy
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

from tests import test_character_adoptions as fixtures
from tools import character_library as library
from tools import unified_asset_library as unified


class CharacterPoseOverrideTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CharacterAdoptionTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.fixture.configure()
        self.names = ['neutral', *[f'pose_{n:02d}' for n in range(24)],
                      'pond_preload_left', 'pond_preload_right']
        self.base = self.registration('base-app', self.names)
        self.fix = self.registration('anatomy-fix', self.names[-2:], fix=True)
        self.evidence = 'assets/library/characters/bear-beret/generation-batches/anatomy-fix/review.json'
        self.fixture.write(self.evidence, {'scope': 'Two independently redrawn anatomy fixes', 'status': 'pass'})
        self.fixture.write(library.SUPPLEMENT, {'schema_version': 1,
            'status': 'stocked-and-assistant-reviewed',
            'review_evidence': [{'path': self.fixture.evidence, 'sha256': self.fixture.sha(self.fixture.evidence)}],
            'items': [{'id': 'bear-beret', 'neutral_reference': {
                key: self.fixture.new[key] for key in ('path', 'sha256')}, 'pose_sets': [{
                    'namespace': 'app', 'registration': self.base,
                    'registration_sha256': self.fixture.sha(self.base)}]}]})
        self.before = library.build_index(self.root)
        selected = self.before['characters'][0]['pose_sets'][0]
        self.override = {'namespace': 'app', 'base_registration': self.base,
            'base_registration_sha256': self.fixture.sha(self.base), 'registration': self.fix,
            'registration_sha256': self.fixture.sha(self.fix), 'replacements': {
                name: {key: selected['poses'][name][key] for key in ('path', 'sha256')}
                for name in self.names[-2:]}}
        for target, value in [('SCOPES', ['assets/library/characters', str(Path(library.SUPPLEMENT).parent)]),
                              ('EXTRAS', [library.MANAGEMENT, library.INDEX, library.STOCK, library.MOTIONS,
                                          library.STYLE, library.EYECATCHES])]:
            scope = patch.object(library, target, value)
            scope.start()
            self.addCleanup(scope.stop)

    def registration(self, batch, names, fix=False):
        prefix = f'assets/library/characters/bear-beret/generation-batches/{batch}/'
        frames, sheets = [], []
        for n, name in enumerate(names):
            neutral = self.fixture.new
            path = prefix+name+'.png'
            if name == 'neutral':
                path = neutral['path']
            else:
                image = Image.new('RGBA', tuple(neutral['source_size_px']))
                ImageDraw.Draw(image).rectangle((10, 8, 33, 51), fill=('blue' if n % 2 else 'green') if fix else 'orange')
                dest = self.root/path
                dest.parent.mkdir(parents=True, exist_ok=True)
                image.save(dest)
            checksum = self.fixture.sha(path)
            sheets.append({'id': name, 'source_sheet': path, 'source_sheet_sha256': checksum,
                           'reference_height_px': neutral['reference_height_px']})
            frames.append({'id': name, 'path': path, 'sha256': checksum,
                'size_px': neutral['source_size_px'], 'sheet_id': name, 'source_sheet': path,
                'source_sheet_sha256': checksum, 'crop_from_sheet_xyxy': [0, 0, *neutral['source_size_px']],
                'body_bbox_px': neutral['body_bbox_px'], 'anchor_px': neutral['anchor_px'],
                'tail_bbox_px': None, 'reference_height_px': neutral['reference_height_px']})
        relative = prefix+'registration.json'
        self.fixture.write(relative, {'schema_version': 1, 'character_id': 'bear-beret',
            'canonical_neutral': {key: self.fixture.new[key] for key in ('path', 'sha256')},
            'sheets': sheets, 'frames': frames,
            'clips': {} if fix else {'preload': ['neutral', self.names[-2], 'pose_10', self.names[-1], 'neutral']}})
        return relative

    def configure(self, override=None):
        entry = deepcopy(self.fixture.entry)
        entry['pose_set_overrides'] = [self.override if override is None else override]
        entry['selection_evidence'].append({'path': self.evidence, 'sha256': self.fixture.sha(self.evidence)})
        self.fixture.configure(entry)

    def test_two_pose_fix_preserves_other_twenty_five_clips_neutral_and_history(self):
        originals = {p.relative_to(self.root).as_posix(): p.read_bytes()
                     for p in self.root.rglob('*') if p.is_file()}
        self.configure()
        after = library.build_index(self.root)
        old, new = self.before['characters'][0], after['characters'][0]
        self.assertEqual(self.before['characters'][1], after['characters'][1])
        for field in ('neutral', 'eyecatch_key_poses', 'eyecatch_collection'):
            self.assertEqual(old[field], new[field])
        old_set, new_set = old['pose_sets'][0], new['pose_sets'][0]
        for field in old_set:
            if field != 'poses':
                self.assertEqual(old_set[field], new_set[field])
        self.assertEqual(len(new_set['poses']), 27)
        for name in self.names[:-2]:
            self.assertEqual(old_set['poses'][name], new_set['poses'][name])
        for name in self.names[-2:]:
            self.assertNotEqual(old_set['poses'][name]['sha256'], new_set['poses'][name]['sha256'])
        for relative, content in originals.items():
            if relative != library.ADOPTIONS:
                self.assertEqual((self.root/relative).read_bytes(), content)
        self.assertEqual(new['adoption_selection']['selection_evidence'][:-1],
                         old['adoption_selection']['selection_evidence'])

    def test_base_and_previous_selections_are_guarded(self):
        changes = [lambda x: x.update(base_registration_sha256='0'*64),
                   lambda x: x['replacements']['pond_preload_left'].update(sha256='0'*64),
                   lambda x: x['replacements']['pond_preload_left'].update(path=self.fixture.new['path']),
                   lambda x: x.update(namespace='unknown'),
                   lambda x: x['replacements'].update(neutral={key: self.fixture.new[key] for key in ('path', 'sha256')})]
        for change in changes:
            with self.subTest(change=change):
                override = deepcopy(self.override)
                change(override)
                self.configure(override)
                with self.assertRaises(ValueError):
                    library.build_index(self.root)

    def test_partial_registration_must_cover_exactly_the_requested_subset(self):
        override = deepcopy(self.override)
        del override['replacements']['pond_preload_right']
        self.configure(override)
        with self.assertRaisesRegex(ValueError, 'exactly the replacement poses'):
            library.build_index(self.root)

    def test_candidate_writer_wrong_neutral_or_changed_pixels_cannot_be_selected(self):
        self.configure()
        self.fixture.write(library.MANAGEMENT, {'schema_version': 1, 'batches': [], 'reservations': [{
            'id': 'fix-writer', 'owner': 'fix-agent', 'status': 'active', 'root': str(Path(self.fix).parent)}]})
        with self.assertRaisesRegex(ValueError, 'active generation tree'):
            library.build_index(self.root)
        self.fixture.write(library.MANAGEMENT, {'schema_version': 1, 'batches': [], 'reservations': []})
        registration = library.read(self.root/self.fix)
        registration['canonical_neutral']['sha256'] = '0'*64
        self.fixture.write(self.fix, registration)
        self.override['registration_sha256'] = self.fixture.sha(self.fix)
        self.configure()
        with self.assertRaisesRegex(ValueError, 'adopted neutral'):
            library.build_index(self.root)
        registration['canonical_neutral']['sha256'] = self.fixture.new['sha256']
        self.fixture.write(self.fix, registration)
        self.override['registration_sha256'] = self.fixture.sha(self.fix)
        self.configure()
        damaged = self.root/registration['frames'][0]['path']
        with Image.open(damaged) as image:
            changed = image.copy()
        changed.putpixel((12, 12), (255, 0, 0, 255))
        changed.save(damaged)
        with self.assertRaisesRegex(ValueError, 'source sheet changed'):
            library.build_index(self.root)

    def test_current_alias_changes_only_two_pngs_and_lists_both_source_registrations(self):
        library.refresh(self.root)
        unified.build(self.root)
        before = {p.relative_to(self.root).as_posix(): p.read_bytes()
                  for p in self.root.glob('assets/library/characters/*/current/**/*.png')}
        self.configure()
        library.refresh(self.root)
        shutil.rmtree(self.root/'assets/library/characters/bear-beret/current')
        unified.build(self.root)
        self.assertEqual(unified.verify(self.root)['assets'], 2)
        after = {p.relative_to(self.root).as_posix(): p.read_bytes()
                 for p in self.root.glob('assets/library/characters/*/current/**/*.png')}
        self.assertEqual(set(before), set(after))
        self.assertEqual({path for path in before if before[path] != after[path]}, {
            f'assets/library/characters/bear-beret/current/poses/app/{name}.png' for name in self.names[-2:]})
        manifest = library.read(self.root/'assets/library/characters/bear-beret/current/asset.json')
        override = next(x for x in manifest['source_registrations'] if x.get('role') == 'explicit-pose-override')
        self.assertEqual(override['path'], self.fix)
        self.assertEqual(override['pose_ids'], self.names[-2:])
        required = library._required_current_library_paths_locked(self.root, [])
        for path in [self.base, self.fix, self.evidence, *[p['path'] for p in self.override['replacements'].values()]]:
            self.assertIn(path, required)
        library.refresh(self.root)
        self.assertEqual(library.verify(self.root)['characters'], 2)


if __name__ == '__main__':
    unittest.main()
