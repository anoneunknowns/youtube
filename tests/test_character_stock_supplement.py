"""Reviewed supplemental stock extends the shared entry layer without changing legacy selections."""
import copy
from contextlib import redirect_stdout
import io
from pathlib import Path
import unittest

from tests import test_character_gimmicks as fixtures
from tools import character_library as library
from tools import unified_asset_library as unified


class CharacterStockSupplementTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CharacterGimmickTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        for identity in self.fixture.IDS:
            self.fixture.add_gimmick(identity)
        self.before = library.build_index(self.root)
        self.items = []
        self.evidence = str(Path(library.SUPPLEMENT).parent/'qa-review.json')
        self.fixture.write_json(self.evidence, {'status': 'pass', 'scope': 'synthetic unit-test stock'})

    def collection(self, status='stocked-and-assistant-reviewed'):
        self.fixture.write_json(library.SUPPLEMENT, {'schema_version': 1, 'status': status,
            'review_evidence': [{'path': self.evidence, 'sha256': library.sha(self.root/self.evidence)}],
            'items': self.items})

    def add_stock(self, identity='bear-small', existing=False, icon=False):
        base = f'assets/library/characters/{identity}/generation-batches/supplement-fixture/'
        source = base+'neutral.png'
        self.fixture.save_image(source, self.fixture.subject())
        neutral = {'path': source, 'sha256': library.sha(self.root/source), 'source_size_px': [24, 24],
            'image_region_px': [0, 0, 24, 24], 'body_bbox_px': [8, 6, 16, 20],
            'anchor_px': [12, 20], 'reference_height_px': 14}
        item = {'id': identity, 'name_ja': identity, 'name_en': identity}
        if existing:
            neutral = next(x['neutral'] for x in self.before['characters'] if x['id'] == identity)
            item['neutral_reference'] = {key: neutral[key] for key in ('path', 'sha256')}
        else:
            item['neutral'] = neutral
        sheets, frames = [], []
        for pose in ('blink', 'pond_air_left'):
            relative = base+pose+'.png'
            self.fixture.save_image(relative, self.fixture.subject())
            checksum = library.sha(self.root/relative)
            sheets.append({'id': pose, 'source_sheet': relative, 'source_sheet_sha256': checksum,
                           'reference_height_px': 14})
            frames.append({'id': pose, 'sheet_id': pose, 'source_sheet': relative,
                'source_sheet_sha256': checksum, 'path': relative, 'sha256': checksum,
                'crop_from_sheet_xyxy': [0, 0, 24, 24], 'size_px': [24, 24],
                'body_bbox_px': [8, 6, 16, 20], 'tail_bbox_px': None, 'anchor_px': [12, 20],
                'anchor_kind': 'anatomical-support', 'anchor_measurement': 'measured',
                'vertical_motion_policy': 'scene-adds-trajectory', 'reference_height_px': 14})
        registration = base+'registration.json'
        self.fixture.write_json(registration, {'schema_version': 1, 'character_id': identity,
            'canonical_neutral': {key: neutral[key] for key in ('path', 'sha256')},
            'sheets': sheets, 'frames': frames, 'clips': {'react': {'frames': ['blink', 'pond_air_left'],
                                                                        'durations_ms': [100, 200]}}})
        item['pose_sets'] = [{'namespace': 'app', 'registration': registration,
                             'registration_sha256': library.sha(self.root/registration)}]
        if icon:
            relative = base+'face.png'
            self.fixture.save_image(relative, self.fixture.subject())
            item['icons'] = {'face': {'path': relative, 'sha256': library.sha(self.root/relative),
                'size_px': [24, 24], 'subject_bbox_px': [8, 6, 16, 20], 'role': 'face-icon'}}
        self.items.append(item)
        self.collection()
        return item

    def change_registration(self, item, edit):
        selected = item['pose_sets'][0]
        registration = library.read(self.root/selected['registration'])
        edit(registration)
        self.fixture.write_json(selected['registration'], registration)
        selected['registration_sha256'] = library.sha(self.root/selected['registration'])
        self.collection()

    def test_optional_collection_preserves_nineteen_then_adds_five_without_rebaselining(self):
        self.assertEqual(len(self.before['characters']), 19)
        for identity in ('bear-small', 'hamster', 'rabbit-flower', 'cream-companion', 'cat-patches'):
            self.add_stock(identity)
        index = library.build_index(self.root)
        self.assertEqual(index['characters'][:19], self.before['characters'])
        self.assertEqual(len(index['characters']), 24)
        library.refresh(self.root)
        self.assertEqual(library.verify(self.root)['characters'], 24)
        self.assertEqual(unified.build(self.root)['assets'], 24)
        self.assertEqual(unified.verify(self.root)['assets'], 24)

    def test_new_namespace_preserves_bear_neutral_pixels_and_icon_has_no_body_scale(self):
        self.add_stock('bear-beret', existing=True, icon=True)
        small = self.add_stock()
        small['scene_relative_scale'] = {'relative_to': 'bear-beret', 'body_height_ratio': 0.65}
        self.collection()
        index = library.build_index(self.root)
        self.assertEqual(index['characters'][0]['neutral'], self.before['characters'][0]['neutral'])
        library.refresh(self.root)
        image, anchor, reference = library.load_pose(self.root, 'bear-small', 'app/pond_air_left')
        self.assertEqual((anchor, reference), ([12, 20], 14))
        self.assertEqual(image.tobytes(), self.fixture.subject().tobytes())
        unified.build(self.root)
        self.assertEqual(unified.verify(self.root)['assets'], 20)
        manifest = library.read(self.root/'assets/library/characters/bear-small/current/asset.json')
        self.assertEqual(manifest['scene_relative_scale']['body_height_ratio'], 0.65)
        self.assertEqual(manifest['neutral']['reference_height_px'], 14)
        self.assertEqual(manifest['poses']['app/pond_air_left']['vertical_motion_policy'], 'scene-adds-trajectory')
        bear = library.read(self.root/'assets/library/characters/bear-beret/current/asset.json')
        self.assertEqual(bear['icons']['face']['role'], 'face-icon')
        self.assertNotIn('reference_height_px', bear['icons']['face'])
        self.assertNotIn('icons/face', bear['poses'])
        closure = library._required_current_library_paths_locked(self.root, [])
        for relative in (self.evidence, library.SUPPLEMENT, self.items[0]['icons']['face']['path'],
                         'assets/library/characters/bear-beret/current/icons/face.png'):
            self.assertIn(relative, closure)

    def test_unreviewed_collection_and_changed_review_evidence_fail_closed(self):
        self.add_stock()
        for status in ('generating', 'candidate', 'stocked'):
            self.collection(status)
            with self.assertRaisesRegex(ValueError, 'explicitly reviewed'):
                library.build_index(self.root)
        self.collection()
        (self.root/self.evidence).write_text('changed review')
        with self.assertRaisesRegex(ValueError, 'review evidence changed'):
            library.build_index(self.root)

    def test_active_writer_registration_cannot_be_selected(self):
        item = self.add_stock()
        self.fixture.write_json(library.MANAGEMENT, {'schema_version': 1, 'batches': [], 'reservations': [
            {'id': 'writer', 'owner': 'other-agent', 'status': 'active',
             'root': str(Path(item['pose_sets'][0]['registration']).parent)}]})
        with self.assertRaisesRegex(ValueError, 'active generation tree'):
            library.build_index(self.root)

    def test_existing_neutral_and_namespaces_cannot_be_replaced(self):
        item = self.add_stock('bear-beret', existing=True)
        item['neutral_reference']['sha256'] = '0'*64
        self.collection()
        with self.assertRaisesRegex(ValueError, 'preserve the existing adopted neutral'):
            library.build_index(self.root)
        item['neutral_reference'] = {key: self.before['characters'][0]['neutral'][key] for key in ('path', 'sha256')}
        item['pose_sets'][0]['namespace'] = 'expanded'
        self.collection()
        with self.assertRaisesRegex(ValueError, 'reserved namespace'):
            library.build_index(self.root)
        item['pose_sets'][0]['namespace'] = 'app'
        item['pose_sets'].append(copy.deepcopy(item['pose_sets'][0]))
        self.collection()
        with self.assertRaisesRegex(ValueError, 'Duplicate supplemental pose namespace'):
            library.build_index(self.root)

    def test_pose_source_pixels_calibration_and_neutral_binding_are_immutable(self):
        item = self.add_stock()
        original = library.read(self.root/item['pose_sets'][0]['registration'])
        for edit, message in [(lambda d: d['frames'][0].update(reference_height_px=15), 'scale changed'),
                              (lambda d: d['frames'][0].update(crop_from_sheet_xyxy=[1, 0, 24, 24]), 'pixels changed'),
                              (lambda d: d['canonical_neutral'].update(sha256='0'*64), 'adopted neutral')]:
            with self.subTest(message=message):
                self.fixture.write_json(item['pose_sets'][0]['registration'], original)
                self.change_registration(item, edit)
                with self.assertRaisesRegex(ValueError, message):
                    library.build_index(self.root)

    def test_scene_scale_does_not_accept_unknown_reference_or_icon_body_geometry(self):
        item = self.add_stock(icon=True)
        item['scene_relative_scale'] = {'relative_to': 'unknown', 'body_height_ratio': 0.65}
        self.collection()
        with self.assertRaisesRegex(ValueError, 'unknown character'):
            library.build_index(self.root)
        del item['scene_relative_scale']
        item['icons']['face']['reference_height_px'] = 14
        self.collection()
        with self.assertRaisesRegex(ValueError, 'no body registration'):
            library.build_index(self.root)

    def test_pose_registration_cannot_claim_another_character_identity_or_source(self):
        item = self.add_stock()
        original = library.read(self.root/item['pose_sets'][0]['registration'])
        self.change_registration(item, lambda d: d.update(character_id='hamster'))
        with self.assertRaisesRegex(ValueError, 'different character identity'):
            library.build_index(self.root)
        self.fixture.write_json(item['pose_sets'][0]['registration'], original)
        self.change_registration(item, lambda d: d['frames'][0].update(path=self.before['characters'][0]['neutral']['path']))
        with self.assertRaisesRegex(ValueError, 'own character source'):
            library.build_index(self.root)

    def test_cli_list_reports_additional_pose_namespaces_and_icons(self):
        self.add_stock('bear-beret', existing=True, icon=True)
        library.refresh(self.root)
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(library.main(['--root', str(self.root), 'list']), 0)
        rows = output.getvalue().splitlines()
        self.assertEqual(len(rows), 19)
        self.assertIn(' + 2 app poses + 1 icons', rows[0])
        self.assertTrue(rows[1].endswith('0 original poses + 0 expanded poses + 0 eye-catch poses'))


if __name__ == '__main__':
    unittest.main()
