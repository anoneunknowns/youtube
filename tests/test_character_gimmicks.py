"""Background props share the existing library without changing animal selections."""
from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image, ImageDraw

from tools import character_library as library


class CharacterGimmickTests(unittest.TestCase):
    IDS = ['grass', 'flower-bed', 'airplane', 'rocket', 'helicopter',
           'butterfly', 'ladybug', 'rainbow']

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.items = []
        self.write_json(library.MANAGEMENT, {'schema_version': 1, 'batches': [], 'reservations': []})
        records = []
        for identity in library.NAMES:
            relative = f'assets/library/characters/{identity}/sources/v001/neutral.png'
            self.save_image(relative, self.subject())
            records.append({'id': identity, 'path': relative, 'sha256': library.sha(self.root / relative),
                            'body_bbox_px': [8, 6, 16, 20], 'anchor_px': [12, 20], 'height_px': 14})
        self.write_json(library.STOCK, {'items': []})
        self.write_json(library.MOTIONS, {'items': []})
        self.write_json(library.STYLE, {'records': records})
        extras = patch.object(library, 'EXTRAS', [library.MANAGEMENT, library.INDEX,
                                                 library.STOCK, library.MOTIONS, library.STYLE])
        extras.start()
        self.addCleanup(extras.stop)

    def write_json(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        library.write(path, value)

    def save_image(self, relative, image):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)

    @staticmethod
    def subject():
        image = Image.new('RGBA', (24, 24), (0, 0, 0, 0))
        ImageDraw.Draw(image).rectangle((8, 6, 15, 19), fill=(120, 90, 50, 255))
        return image

    def add_gimmick(self, identity='grass', anchor_kind='base'):
        prefix = f'assets/library/characters/{identity}/'
        neutral = prefix + 'sources/v001/neutral.png'
        image = self.subject()
        self.save_image(neutral, image)
        anchor = [12, 12] if anchor_kind == 'center' else [12, 20]
        prompt = prefix + 'sources/v001/generation-prompt.txt'
        (self.root / prompt).write_text('Synthetic unit-test source, not production artwork.\n')
        manifest = prefix + 'sources/v001/source-manifest.json'
        self.write_json(manifest, {'schema_version': 1, 'category': 'gimmick', 'character_id': identity,
            'render_registration': {'neutral_path': 'neutral.png', 'neutral_sha256': library.sha(self.root / neutral),
                'size_px': [24, 24], 'body_bbox_px': [8, 6, 16, 20], 'neutral_anchor_px': anchor,
                'neutral_natural_height_px': 14, 'anchor_kind': anchor_kind},
            'files': [{'path': 'neutral.png'}, {'path': 'generation-prompt.txt'}]})
        sheet_relative = prefix + 'motions/v001/source-sheet.png'
        sheet = Image.new('RGBA', (48, 24), (0, 0, 0, 0))
        sheet.paste(image, (0, 0))
        sheet.paste(image, (24, 0))
        self.save_image(sheet_relative, sheet)
        frames = []
        for n, pose_id in enumerate(('rest', 'active')):
            relative = prefix + 'motions/v001/' + pose_id + '.png'
            self.save_image(relative, sheet.crop((24*n, 0, 24*(n+1), 24)))
            frames.append({'id': pose_id, 'path': relative, 'sha256': library.sha(self.root / relative),
                'size_px': [24, 24], 'crop_from_sheet_xyxy': [24*n, 0, 24*(n+1), 24],
                'anchor_px': anchor, 'anchor_kind': anchor_kind, 'body_bbox_px': [8, 6, 16, 20],
                'subject_bbox_px': [8, 6, 16, 20], 'tail_bbox_px': None, 'reference_height_px': 14})
        registration = prefix + 'motions/v001/registration.json'
        self.write_json(registration, {'schema_version': 3, 'kind': 'generated-gimmick-key-pose-stock',
            'category': 'gimmick', 'character_id': identity, 'source_sheet': sheet_relative,
            'source_sheet_sha256': library.sha(self.root / sheet_relative), 'common_reference_height_px': 14,
            'canonical_neutral': {'path': neutral, 'sha256': library.sha(self.root / neutral)},
            'frames': frames, 'clips': {'sway': {'frames': ['rest', 'active', 'rest'],
                'durations_ms': [200, 300, 200], 'loop': True}}})
        preview, motion = prefix + 'motions/v001/pose-review.png', prefix + 'motions/v001/key-pose-preview.gif'
        self.save_image(preview, image)
        self.save_image(motion, image)
        item = {'id': identity, 'name_ja': identity + 'のテスト素材', 'name_en': identity,
            'category': 'gimmick', 'source_manifest_path': manifest,
            'source_manifest_sha256': library.sha(self.root / manifest),
            'registration': registration, 'registration_sha256': library.sha(self.root / registration),
            'preview': preview, 'motion_preview': motion}
        self.items.append(item)
        self.write_collection()
        return item

    def write_collection(self):
        self.write_json(library.GIMMICKS, {'schema_version': 1,
            'kind': 'reviewed-background-gimmick-collection', 'status': 'stocked-and-assistant-reviewed',
            'items': self.items})

    def change_registration(self, item, edit):
        path = self.root / item['registration']
        value = library.read(path)
        edit(value)
        library.write(path, value)
        item['registration_sha256'] = library.sha(path)
        self.write_collection()

    def add_multisheet_gimmick(self):
        item = self.add_gimmick('rocket', 'center')
        prefix = 'assets/library/characters/rocket/'
        sheets, frames = [], []
        for sheet_id, size, bounds, reference in [
                ('a', [140, 160], [40, 30, 100, 130], 100),
                ('b', [170, 190], [50, 35, 120, 155], 120)]:
            subject = Image.new('RGBA', size, (0, 0, 0, 0))
            ImageDraw.Draw(subject).rectangle((bounds[0], bounds[1], bounds[2]-1, bounds[3]-1),
                                             fill=(120, 90, 50, 255))
            sheet = Image.new('RGBA', (size[0]*2, size[1]), (0, 0, 0, 0))
            sheet.paste(subject, (0, 0))
            sheet.paste(subject, (size[0], 0))
            sheet_path = prefix + 'motions/v001/source-sheets/' + sheet_id + '.png'
            self.save_image(sheet_path, sheet)
            prompt = prefix + 'motions/v001/source-sheets/' + sheet_id + '-prompt.txt'
            inputs = prefix + 'motions/v001/source-sheets/' + sheet_id + '-input.json'
            (self.root / prompt).write_text('Native synthetic sheet calibration fixture.\n')
            self.write_json(inputs, {'fixture': True})
            sheets.append({'id': sheet_id, 'source_sheet': sheet_path,
                'source_sheet_sha256': library.sha(self.root / sheet_path),
                'reference_height_px': reference, 'generation_input': inputs, 'generation_prompt': prompt})
            for n, label in enumerate(('neutral', 'active')):
                pose_id = label + '_' + sheet_id
                path = prefix + 'motions/v001/' + pose_id + '.png'
                crop = [size[0]*n, 0, size[0]*(n+1), size[1]]
                self.save_image(path, sheet.crop(crop))
                frames.append({'id': pose_id, 'path': path, 'sha256': library.sha(self.root / path),
                    'size_px': size, 'crop_from_sheet_xyxy': crop, 'anchor_px': [size[0]/2, size[1]/2],
                    'anchor_kind': 'center', 'body_bbox_px': bounds, 'subject_bbox_px': bounds,
                    'tail_bbox_px': None, 'reference_height_px': reference, 'sheet_id': sheet_id,
                    'source_sheet': sheet_path, 'source_sheet_sha256': sheets[-1]['source_sheet_sha256']})
        neutral_relative = prefix + 'sources/v001/neutral.png'
        (self.root / neutral_relative).write_bytes((self.root / frames[0]['path']).read_bytes())
        manifest = library.read(self.root / item['source_manifest_path'])
        manifest['render_registration'].update(neutral_sha256=frames[0]['sha256'],
            size_px=frames[0]['size_px'], body_bbox_px=frames[0]['body_bbox_px'],
            neutral_anchor_px=frames[0]['anchor_px'], neutral_natural_height_px=100)
        self.write_json(item['source_manifest_path'], manifest)
        item['source_manifest_sha256'] = library.sha(self.root / item['source_manifest_path'])
        registration = {'schema_version': 3, 'kind': 'generated-gimmick-key-pose-stock',
            'category': 'gimmick', 'character_id': 'rocket', 'common_reference_height_px': 100,
            'canonical_neutral': {'path': neutral_relative, 'sha256': frames[0]['sha256'], 'frame_id': 'neutral_a'},
            'sheets': sheets, 'frames': frames,
            'clips': {'flight': {'frames': ['neutral_a', 'active_a', 'active_b'],
                                  'durations_ms': [300, 200, 300], 'loop': True}}}
        self.write_json(item['registration'], registration)
        item['registration_sha256'] = library.sha(self.root / item['registration'])
        self.write_collection()
        return item

    def test_native_multisheet_gimmick_uses_each_calibrated_sheet_scale(self):
        item = self.add_multisheet_gimmick()
        original_sheets = {sheet['source_sheet']: (self.root / sheet['source_sheet']).read_bytes()
                           for sheet in library.read(self.root / item['registration'])['sheets']}
        library.refresh(self.root)
        result = library.verify(self.root)
        self.assertEqual(result['generic_key_pose_pngs'], 4)
        selected = library.read(self.root / library.INDEX)['characters'][-1]
        self.assertEqual(selected['key_poses']['common_reference_height_px'], 100)
        self.assertEqual(selected['key_poses']['sheet_reference_heights_px'], {'a': 100, 'b': 120})
        for pose_id, size, reference in [('neutral_a', (140, 160), 100), ('active_b', (170, 190), 120)]:
            image, anchor, height = library.load_pose(self.root, 'rocket', 'gimmick/' + pose_id)
            self.assertEqual(image.size, size)
            self.assertEqual(height, reference)
        preview = library.preview(self.root, 'rocket', 'gimmick/active_b', 240,
                                  self.root / 'native-sheet-preview.png', 'transparent')
        self.assertEqual(preview['scale'], 2)
        for path, payload in original_sheets.items():
            self.assertEqual((self.root / path).read_bytes(), payload)

    def test_multisheet_gimmick_rejects_pose_scale_or_neutral_binding_changes(self):
        item = self.add_multisheet_gimmick()
        original = library.read(self.root / item['registration'])
        changes = [
            (lambda r: r['frames'][2].update(reference_height_px=119), 'share a calibrated'),
            (lambda r: r['frames'][2].update(sheet_id='missing'), 'Unknown gimmick source sheet'),
            (lambda r: r['sheets'][1].update(id='a'), 'duplicate gimmick sheet'),
            (lambda r: r['canonical_neutral'].update(frame_id='active_b'), 'not bound to a source frame'),
        ]
        for change, message in changes:
            with self.subTest(message=message):
                library.write(self.root / item['registration'], copy.deepcopy(original))
                self.change_registration(item, change)
                with self.assertRaisesRegex(ValueError, message):
                    library.build_index(self.root)

    def test_nineteen_entries_share_one_index_and_preserve_old_selections(self):
        before = library.build_index(self.root)
        for i, identity in enumerate(self.IDS):
            self.add_gimmick(identity, ('ground', 'base', 'center')[i % 3])
        library.refresh(self.root)
        index = library.read(self.root / library.INDEX)
        self.assertEqual(index['characters'][:11], before['characters'])
        self.assertEqual(len(index['characters']), 19)
        self.assertEqual(sum(row['category'] == 'gimmick' for row in index['characters']), 8)
        result = library.verify(self.root)
        self.assertEqual(result['characters'], 19)
        self.assertEqual(result['generic_key_pose_pngs'], 16)
        for identity in self.IDS:
            image, anchor, height = library.load_pose(self.root, identity, 'gimmick/active')
            self.assertEqual(image.tobytes(), self.subject().tobytes())
            self.assertEqual(height, 14)
            self.assertEqual(len(anchor), 2)
        printed = io.StringIO()
        with redirect_stdout(printed):
            self.assertEqual(library.main(['--root', str(self.root), 'list']), 0)
        self.assertEqual(len(printed.getvalue().splitlines()), 19)
        self.assertIn('\tgimmick\t', printed.getvalue())
        self.assertIn('\tcharacter\t', printed.getvalue())

    def test_namespaces_and_calibrated_preview_work_without_feet(self):
        self.add_gimmick('airplane', 'center')
        library.refresh(self.root)
        neutral, anchor, height = library.load_pose(self.root, 'airplane')
        self.assertEqual(anchor, [12, 12])
        self.assertEqual(height, 14)
        with self.assertRaisesRegex(ValueError, 'require gimmick/<pose>'):
            library.load_pose(self.root, 'airplane', 'active')
        with self.assertRaisesRegex(ValueError, 'not a gimmick'):
            library.load_pose(self.root, 'bear-beret', 'gimmick/rest')
        result = library.preview(self.root, 'airplane', 'gimmick/active', 28,
                                 self.root / 'preview.png', 'transparent')
        self.assertEqual(result['scale'], 2)
        self.assertEqual(neutral.tobytes(), self.subject().tobytes())

    def test_clip_targets_and_common_scale_cannot_be_redefined_per_pose(self):
        item = self.add_gimmick()
        original = library.read(self.root / item['registration'])
        changes = [
            (lambda r: r['frames'][0].update(anchor_kind='feet'), 'anchor_kind'),
            (lambda r: r['frames'][1].update(reference_height_px=12), 'share a calibrated'),
            (lambda r: r['clips']['sway'].update(frames=['missing']), 'unknown pose'),
            (lambda r: r['clips']['sway'].update(durations_ms=[0, 200, 200]), 'clip timing'),
            (lambda r: r['frames'][0].update(subject_bbox_px=[0, 0, 1, 1]), 'subject/body bounds differ'),
        ]
        for change, message in changes:
            with self.subTest(message=message):
                library.write(self.root / item['registration'], copy.deepcopy(original))
                self.change_registration(item, change)
                with self.assertRaisesRegex(ValueError, message):
                    library.build_index(self.root)

    def test_duplicate_collection_ids_and_changed_neutral_are_rejected(self):
        item = self.add_gimmick()
        self.items.append(copy.deepcopy(item))
        self.write_collection()
        with self.assertRaisesRegex(ValueError, 'Duplicate character/gimmick identity'):
            library.build_index(self.root)
        self.items.pop()
        self.write_collection()
        neutral = self.root / 'assets/library/characters/grass/sources/v001/neutral.png'
        neutral.write_bytes(b'changed adopted source')
        with self.assertRaisesRegex(ValueError, 'Gimmick neutral changed'):
            library.build_index(self.root)

    def test_current_profile_preserves_gimmick_provenance_and_standalone_export(self):
        item = self.add_gimmick()
        library.refresh(self.root)
        paths = {entry['path'] for entry in library.read(self.root / library.FILES)['files']} | {library.PUBLICATION}
        def publish(selected):
            self.write_json(library.PUBLICATION, {'schema_version': 1, 'scope': 'current-only-nonvideo',
                'files': sorted(paths | {library.FILES}), 'character_library_files': sorted(selected)})
        prompt = 'assets/library/characters/grass/sources/v001/generation-prompt.txt'
        publish(paths - {prompt})
        with self.assertRaisesRegex(ValueError, 'omits required adopted library source'):
            library.refresh(self.root)
        publish(paths)
        library.refresh(self.root)
        expected = library.verify(self.root)
        output = self.root / 'gimmicks.zip'
        library.export(self.root, output)
        with zipfile.ZipFile(output) as archive:
            archive.extractall(self.root / 'extracted')
        self.assertEqual(library.verify(self.root / 'extracted/character-library'), expected)


if __name__ == '__main__':
    unittest.main()
