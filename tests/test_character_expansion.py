"""Exercise source preservation, sheet calibration and canonical-neutral loading."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image, ImageDraw

from tools import character_library as library
from tools import register_character_expansion as expansion


class ExpansionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.folder = self.root / 'assets/library/characters/siamese-cat/motions/v002'
        self.folder.mkdir(parents=True)
        self.neutral = self.root / 'canonical.png'
        Image.new('RGBA', (32, 40), (1, 2, 3, 255)).save(self.neutral)
        self.canonical = {'id': 'siamese-cat', 'neutral': {
            'path': 'canonical.png', 'sha256': expansion.sha(self.neutral),
            'image_region_px': [0, 0, 32, 40], 'anchor_px': [16, 40],
            'reference_height_px': 40}}
        self.item = {'id': 'siamese-cat', 'version': 'v002',
                     'review': {key: 'Reviewed synthetic fixture' for key in ['identity', 'style', 'alpha', 'motion']},
                     'sheets': []}
        for group_index, (group, pose_ids) in enumerate(expansion.GROUPS.items()):
            sheet = Image.new('RGBA', (180, 180), (0, 0, 0, 0))
            draw = ImageDraw.Draw(sheet)
            for index in range(9):
                x, y = index % 3 * 60, index // 3 * 60
                draw.rectangle((x + 10, y + 8, x + 40, y + 48), fill=(80 + index * 10, 100, 50, 254))
            source = self.folder / (group + '.png')
            sheet.save(source)
            prompt = self.folder / (group + '-prompt.txt')
            prompt.write_text('Generate matching poses without changing identity', encoding='utf-8')
            provenance = self.folder / (group + '-input.json')
            provenance.write_text(json.dumps({'tool': 'built-in-imagegen', 'exact_model_identifier_exposed': False,
                'input_references': [{'path': 'canonical.png', 'sha256': expansion.sha(self.neutral), 'role': 'canonical-identity-reference'}]}))
            frames = [{'id': identity, 'index': index, 'body_bbox_px': [10, 8, 41, 49],
                       'anchor_px': [25.5, 49], 'support_kind': 'inferred-ground-plane' if identity in ('tap_pop', 'success_air') else 'anatomical-support',
                       'support_notes': 'Synthetic inferred ground plane for test' if identity in ('tap_pop', 'success_air') else ''}
                      for index, identity in enumerate(pose_ids)]
            self.item['sheets'].append({'id': group, 'source_sheet': str(source),
                'source_sheet_sha256': expansion.sha(source), 'prompt_path': str(prompt),
                'generation_input_path': str(provenance), 'reference_height_px': 41 + group_index * 3,
                'calibration': {'method': 'reviewed-sheet-calibration', 'reference_pose': pose_ids[0], 'notes': 'Fixture evidence'},
                'frames': frames})

    def checked(self):
        return expansion.validate_item(self.root, self.item, self.canonical, True)

    def saved_registration(self):
        check = self.checked()
        for frame in check['frames']:
            destination = self.folder / (frame['id'] + '.png')
            frame['image'].save(destination)
            frame['path'] = expansion.local(self.root, destination)
            frame['sha256'] = expansion.sha(destination)
        return check, {'sheets': [{'id': sheet['id'], 'source_sheet': expansion.local(self.root, sheet['path']),
            'source_sheet_sha256': sheet['details']['sha256'], 'reference_height_px': sheet['reference_height_px']}
            for sheet in check['sheets']], 'frames': [{key: value for key, value in frame.items() if key != 'image'} for frame in check['frames']]}

    def verifiable_index(self, legacy=False):
        _, registration = self.saved_registration()
        if legacy:
            sheet = registration['sheets'][0]
            registration = {'source_sheet': sheet['source_sheet'],
                'source_sheet_sha256': sheet['source_sheet_sha256'],
                'common_reference_height_px': sheet['reference_height_px'],
                'frames': [frame for frame in registration['frames'] if frame['id'] in ('blink', 'think')]}
        target = self.folder / 'registration.json'
        target.write_text(json.dumps(registration))
        poses = {}
        for frame in registration['frames']:
            poses[frame['id']] = {key: frame[key] for key in ['path', 'sha256', 'size_px',
                'anchor_px', 'body_bbox_px', 'tail_bbox_px', 'reference_height_px']}
            if not legacy:
                poses[frame['id']].update(frame_id=frame['id'], sheet_id=frame['sheet_id'])
        block = {'registration': expansion.local(self.root, target),
                 'registration_sha256': library.sha(target), 'poses': poses}
        if legacy:
            block['common_reference_height_px'] = registration['common_reference_height_px']
        else:
            block['sheet_reference_heights_px'] = {sheet['id']: sheet['reference_height_px'] for sheet in registration['sheets']}
        return {'source_collections': [], 'characters': [{**self.canonical,
            'key_poses' if legacy else 'expanded_key_poses': block}]}

    def verify_fixture(self, index):
        library.write(self.root / library.INDEX, index)
        paths = sorted(path.relative_to(self.root).as_posix() for path in self.root.rglob('*')
                       if path.is_file() and path.relative_to(self.root).as_posix() != library.FILES)
        library.write(self.root / library.FILES, {'files': [{'path': relative,
            'bytes': (self.root / relative).stat().st_size, 'sha256': library.sha(self.root / relative)} for relative in paths]})
        with patch.object(library, '_inventory_paths_locked', return_value=paths):
            return library.verify(self.root)

    def test_verifier_rejects_swapped_pose_names_with_consistent_file_hashes(self):
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                index = self.verifiable_index(legacy)
                self.assertEqual(self.verify_fixture(index)['neutral_png_sources'], 1)
                block = 'key_poses' if legacy else 'expanded_key_poses'
                poses = index['characters'][0][block]['poses']
                poses['blink'], poses['think'] = poses['think'], poses['blink']
                with self.assertRaisesRegex(ValueError, 'Pose name or sheet differs'):
                    self.verify_fixture(index)

    def test_verifier_rejects_wrong_frame_or_sheet_metadata_and_missing_names(self):
        original = self.verifiable_index()
        for fault in ('frame_id', 'sheet_id', 'pose_name'):
            with self.subTest(fault=fault):
                index = copy.deepcopy(original)
                poses = index['characters'][0]['expanded_key_poses']['poses']
                if fault == 'pose_name':
                    poses['unregistered-name'] = poses.pop('blink')
                else:
                    poses['blink'][fault] = 'think' if fault == 'frame_id' else 'postures'
                with self.assertRaisesRegex(ValueError, 'Pose name or sheet differs|coverage differs'):
                    self.verify_fixture(index)

    def test_neutral_source_count_measures_verified_unique_pngs(self):
        index = {'source_collections': [], 'characters': [copy.deepcopy(self.canonical),
            {**copy.deepcopy(self.canonical), 'id': 'second-character'}]}
        result = self.verify_fixture(index)
        self.assertEqual(result['characters'], 2)
        self.assertEqual(result['neutral_png_sources'], 1)

    def test_exact_crops_preserve_alpha254_and_independent_sheet_calibrations(self):
        check, registration = self.saved_registration()
        self.assertEqual(len(library.verify_pose_registration(self.root, registration, 'siamese-cat')), 27)
        for sheet in check['sheets']:
            self.assertEqual({frame['reference_height_px'] for frame in sheet['frames']}, {sheet['reference_height_px']})
            self.assertEqual(sheet['frames'][0]['image'].getchannel('A').getextrema(), (0, 254))
        self.assertEqual([sheet['reference_height_px'] for sheet in check['sheets']], [41, 44, 47])

    def test_rejects_wrong_reference_hash_and_missing_neutral(self):
        provenance = Path(self.item['sheets'][0]['generation_input_path'])
        data = json.loads(provenance.read_text())
        data['input_references'][0]['sha256'] = '0' * 64
        provenance.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'reference hash'):
            self.checked()
        data['input_references'] = []
        provenance.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'canonical neutral reference'):
            self.checked()

    def test_rejects_missing_state_or_unreviewed_airborne_support(self):
        original_frames = copy.deepcopy(self.item['sheets'][0]['frames'])
        self.item['sheets'][0]['frames'].pop()
        with self.assertRaisesRegex(ValueError, 'coverage'):
            self.checked()
        self.item['sheets'][0]['frames'] = original_frames
        self.item['sheets'][1]['frames'][1]['support_kind'] = 'anatomical-support'
        with self.assertRaisesRegex(ValueError, 'inferred ground plane'):
            self.checked()

    def test_rejects_cell_edge_contact_instead_of_masking(self):
        source = Path(self.item['sheets'][0]['source_sheet'])
        image = Image.open(source)
        image.putpixel((0, 15), (100, 100, 100, 255))
        image.save(source)
        with self.assertRaisesRegex(ValueError, 'cell edge'):
            expansion.cells(source, 'reactions')

    def test_verifier_rejects_per_pose_rescaling_or_changed_pixels(self):
        check, registration = self.saved_registration()
        damaged = copy.deepcopy(registration)
        damaged['frames'][1]['reference_height_px'] += 1
        with self.assertRaisesRegex(ValueError, 'sheet scale changed'):
            library.verify_pose_registration(self.root, damaged, 'siamese-cat')
        path = self.root / registration['frames'][1]['path']
        image = Image.open(path)
        image.putpixel((20, 20), (250, 250, 250, 255))
        image.save(path)
        registration['frames'][1]['sha256'] = library.sha(path)
        with self.assertRaisesRegex(ValueError, 'pixels changed'):
            library.verify_pose_registration(self.root, registration, 'siamese-cat')

    def test_original_neutral_and_expansion_neutral_are_separately_loadable(self):
        _, registration = self.saved_registration()
        generated = registration['frames'][0]
        index = {'characters': [{**self.canonical, 'expanded_key_poses': {'poses': {'neutral': generated}}}]}
        (self.root / 'catalogs').mkdir()
        (self.root / library.INDEX).write_text(json.dumps(index))
        neutral, anchor, height = library.load_pose(self.root, 'siamese-cat')
        generated_image, generated_anchor, generated_height = library.load_pose(self.root, 'siamese-cat', 'expanded/neutral')
        self.assertEqual(neutral.size, (32, 40))
        self.assertEqual(height, 40)
        self.assertEqual(generated_image.size, (60, 60))
        self.assertEqual(generated_height, 41)

    def test_refresh_preserves_original_block_and_explicit_expansion_export(self):
        check, registration = self.saved_registration()
        registration['canonical_neutral'] = self.canonical['neutral']
        new_registration = self.folder / 'registration.json'
        new_registration.write_text(json.dumps(registration))
        old_frame = copy.deepcopy(registration['frames'][1])
        # A different source path makes the retained old pose distinguishable.
        legacy_png = self.root / 'legacy-blink.png'
        legacy_sheet = self.root / 'legacy-sheet.png'
        with Image.open(self.root / registration['sheets'][0]['source_sheet']) as source:
            source.putpixel((old_frame['crop_from_sheet_xyxy'][0] + 20, 20), (60, 190, 40, 254))
            source.save(legacy_sheet)
            source.crop(old_frame['crop_from_sheet_xyxy']).save(legacy_png)
        old_frame['path'] = 'legacy-blink.png'
        old_frame['sha256'] = library.sha(legacy_png)
        old_frame['reference_height_px'] = 82
        old_registration = self.root / 'legacy-registration.json'
        old_registration.write_text(json.dumps({'source_sheet': 'legacy-sheet.png',
            'source_sheet_sha256': library.sha(legacy_sheet),
            'common_reference_height_px': 82, 'frames': [old_frame]}))
        source_manifest = self.root / 'neutral-manifest.json'
        source_manifest.write_text('{}')
        stock = {'items': [{'id': 'siamese-cat', 'source_version': 'v005',
            'source_manifest_path': 'neutral-manifest.json', 'source_manifest_sha256': library.sha(source_manifest)}]}
        motions = {'items': [{'id': 'siamese-cat', 'registration': 'legacy-registration.json',
            'registration_sha256': library.sha(old_registration), 'preview': 'old-preview.png', 'motion_preview': 'old-motion.gif'}]}
        style = {'records': [{'id': identity, 'path': 'canonical.png', 'sha256': library.sha(self.neutral),
            'body_bbox_px': [0, 0, 32, 40], 'anchor_px': [16, 40], 'height_px': 40} for identity in library.NAMES]}
        collection = {'status': 'stocked-and-assistant-reviewed', 'items': [{'id': 'siamese-cat',
            'registration': expansion.local(self.root, new_registration), 'registration_sha256': library.sha(new_registration),
            'preview': 'new-preview.png', 'motion_preview': 'new-motion.gif'}]}
        for relative, data in [(library.STOCK, stock), (library.MOTIONS, motions), (library.STYLE, style), (library.EXPANSION, collection)]:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data))
        def fixture_inventory(root):
            excluded = {library.FILES, *(path + '.lock' for path in (library.MANAGEMENT, library.INDEX, library.FILES))}
            return sorted(path.relative_to(root).as_posix() for path in root.rglob('*')
                          if path.is_file() and path.relative_to(root).as_posix() not in excluded)
        original_legacy_bytes = old_registration.read_bytes()
        with patch.object(library, '_inventory_paths_locked', side_effect=fixture_inventory):
            # Establish the exact original schema as concurrent adapters see it.
            expansion_manifest = self.root / library.EXPANSION
            expansion_manifest.unlink()
            library.refresh(self.root)
            old_index = library.read(self.root / library.INDEX)
            old_character = next(item for item in old_index['characters'] if item['id'] == 'siamese-cat')
            expansion_manifest.write_text(json.dumps(collection))
            library.refresh(self.root)
            adopted = next(item for item in library.read(self.root / library.INDEX)['characters'] if item['id'] == 'siamese-cat')
            keys = adopted['key_poses']
            self.assertEqual(keys, old_character['key_poses'])
            self.assertEqual(keys['common_reference_height_px'], 82)
            self.assertEqual(keys['poses']['blink']['path'], 'legacy-blink.png')
            expanded = adopted['expanded_key_poses']
            self.assertEqual(expanded['poses']['blink']['path'], registration['frames'][1]['path'])
            old_image, _, old_height = library.load_pose(self.root, 'siamese-cat', 'blink')
            new_image, _, new_height = library.load_pose(self.root, 'siamese-cat', 'expanded/blink')
            self.assertEqual(old_height, keys['common_reference_height_px'])
            self.assertEqual(new_height, expanded['poses']['blink']['reference_height_px'])
            self.assertNotEqual(old_image.tobytes(), new_image.tobytes())
            self.assertNotEqual(old_height, new_height)
            self.assertEqual(old_registration.read_bytes(), original_legacy_bytes)
            self.assertEqual(library.verify(self.root)['generic_key_pose_pngs'], 28)
            with tempfile.TemporaryDirectory() as delivery:
                archive = Path(delivery) / 'library.zip'
                receipt = library.export(self.root, archive)
                self.assertTrue(receipt['all_members_hash_verified'])
                with zipfile.ZipFile(archive) as bundle:
                    names = bundle.namelist()
                    self.assertIn('character-library/legacy-registration.json', names)
                    self.assertIn('character-library/' + expansion.local(self.root, new_registration), names)

    def test_review_tiles_measure_both_axes_and_playback_retains_sheet_scale(self):
        check = self.checked()
        expansion.previews(self.root, check, self.folder)
        report = expansion.read(self.folder / 'alignment-report.json')
        self.assertEqual(len(report['records']), 27)
        for record in report['records']:
            self.assertTrue(record['horizontal_centered'])
            self.assertTrue(record['vertical_centered'])
            self.assertTrue(record['passed'])
        playback = expansion.read(self.folder / 'playback-geometry.json')
        for group in expansion.GROUPS:
            scales = {frame['scale'] for frame in playback['frames'] if frame['sheet_id'] == group}
            self.assertEqual(len(scales), 1)
        self.assertEqual(len({tuple(frame['support_point_px']) for frame in playback['frames']}), 1)


if __name__ == '__main__':
    unittest.main()
