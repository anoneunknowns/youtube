"""Explicit adoption must preserve historical QA and unrelated character choices."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

from tools import character_library as library
from tools import unified_asset_library as unified


class CharacterAdoptionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.names = patch.object(library, 'NAMES', {
            'bear-beret': ('クマ', 'Bear'), 'rabbit-beret': ('ウサギ', 'Rabbit')})
        self.names.start()
        self.addCleanup(self.names.stop)
        self.write(library.MANAGEMENT, {'schema_version': 1, 'batches': [], 'reservations': []})
        self.write(library.INDEX, {})
        self.old_bear = self.neutral('bear-beret', 'v001', (32, 48), [8, 6, 24, 42], 'gold')
        self.rabbit = self.neutral('rabbit-beret', 'v001', (32, 48), [8, 6, 24, 42], 'pink')
        style = {'records': [dict(self.old_bear, id='bear-beret', height_px=430),
                             dict(self.rabbit, id='rabbit-beret', height_px=430)]}
        self.write(library.STYLE, style)
        self.write(library.STOCK, {'items': []})
        self.write(library.MOTIONS, {'items': []})
        self.old_registration = 'assets/library/characters/bear-beret/eyecatches/v001/registration.json'
        self.registration(self.old_registration, self.old_bear, 'v001')
        self.write(library.EYECATCHES, {'status': 'stocked-and-assistant-reviewed', 'items': [{
            'id': 'bear-beret', 'registration': self.old_registration,
            'registration_sha256': self.sha(self.old_registration),
            'preview': self.old_bear['path'], 'motion_preview': self.old_bear['path']}]})
        self.historical = {name: (self.root/name).read_bytes()
                           for name in (library.STYLE, library.EYECATCHES, self.old_registration, self.old_bear['path'])}
        self.new = self.neutral('bear-beret', 'v002', (44, 60), [10, 8, 34, 52], 'orange')
        self.new_registration = 'assets/library/characters/bear-beret/eyecatches/v002/registration.json'
        self.registration(self.new_registration, self.new, 'v002', bow=True)
        self.evidence = 'design/current-adoption/evidence.json'
        self.write(self.evidence, {'reason': 'User requested reviewed recommendation as the current version.'})
        self.entry = {'id': 'bear-beret', 'status': 'adopted', 'neutral': deepcopy(self.new),
                      'eyecatch': {'version': 'v002', 'registration': self.new_registration,
                                   'registration_sha256': self.sha(self.new_registration),
                                   'preview': self.new['path'], 'motion_preview': self.new['path']},
                      'selection_evidence': [{'path': self.evidence, 'sha256': self.sha(self.evidence)}]}

    def write(self, relative, value):
        path = self.root/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def sha(self, relative):
        return library.sha(self.root/relative)

    def neutral(self, identity, version, size, body, color):
        relative = f'assets/library/characters/{identity}/references/canonical-neutral-{version}.png'
        path = self.root/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new('RGBA', size)
        ImageDraw.Draw(image).rectangle([body[0], body[1], body[2]-1, body[3]-1], fill=color)
        image.save(path)
        return {'path': relative, 'sha256': self.sha(relative), 'source_size_px': list(size),
                'image_region_px': [0, 0, *size], 'body_bbox_px': body,
                'anchor_px': [(body[0]+body[2])/2, body[3]], 'reference_height_px': body[3]-body[1]}

    def registration(self, relative, neutral, version, bow=False):
        frames, sheets = [], []
        for identity in ['neutral', *(['bow_half'] if bow else [])]:
            path = neutral['path']
            if identity == 'bow_half':
                path = f'assets/library/characters/bear-beret/eyecatches/{version}/bow_half.png'
                target = self.root/path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((self.root/neutral['path']).read_bytes())
            sheets.append({'id': identity, 'source_sheet': path, 'source_sheet_sha256': self.sha(path),
                           'reference_height_px': neutral['reference_height_px']})
            frames.append({'id': identity, 'path': path, 'sha256': self.sha(path),
                           'size_px': neutral['source_size_px'], 'sheet_id': identity,
                           'source_sheet': path, 'source_sheet_sha256': self.sha(path),
                           'crop_from_sheet_xyxy': neutral['image_region_px'],
                           'body_bbox_px': neutral['body_bbox_px'], 'anchor_px': neutral['anchor_px'],
                           'tail_bbox_px': None, 'reference_height_px': neutral['reference_height_px']})
        self.write(relative, {'schema_version': 2, 'kind': 'generated-character-eyecatch-key-pose-stock',
                             'character_id': 'bear-beret', 'version': version,
                             'status': 'stocked-and-assistant-reviewed', 'canonical_neutral': neutral,
                             'sheets': sheets, 'frames': frames,
                             'clips': {'bow' if bow else 'idle': [frame['id'] for frame in frames]}})

    def configure(self, entry=None):
        self.write(library.ADOPTIONS, {'schema_version': 1, 'kind': 'explicit-character-adoptions',
                                       'adoptions': [self.entry if entry is None else entry]})

    def change_registration(self, mutate):
        data = library.read(self.root/self.new_registration)
        mutate(data)
        self.write(self.new_registration, data)
        self.entry['eyecatch']['registration_sha256'] = self.sha(self.new_registration)

    def index(self):
        return library.build_index(self.root)

    def test_missing_override_preserves_legacy_sources_and_history(self):
        index = self.index()
        bear = next(item for item in index['characters'] if item['id'] == 'bear-beret')
        self.assertEqual(bear['neutral']['path'], self.old_bear['path'])
        self.assertEqual(bear['eyecatch_key_poses']['registration'], self.old_registration)
        for relative, data in self.historical.items():
            self.assertEqual((self.root/relative).read_bytes(), data)

    def test_override_changes_both_default_sources_without_touching_another_character(self):
        previous = self.index()
        self.configure()
        current = self.index()
        before, after = [{item['id']: item for item in index['characters']} for index in (previous, current)]
        self.assertEqual(before['rabbit-beret'], after['rabbit-beret'])
        self.assertEqual(after['bear-beret']['neutral']['path'], self.new['path'])
        self.assertEqual(after['bear-beret']['eyecatch_key_poses']['registration'], self.new_registration)
        self.assertEqual(after['bear-beret']['eyecatch_key_poses']['version'], 'v002')
        self.assertEqual(after['bear-beret']['eyecatch_collection'], library.ADOPTIONS)
        self.assertIn(library.ADOPTIONS, {item['path'] for item in current['source_collections']})
        self.write(library.INDEX, current)
        image, anchor, reference = library.load_pose(self.root, 'bear-beret')
        self.assertEqual(image.size, (44, 60))
        self.assertEqual(anchor, [22, 52])
        self.assertEqual(reference, 44)
        image, anchor, reference = library.load_pose(self.root, 'bear-beret', 'eyecatch/bow_half')
        self.assertEqual((image.size, reference), ((44, 60), 44))
        for relative, data in self.historical.items():
            self.assertEqual((self.root/relative).read_bytes(), data)

    def test_unknown_duplicate_or_unadopted_entries_are_rejected(self):
        for entries in [[dict(self.entry, id='unknown')], [self.entry, self.entry],
                        [dict(self.entry, status='candidate-not-adopted')]]:
            with self.subTest(entries=entries):
                self.write(library.ADOPTIONS, {'schema_version': 1, 'kind': 'explicit-character-adoptions', 'adoptions': entries})
                with self.assertRaises(ValueError):
                    self.index()

    def test_neutral_sha_size_reference_and_anchor_are_validated(self):
        for field, wrong in [('sha256', '0'*64), ('source_size_px', [45, 60]),
                             ('reference_height_px', 100), ('anchor_px', [100, 52]),
                             ('body_bbox_px', [10, 8, 44, 61]), ('image_region_px', [0, 0, 22, 60])]:
            with self.subTest(field=field):
                entry = deepcopy(self.entry)
                entry['neutral'][field] = wrong
                self.configure(entry)
                with self.assertRaises(ValueError):
                    self.index()

    def test_changed_neutral_pixels_cannot_be_adopted_with_the_previous_hash(self):
        self.configure()
        image = Image.open(self.root/self.new['path']).copy()
        image.putpixel((20, 20), (0, 0, 255, 255))
        image.save(self.root/self.new['path'])
        with self.assertRaisesRegex(ValueError, 'SHA-256 differs'):
            self.index()

    def test_registration_hash_and_character_identity_are_validated(self):
        entry = deepcopy(self.entry)
        entry['eyecatch']['registration_sha256'] = '0'*64
        self.configure(entry)
        with self.assertRaisesRegex(ValueError, 'SHA-256 differs'):
            self.index()
        self.change_registration(lambda data: data.update(character_id='rabbit-beret'))
        self.configure()
        with self.assertRaisesRegex(ValueError, 'identity/status differs'):
            self.index()

    def test_canonical_neutral_geometry_must_match_the_explicit_selection(self):
        self.change_registration(lambda data: data['canonical_neutral'].update(anchor_px=[23, 52]))
        self.configure()
        with self.assertRaisesRegex(ValueError, 'canonical neutral differs'):
            self.index()

    def test_neutral_frame_geometry_cannot_disagree_with_its_canonical_neutral(self):
        self.change_registration(lambda data: data['frames'][0].update(anchor_px=[23, 52]))
        self.configure()
        with self.assertRaisesRegex(ValueError, 'neutral frame geometry differs'):
            self.index()

    def test_duplicate_frames_wrong_crop_and_unknown_sheet_are_rejected(self):
        original = library.read(self.root/self.new_registration)
        mutations = [lambda data: data['frames'].append(deepcopy(data['frames'][0])),
                     lambda data: data['frames'][1].update(crop_from_sheet_xyxy=[0, 0, 40, 60]),
                     lambda data: data['frames'][1].update(sheet_id='missing')]
        for mutate in mutations:
            self.write(self.new_registration, original)
            self.change_registration(mutate)
            self.configure()
            with self.assertRaises(ValueError):
                self.index()

    def test_a_known_clip_cannot_silently_target_an_unregistered_pose(self):
        self.change_registration(lambda data: data.update(clips={'bow': ['unregistered']}))
        self.configure()
        with self.assertRaisesRegex(ValueError, 'unknown pose'):
            self.index()

    def test_selection_evidence_is_required_hash_checked_and_unique(self):
        for evidence in [[], [{'path': self.evidence, 'sha256': '0'*64}],
                         self.entry['selection_evidence']*2]:
            self.configure(dict(self.entry, selection_evidence=evidence))
            with self.assertRaises(ValueError):
                self.index()

    def test_malformed_schema_clip_names_and_missing_native_contract_are_rejected(self):
        original = library.read(self.root/self.new_registration)
        mutations = [lambda data: data.update(canonical_neutral=[]),
                     lambda data: data['frames'][1].update(sheet_id=[]),
                     lambda data: data['frames'][1].pop('tail_bbox_px'),
                     lambda data: data['frames'][1].update(crop_from_sheet_xyxy=[-1, 0, 44, 60]),
                     lambda data: data['frames'][1].update(tail_bbox_px=[0, 0, 100, 100]),
                     lambda data: data.update(clips={'bad clip': ['neutral']})]
        for mutate in mutations:
            self.write(self.new_registration, original)
            self.change_registration(mutate)
            self.configure()
            with self.assertRaises(ValueError):
                self.index()

    def test_video_cannot_be_required_selection_evidence(self):
        relative = 'design/current-adoption/local-only.mp4'
        (self.root/relative).write_bytes(b'local optional video')
        entry = deepcopy(self.entry)
        entry['selection_evidence'] = [{'path': relative, 'sha256': self.sha(relative)}]
        self.configure(entry)
        with self.assertRaisesRegex(ValueError, 'Video cannot'):
            self.index()

    def test_unified_current_can_be_rebuilt_after_archiving_only_the_changed_character(self):
        self.write(library.INDEX, self.index())
        unified.build(self.root)
        bear = 'assets/library/characters/bear-beret/current'
        rabbit = 'assets/library/characters/rabbit-beret/current/neutral.png'
        old_current = {str(path.relative_to(self.root/bear)): path.read_bytes()
                       for path in (self.root/bear).rglob('*') if path.is_file()}
        rabbit_bytes = (self.root/rabbit).read_bytes()
        self.configure()
        self.write(library.INDEX, self.index())
        with self.assertRaisesRegex(ValueError, 'Refusing to overwrite'):
            unified.build(self.root)
        backup = self.root/'.work/preserved-bear-current'
        backup.parent.mkdir()
        shutil.move(self.root/bear, backup)
        unified.build(self.root)
        self.assertEqual(unified.verify(self.root)['assets'], 2)
        self.assertEqual((self.root/rabbit).read_bytes(), rabbit_bytes)
        self.assertEqual(self.sha(bear+'/neutral.png'), self.new['sha256'])
        for relative, data in old_current.items():
            self.assertEqual((backup/relative).read_bytes(), data)
        for relative, data in self.historical.items():
            self.assertEqual((self.root/relative).read_bytes(), data)

    def test_operational_paths_and_own_character_sources_are_enforced(self):
        for path in ['/tmp/not-a-project.png', '../not-a-project.png', self.rabbit['path']]:
            entry = deepcopy(self.entry)
            entry['neutral']['path'] = path
            self.configure(entry)
            with self.assertRaises(ValueError):
                self.index()

    def test_active_registration_is_rejected_until_management_handoff(self):
        self.configure()
        self.write(library.MANAGEMENT, {'schema_version': 1, 'batches': [], 'reservations': [{
            'id': 'new-pose-registration', 'owner': 'manager', 'status': 'active',
            'root': 'assets/library/characters/bear-beret/eyecatches/v002'}]})
        with self.assertRaisesRegex(ValueError, 'active generation tree'):
            self.index()

    def test_inventory_and_portable_closure_include_override_and_external_evidence(self):
        self.configure()
        extras = [library.MANAGEMENT, library.INDEX, library.STOCK, library.MOTIONS, library.STYLE, library.EYECATCHES]
        with patch.object(library, 'SCOPES', ['assets/library/characters']), patch.object(library, 'EXTRAS', extras):
            paths = set(library.inventory_paths(self.root))
            self.assertIn(library.ADOPTIONS, paths)
            self.assertIn(self.evidence, paths)
            required = library._required_current_library_paths_locked(self.root, [])
            self.assertIn(library.ADOPTIONS, required)
            self.assertIn(self.evidence, required)
            self.assertIn(self.new_registration, required)
            self.assertNotIn(self.old_registration, required, 'Historical collection metadata must not require obsolete bear media.')
            for missing in [self.evidence, library.ADOPTIONS]:
                selected = sorted((paths | {library.PUBLICATION}) - {missing})
                self.write(library.PUBLICATION, {'schema_version': 1, 'scope': 'current-only-nonvideo',
                                                'files': selected, 'character_library_files': selected})
                with self.assertRaisesRegex(ValueError, 'omits required adopted library source'):
                    library.inventory_paths(self.root)


if __name__ == '__main__':
    unittest.main()
