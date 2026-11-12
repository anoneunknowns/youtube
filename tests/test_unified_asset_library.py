"""The shared entry layer preserves adopted pixels, geometry and source identity."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

from tools import character_library as characters
from tools import unified_asset_library as unified


class UnifiedAssetLibraryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.old = self.asset('rabbit-beret', 'character', atlas=True)
        self.new = self.asset('grass', 'gimmick')
        self.index = {'schema_version': 1, 'characters': [self.old, self.new]}
        self.write_json(unified.INDEX, self.index)

    def write_json(self, relative, document):
        path = self.root/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(unified.payload(document))

    def save(self, relative, image):
        path = self.root/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def asset(self, identity, category, atlas=False):
        base = 'assets/library/characters/'+identity+'/'
        image = Image.new('RGBA', (64, 48) if atlas else (32, 32), (0, 0, 0, 0))
        bounds = [18, 12, 38, 36] if atlas else [6, 5, 25, 29]
        ImageDraw.Draw(image).rectangle((bounds[0], bounds[1], bounds[2]-1, bounds[3]-1), fill=(121, 55, 5, 243))
        image.putpixel((bounds[0]+1, bounds[1]+1), (33, 155, 74, 254))
        source = base+'sources/v001/neutral-atlas.png'
        neutral = {'path': source, 'sha256': self.save(source, image), 'source_size_px': list(image.size),
            'image_region_px': [12, 8, 44, 40] if atlas else [0, 0, 32, 32],
            'body_bbox_px': bounds, 'anchor_px': [28, 36] if atlas else [15, 29],
            'tail_bbox_px': [36, 20, 42, 34] if atlas else None, 'reference_height_px': 24}
        selected = {'id': identity, 'name_ja': 'テスト'+identity, 'name_en': identity,
                    'category': category, 'neutral': neutral}
        for block, namespace, pose in [('key_poses', 'gimmick' if category == 'gimmick' else 'basic', 'blink'),
                                       ('expanded_key_poses', 'expanded', 'rest'), ('eyecatch_key_poses', 'eyecatch', 'sip')]:
            if category == 'gimmick' and block != 'key_poses':
                continue
            pose_image = Image.new('RGBA', (32, 32), (0, 0, 0, 0))
            ImageDraw.Draw(pose_image).ellipse((5, 4, 26, 28), fill=(88, 140, 55, 254))
            pose_path = base+'motions/'+namespace+'/'+pose+'.png'
            record = {'path': pose_path, 'sha256': self.save(pose_path, pose_image), 'size_px': [32, 32],
                'anchor_px': [16, 29], 'body_bbox_px': [5, 4, 27, 29], 'tail_bbox_px': None, 'reference_height_px': 25}
            registration_path = base+'motions/'+namespace+'/registration.json'
            registration = {'frames': [{'id': pose, **record}]}
            if namespace == 'expanded':
                registration['clips'] = {'bounce': ['rest', 'rest']}
            self.write_json(registration_path, registration)
            selected[block] = {'registration': registration_path,
                'registration_sha256': unified.digest((self.root/registration_path).read_bytes()), 'poses': {pose: record}}
            if namespace == 'eyecatch':
                selected[block]['clips'] = {'tea': ['sip', 'sip']}
            if namespace == 'gimmick':
                selected[block]['clips'] = {'sway': {'frames': ['blink', 'blink'], 'durations_ms': [200, 300], 'loop': True}}
        return selected

    def manifest(self, identity):
        path = self.root/f'assets/library/characters/{identity}/current/asset.json'
        return json.loads(path.read_text())

    def test_old_atlas_and_new_gimmick_use_the_same_physical_format(self):
        originals = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(unified.build(self.root)['assets'], 2)
        self.assertEqual(unified.verify(self.root)['assets'], 2)
        old, new = self.manifest('rabbit-beret'), self.manifest('grass')
        self.assertEqual(old.keys(), new.keys())
        self.assertEqual(old['neutral']['path'], new['neutral']['path'])
        self.assertEqual(old['neutral']['anchor_px'], [16, 28])
        self.assertEqual(old['neutral']['body_bbox_px'], [6, 4, 26, 28])
        self.assertEqual(old['neutral']['tail_bbox_px'], [24, 12, 30, 26])
        self.assertEqual(old['neutral']['reference_height_px'], 24)
        self.assertEqual(old['neutral']['source_image_region_px'], [12, 8, 44, 40])
        with Image.open(self.root/self.old['neutral']['path']) as source, Image.open(
                self.root/'assets/library/characters/rabbit-beret/current/neutral.png') as alias:
            self.assertEqual(alias.mode, 'RGBA')
            self.assertEqual(alias.tobytes(), source.crop((12, 8, 44, 40)).tobytes())
        self.assertEqual((self.root/'assets/library/characters/grass/current/neutral.png').read_bytes(),
                         (self.root/self.new['neutral']['path']).read_bytes())
        for relative, data in originals.items():
            self.assertEqual((self.root/relative).read_bytes(), data)
        for asset in (old, new):
            for pose in asset['poses'].values():
                alias = self.root/f'assets/library/characters/{asset["id"]}/current'/pose['path']
                self.assertEqual(alias.read_bytes(), (self.root/pose['source_path']).read_bytes())

    def test_clip_targets_are_qualified_and_missing_old_clips_keep_registration_links(self):
        unified.build(self.root)
        base = self.root/'assets/library/characters/rabbit-beret/current'
        clips = json.loads((base/'clips.json').read_text())
        self.assertEqual(clips['clips']['expanded/bounce']['frames'], ['expanded/rest', 'expanded/rest'])
        self.assertEqual(clips['clips']['eyecatch/tea']['frames'], ['eyecatch/sip', 'eyecatch/sip'])
        self.assertFalse(next(r for r in clips['source_registrations'] if r['namespace'] == 'basic')['clips_available'])
        prop = json.loads((self.root/'assets/library/characters/grass/current/clips.json').read_text())
        self.assertEqual(prop['clips']['gimmick/sway']['durations_ms'], [200, 300])
        self.assertEqual(prop['clips']['gimmick/sway']['frames'], ['gimmick/blink', 'gimmick/blink'])

    def test_build_is_idempotent_and_refuses_changed_alias_without_touching_sources(self):
        unified.build(self.root)
        before = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        unified.build(self.root)
        self.assertEqual(before, {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        alias = self.root/'assets/library/characters/grass/current/poses/gimmick/blink.png'
        alias.write_bytes(b'changed alias')
        with self.assertRaisesRegex(ValueError, 'Current PNG differs'):
            unified.verify(self.root)
        with self.assertRaisesRegex(ValueError, 'Refusing to overwrite'):
            unified.build(self.root)
        self.assertEqual(alias.read_bytes(), b'changed alias')

    def test_wrong_source_hash_and_tampered_geometry_cannot_be_rebaselined(self):
        self.index['characters'][0]['neutral']['sha256'] = '0'*64
        self.write_json(unified.INDEX, self.index)
        with self.assertRaisesRegex(ValueError, 'SHA-256 differs from adopted index'):
            unified.build(self.root)
        self.assertFalse((self.root/unified.MASTER).exists())
        self.index['characters'][0]['neutral']['sha256'] = unified.digest((self.root/self.old['neutral']['path']).read_bytes())
        self.write_json(unified.INDEX, self.index)
        unified.build(self.root)
        relative = 'assets/library/characters/rabbit-beret/current/asset.json'
        manifest = self.manifest('rabbit-beret')
        manifest['neutral']['anchor_px'] = [0, 0]
        self.write_json(relative, manifest)
        master = json.loads((self.root/unified.MASTER).read_text())
        master['assets'][0]['sha256'] = unified.digest((self.root/relative).read_bytes())
        self.write_json(unified.MASTER, master)
        with self.assertRaisesRegex(ValueError, 'master differs from the adopted index'):
            unified.verify(self.root)

    def test_unknown_current_files_are_rejected_and_never_deleted(self):
        unified.build(self.root)
        unknown = self.root/'assets/library/characters/grass/current/unknown.txt'
        unknown.write_text('retain this for inspection')
        with self.assertRaisesRegex(ValueError, 'unlisted files'):
            unified.verify(self.root)
        with self.assertRaisesRegex(ValueError, 'no files deleted'):
            unified.build(self.root)
        self.assertEqual(unknown.read_text(), 'retain this for inspection')

    def test_source_change_during_copy_does_not_publish_a_master(self):
        original = unified.create_alias
        calls = 0
        def change_after_copy(*args, **kwargs):
            nonlocal calls
            original(*args, **kwargs)
            calls += 1
            if calls == 1:
                path = self.root/unified.INDEX
                path.write_bytes(path.read_bytes()+b'\n')
        with patch.object(unified, 'create_alias', side_effect=change_after_copy):
            with self.assertRaisesRegex(ValueError, 'Source changed during build'):
                unified.build(self.root)
        self.assertFalse((self.root/unified.MASTER).exists())
        self.assertFalse((self.root/'assets/library/characters/rabbit-beret/current/asset.json').exists())

    def test_optional_current_metadata_and_profile_closure_are_not_forced_when_absent(self):
        with patch.object(characters, 'EXTRAS', []), patch.object(characters, 'SCOPES', []):
            self.assertEqual(characters.inventory_paths(self.root), [])
            unified.build(self.root)
            self.assertEqual(characters.inventory_paths(self.root), [unified.MASTER])
        with patch.object(characters, '_build_index_locked', return_value={'characters': [], 'source_collections': []}), \
                patch.object(characters, 'EXTRAS', []):
            required = characters._required_current_library_paths_locked(self.root, [])
            self.assertTrue(unified.required_paths(self.root) <= required)
            self.assertNotIn(unified.TOOL, required)
            helper = self.root/unified.TOOL
            helper.parent.mkdir(parents=True, exist_ok=True)
            helper.write_text('# optional helper fixture\n')
            self.assertIn(unified.TOOL, characters._required_current_library_paths_locked(self.root, []))


if __name__ == '__main__':
    unittest.main()
