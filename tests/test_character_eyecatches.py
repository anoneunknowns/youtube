"""Verify exact eye-catch crops, explicit scope and namespace compatibility."""
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
from tools import register_character_eyecatches as eye


class EyecatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / 'assets/library/characters/bear-beret/eyecatches/v001'
        self.folder.mkdir(parents=True)
        self.neutral = self.root / 'canonical.png'
        Image.new('RGBA', (32, 40), (80, 100, 50, 255)).save(self.neutral)
        self.canonical = {'id': 'bear-beret', 'neutral': {
            'path': 'canonical.png', 'sha256': eye.sha(self.neutral),
            'image_region_px': [0, 0, 32, 40], 'anchor_px': [16, 40],
            'reference_height_px': 40}}
        self.item = {'id': 'bear-beret', 'version': 'v001',
                     'review': {key: 'Reviewed fixture' for key in ['identity', 'style', 'alpha', 'motion']},
                     'sheets': []}
        for gi, (group, ids) in enumerate(eye.GROUPS.items()):
            sheet = Image.new('RGBA', (180, 180), 0)
            draw = ImageDraw.Draw(sheet)
            for i in range(9):
                x, y = i % 3 * 60, i // 3 * 60
                draw.rectangle((x + 10, y + 8, x + 40, y + 48), fill=(90 + i, 100, 40, 254))
            source = self.folder / (group + '.png')
            sheet.save(source)
            prompt = self.folder / (group + '-prompt.txt')
            prompt.write_text('Generate transparent identity-matched eye-catch poses')
            provenance = self.folder / (group + '-input.json')
            provenance.write_text(json.dumps({'input_references': [{'role': 'canonical identity',
                'path': 'canonical.png', 'sha256': eye.sha(self.neutral)}]}))
            self.item['sheets'].append({'id': group, 'source_sheet': str(source),
                'source_sheet_sha256': eye.sha(source), 'prompt_path': str(prompt),
                'generation_input_path': str(provenance), 'reference_height_px': 41 + gi * 4,
                'calibration': {'method': 'reviewed-calibration', 'reference_pose': ids[0], 'notes': 'Fixture evidence'},
                'frames': [{'id': name, 'index': i, 'body_bbox_px': [10, 8, 41, 49],
                    'anchor_px': [25.5, 49], 'support_kind': 'inferred-ground-plane' if name in eye.AIRBORNE else 'anatomical-support',
                    'support_notes': 'Fixture inferred ground plane' if name in eye.AIRBORNE else ''}
                    for i, name in enumerate(ids)]})

    def checked(self):
        return eye.validate_item(self.root, self.item, self.canonical, True)

    def saved(self):
        check = self.checked()
        for frame in check['frames']:
            destination = self.folder / (frame['id'] + '.png')
            frame['image'].save(destination)
            frame.update(path=eye.local(self.root, destination), sha256=eye.sha(destination))
        return check, {'canonical_neutral': self.canonical['neutral'],
            'sheets': [{'id': s['id'], 'source_sheet': eye.local(self.root, s['path']),
                'source_sheet_sha256': s['details']['sha256'], 'reference_height_px': s['reference_height_px']}
                for s in check['sheets']],
            'frames': [{k: v for k, v in f.items() if k != 'image'} for f in check['frames']]}

    def test_exact_crops_shared_scale_and_all_four_clips(self):
        check, registration = self.saved()
        self.assertEqual(len(library.verify_pose_registration(self.root, registration, 'bear-beret')), 18)
        self.assertEqual(set(eye.CLIPS), {'tea', 'bow', 'jump', 'dance'})
        for sequence in eye.CLIPS.values():
            self.assertTrue(set(sequence).issubset({f['id'] for f in check['frames']}))
        self.assertEqual([s['reference_height_px'] for s in check['sheets']], [41, 45])
        self.assertEqual(check['frames'][0]['image'].getchannel('A').getextrema(), (0, 254))

    def test_rejects_ref_changes_missing_states_and_airborne_contact_claim(self):
        bad = copy.deepcopy(self.item)
        bad['sheets'][0]['frames'].pop()
        with self.assertRaisesRegex(ValueError, 'coverage'):
            eye.validate_item(self.root, bad, self.canonical, True)
        for airborne in eye.AIRBORNE:
            bad = copy.deepcopy(self.item)
            next(f for f in bad['sheets'][1]['frames'] if f['id'] == airborne)['support_kind'] = 'anatomical-support'
            with self.assertRaisesRegex(ValueError, 'inferred ground plane'):
                eye.validate_item(self.root, bad, self.canonical, True)
        provenance = Path(self.item['sheets'][0]['generation_input_path'])
        data = json.loads(provenance.read_text())
        data['input_references'][0]['sha256'] = '0' * 64
        provenance.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'reference hash'):
            self.checked()

    def test_rejects_clipping_and_implicit_or_bird_scope(self):
        source = Path(self.item['sheets'][0]['source_sheet'])
        image = Image.open(source)
        image.putpixel((0, 18), (40, 50, 60, 255))
        image.save(source)
        with self.assertRaisesRegex(ValueError, 'cell edge'):
            eye.cells(source, 'tea_bow')
        config = self.root / 'config.json'
        for expected in [None, [], ['little-bird'], ['bear-beret', 'bear-beret']]:
            config.write_text(json.dumps({'expected_ids': expected, 'items': [self.item]}))
            with self.assertRaisesRegex(ValueError, 'expected_ids'):
                eye.register(self.root, config, True, True)

    def test_namespace_does_not_fallback_to_unprefixed_names(self):
        _, registration = self.saved()
        generated = registration['frames'][0]
        index = {'characters': [{**self.canonical,
            'expanded_key_poses': {'poses': {'neutral': generated}},
            'eyecatch_key_poses': {'poses': {'neutral': generated, 'tea_hold': registration['frames'][1]}}}]}
        (self.root / 'catalogs').mkdir()
        (self.root / library.INDEX).write_text(json.dumps(index))
        self.assertEqual(library.load_pose(self.root, 'bear-beret', 'neutral')[0].size, (32, 40))
        self.assertEqual(library.load_pose(self.root, 'bear-beret', 'eyecatch/neutral')[0].size, (60, 60))
        self.assertEqual(library.load_pose(self.root, 'bear-beret', 'expanded/neutral')[0].size, (60, 60))
        with self.assertRaisesRegex(ValueError, 'No generic reviewed pose'):
            library.load_pose(self.root, 'bear-beret', 'tea_hold')

    def test_verifier_rejects_eye_pose_name_and_sheet_swaps_after_rehash(self):
        _, registration = self.saved()
        target = self.folder / 'registration.json'
        target.write_text(json.dumps(registration))
        block = {'registration': eye.local(self.root, target), 'registration_sha256': eye.sha(target),
                 'sheet_reference_heights_px': {sheet['id']: sheet['reference_height_px'] for sheet in registration['sheets']},
                 'poses': {frame['id']: {**{key: frame[key] for key in ['path', 'sha256', 'size_px',
                    'anchor_px', 'body_bbox_px', 'tail_bbox_px', 'reference_height_px', 'sheet_id']},
                    'frame_id': frame['id']} for frame in registration['frames']}}
        original = {'source_collections': [], 'characters': [{**self.canonical, 'eyecatch_key_poses': block}]}
        def verify(index):
            library.write(self.root / library.INDEX, index)
            paths = sorted(path.relative_to(self.root).as_posix() for path in self.root.rglob('*')
                if path.is_file() and path.relative_to(self.root).as_posix() != library.FILES)
            library.write(self.root / library.FILES, {'files': [{'path': relative,
                'bytes': (self.root / relative).stat().st_size, 'sha256': library.sha(self.root / relative)} for relative in paths]})
            with patch.object(library, '_inventory_paths_locked', return_value=paths):
                return library.verify(self.root)
        self.assertEqual(verify(original)['generic_key_pose_pngs'], 18)
        for fault in ('name', 'sheet'):
            with self.subTest(fault=fault):
                index = copy.deepcopy(original)
                poses = index['characters'][0]['eyecatch_key_poses']['poses']
                if fault == 'name':
                    poses['tea_sip'], poses['bow_deep'] = poses['bow_deep'], poses['tea_sip']
                else:
                    poses['tea_sip']['sheet_id'] = 'jump_dance'
                with self.assertRaisesRegex(ValueError, 'Pose name or sheet differs'):
                    verify(index)

    def test_refresh_preserves_prior_blocks_and_verifies_export(self):
        _, registration = self.saved()
        target = self.folder / 'registration.json'
        target.write_text(json.dumps(registration))
        # Fixture a distinct prior common-scale block and an expanded block.
        old_frame = copy.deepcopy(registration['frames'][0])
        old_frame['id'] = 'blink'
        old_frame['reference_height_px'] = 82
        old_png = self.root / 'legacy.png'
        with Image.open(self.root / old_frame['path']) as image:
            image.save(old_png)
        old_frame.update(path='legacy.png', sha256=eye.sha(old_png))
        old_reg = self.root / 'legacy.json'
        old_reg.write_text(json.dumps({'source_sheet': registration['sheets'][0]['source_sheet'],
            'source_sheet_sha256': registration['sheets'][0]['source_sheet_sha256'],
            'common_reference_height_px': 82, 'frames': [old_frame]}))
        expanded = copy.deepcopy(registration)
        expanded['frames'] = [registration['frames'][0]]
        expanded_reg = self.root / 'expanded.json'
        expanded_reg.write_text(json.dumps(expanded))
        manifest = self.root / 'neutral.json'
        manifest.write_text('{}')
        stock = {'items': [{'id': 'bear-beret', 'source_version': 'v001',
            'source_manifest_path': 'neutral.json', 'source_manifest_sha256': eye.sha(manifest)}]}
        motions = {'items': [{'id': 'bear-beret', 'registration': 'legacy.json',
            'registration_sha256': eye.sha(old_reg), 'preview': 'old.png', 'motion_preview': 'old.gif'}]}
        style = {'records': [{'id': identity, 'path': 'canonical.png', 'sha256': eye.sha(self.neutral),
            'body_bbox_px': [0, 0, 32, 40], 'anchor_px': [16, 40], 'height_px': 40} for identity in library.NAMES]}
        expansion = {'status': 'stocked-and-assistant-reviewed', 'items': [{'id': 'bear-beret',
            'registration': 'expanded.json', 'registration_sha256': eye.sha(expanded_reg),
            'preview': 'expanded.png', 'motion_preview': 'expanded.gif'}]}
        eyecatches = {'status': 'stocked-and-assistant-reviewed', 'items': [{'id': 'bear-beret',
            'registration': eye.local(self.root, target), 'registration_sha256': eye.sha(target),
            'preview': 'eye.png', 'motion_preview': 'eye.gif'}]}
        for relative, data in [(library.STOCK, stock), (library.MOTIONS, motions),
                (library.STYLE, style), (library.EXPANSION, expansion)]:
            p = self.root / relative
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(data))
        def inventory(root):
            excluded = {library.FILES, *(path + '.lock' for path in (library.MANAGEMENT, library.INDEX, library.FILES))}
            return sorted(p.relative_to(root).as_posix() for p in root.rglob('*')
                if p.is_file() and p.relative_to(root).as_posix() not in excluded)
        with patch.object(library, '_inventory_paths_locked', side_effect=inventory):
            library.refresh(self.root)
            before = library.read(self.root / library.INDEX)['characters'][0]
            p = self.root / library.EYECATCHES
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(eyecatches))
            library.refresh(self.root)
            after = library.read(self.root / library.INDEX)['characters'][0]
            self.assertEqual(before['key_poses'], after['key_poses'])
            self.assertEqual(before['expanded_key_poses'], after['expanded_key_poses'])
            self.assertEqual(before['neutral'], after['neutral'])
            self.assertEqual(len(after['eyecatch_key_poses']['poses']), 18)
            self.assertEqual(library.verify(self.root)['generic_key_pose_pngs'], 20)
            with tempfile.TemporaryDirectory() as delivery:
                archive = Path(delivery) / 'library.zip'
                self.assertTrue(library.export(self.root, archive)['all_members_hash_verified'])
                with zipfile.ZipFile(archive) as z:
                    self.assertIn('character-library/' + eye.local(self.root, target), z.namelist())

    def test_centered_review_and_fixed_ground_playback(self):
        check = self.checked()
        eye.previews(self.root, check, self.folder)
        reports = eye.read(self.folder / 'alignment-report.json')['records']
        self.assertEqual(len(reports), 18)
        self.assertTrue(all(r['horizontal_centered'] and r['vertical_centered'] and r['passed'] for r in reports))
        playback = eye.read(self.folder / 'playback-geometry.json')
        self.assertEqual(len({tuple(f['support_point_px']) for f in playback['frames']}), 1)
        for group in eye.GROUPS:
            self.assertEqual(len({f['scale'] for f in playback['frames'] if f['sheet_id'] == group}), 1)
        self.assertTrue(all((self.folder / (name + '-preview.gif')).is_file() for name in eye.CLIPS))


if __name__ == '__main__':
    unittest.main()
