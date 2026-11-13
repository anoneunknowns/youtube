"""Closed selections preserve all untouched poses and inherited canonical choices."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

from tests import test_character_adoptions as fixtures
from tools import character_library as library, unified_asset_library as unified


class PartialPoseSelectionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CharacterAdoptionTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.old_neutral = self.fixture.old_bear
        self.cream = self.fixture.neutral('cream-companion', 'v001', (32, 48), [8, 6, 24, 42], 'cornsilk')
        self.expanded_names = ['neutral', 'think', *[f'pose_{n:02}' for n in range(25)]]
        self.app_names = ['neutral', 'success_air', *[f'pose_{n:02}' for n in range(14)]]
        self.old_expanded = self.registration('bear-beret', 'base-expanded', self.old_neutral,
                                               self.expanded_names, expanded=True)
        self.old_app = self.registration('cream-companion', 'base-app', self.cream,
                                          self.app_names, expanded=False)
        self.fixture.write(library.EXPANSION, {'status': 'stocked-and-assistant-reviewed', 'items': [{
            'id': 'bear-beret', 'registration': self.old_expanded,
            'registration_sha256': self.fixture.sha(self.old_expanded),
            'preview': self.old_neutral['path'], 'motion_preview': self.old_neutral['path']}]})
        self.fixture.write(library.SUPPLEMENT, {'schema_version': 1,
            'status': 'stocked-and-assistant-reviewed',
            'review_evidence': [{'path': self.fixture.evidence, 'sha256': self.fixture.sha(self.fixture.evidence)}],
            'items': [{'id': 'cream-companion', 'name_ja': 'クリーム', 'name_en': 'Cream',
                       'neutral': self.cream, 'pose_sets': [{'namespace': 'app',
                       'registration': self.old_app, 'registration_sha256': self.fixture.sha(self.old_app)}]}]})
        for key, value in [('SCOPES', ['assets/library/characters', 'assets/library/collections']),
                           ('EXTRAS', [library.MANAGEMENT, library.INDEX, library.STOCK,
                            library.MOTIONS, library.STYLE, library.EYECATCHES,
                            library.EXPANSION, library.SUPPLEMENT])]:
            patched = patch.object(library, key, value)
            patched.start()
            self.addCleanup(patched.stop)
        self.before = library.build_index(self.root)
        self.expanded = self.mix('bear-beret', self.old_expanded, 'think', self.old_neutral, expanded=True)
        self.app = self.mix('cream-companion', self.old_app, 'success_air', self.cream, expanded=False)
        self.entries = [
            {'id': 'bear-beret', 'status': 'adopted', 'expanded': self.expanded,
             'selection_evidence': [{'path': self.fixture.evidence, 'sha256': self.fixture.sha(self.fixture.evidence)}]},
            {'id': 'cream-companion', 'status': 'adopted', 'pose_set_selections': [self.app],
             'selection_evidence': [{'path': self.fixture.evidence, 'sha256': self.fixture.sha(self.fixture.evidence)}]}]

    def registration(self, identity, batch, canonical, names, *, expanded):
        prefix = f'assets/library/characters/{identity}/generation-batches/{batch}/'
        frames, sheets = [], []
        for n, name in enumerate(names):
            path = prefix + name + '.png'
            image = Image.new('RGBA', (32, 48))
            ImageDraw.Draw(image).ellipse((8, 6, 23, 41), fill='gold' if n % 2 else 'orange')
            dest = self.root/path
            dest.parent.mkdir(parents=True, exist_ok=True)
            image.save(dest)
            checksum = self.fixture.sha(path)
            sheet = {'id': name, 'source_sheet': path, 'source_sheet_sha256': checksum,
                     'reference_height_px': 36}
            sheets.append(sheet)
            frames.append({'id': name, 'path': path, 'sha256': checksum, 'size_px': [32, 48],
                'sheet_id': name, **{k: sheet[k] for k in ('source_sheet', 'source_sheet_sha256')},
                'crop_from_sheet_xyxy': [0, 0, 32, 48], 'body_bbox_px': [8, 6, 24, 42],
                'anchor_px': [16, 42], 'tail_bbox_px': None, 'reference_height_px': 36,
                'support_kind': 'anatomical-support'})
        relative = prefix+'registration.json'
        self.fixture.write(relative, {'schema_version': 2 if expanded else 1,
            'kind': ('generated-character-multisheet-key-pose-stock' if expanded
                     else 'app-character-native-pose-registration'),
            'character_id': identity, 'version': 'v002' if expanded else 'v001',
            'status': ('stocked-and-assistant-reviewed' if expanded
                       else 'candidate-prepared; visual-review-and-manager-adoption-required'),
            'canonical_neutral': deepcopy(canonical) if expanded else {k: canonical[k] for k in ('path', 'sha256')},
            'sheets': sheets, 'frames': frames, 'scale_policy': 'shared source-sheet scale',
            'clips': {'test': ['neutral', names[1], names[-1], 'neutral']}})
        return relative

    def mix(self, identity, base_path, target, canonical, *, expanded):
        old = library.read(self.root/base_path)
        new = deepcopy(old)
        version = 'v003' if expanded else 'v002'
        prefix = f'assets/library/characters/{identity}/generation-batches/selected-mix/'
        path = prefix+target+'.png'
        image = Image.new('RGBA', (64, 96))
        ImageDraw.Draw(image).ellipse((16, 12, 47, 83), fill='purple')
        dest = self.root/path
        dest.parent.mkdir(parents=True, exist_ok=True)
        image.save(dest)
        checksum = self.fixture.sha(path)
        sheet = {'id': 'replacement', 'source_sheet': path, 'source_sheet_sha256': checksum,
                 'reference_height_px': 72}
        new['sheets'].append(sheet)
        frame = next(frame for frame in new['frames'] if frame['id'] == target)
        previous = {k: frame[k] for k in ('path', 'sha256')}
        frame.update(path=path, sha256=checksum, size_px=[64, 96], sheet_id='replacement',
                     source_sheet=path, source_sheet_sha256=checksum,
                     crop_from_sheet_xyxy=[0, 0, 64, 96], body_bbox_px=[16, 12, 48, 84],
                     anchor_px=[32, 84], reference_height_px=72)
        new.update(version=version, status='stocked-and-assistant-reviewed')
        relative = prefix+'registration.json'
        self.fixture.write(relative, new)
        selected = {'version': version, 'registration': relative,
            'registration_sha256': self.fixture.sha(relative), 'base_registration': base_path,
            'base_registration_sha256': self.fixture.sha(base_path),
            'canonical_neutral': {k: canonical[k] for k in ('path', 'sha256')},
            'replacements': {target: previous}}
        if expanded:
            selected.update(preview=canonical['path'], motion_preview=canonical['path'])
        else:
            selected['namespace'] = 'app'
        return selected

    def configure(self, entries=None):
        self.fixture.write(library.ADOPTIONS, {'schema_version': 1,
            'kind': 'explicit-character-adoptions', 'adoptions': self.entries if entries is None else entries})

    def change(self, selected, mutate):
        document = library.read(self.root/selected['registration'])
        mutate(document)
        self.fixture.write(selected['registration'], document)
        selected['registration_sha256'] = self.fixture.sha(selected['registration'])

    @staticmethod
    def by_id(index):
        return {item['id']: item for item in index['characters']}

    def test_both_selections_preserve_inherited_neutral_eye_other_26_15_and_history(self):
        historical = {p.relative_to(self.root).as_posix(): p.read_bytes()
                      for p in self.root.rglob('*') if p.is_file()}
        self.configure()
        after = self.by_id(library.build_index(self.root))
        before = self.by_id(self.before)
        self.assertEqual(before['rabbit-beret'], after['rabbit-beret'])
        for identity, target in [('bear-beret', 'think'), ('cream-companion', 'success_air')]:
            self.assertEqual(before[identity]['neutral'], after[identity]['neutral'])
            if identity == 'bear-beret':
                self.assertEqual(before[identity]['eyecatch_key_poses'], after[identity]['eyecatch_key_poses'])
                self.assertEqual(before[identity]['eyecatch_collection'], after[identity]['eyecatch_collection'])
                old, new = [x[identity]['expanded_key_poses'] for x in (before, after)]
                self.assertEqual(len(new['poses']), 27)
            else:
                old, new = [x[identity]['pose_sets'][0] for x in (before, after)]
                self.assertEqual(len(new['poses']), 16)
                self.assertEqual(old['clips'], new['clips'])
            self.assertEqual(set(old['poses']), set(new['poses']))
            for name in old['poses']:
                if name != target:
                    self.assertEqual(old['poses'][name], new['poses'][name])
                else:
                    self.assertNotEqual(old['poses'][name]['sha256'], new['poses'][name]['sha256'])
        for relative, data in historical.items():
            self.assertEqual((self.root/relative).read_bytes(), data)

    def test_full_adoption_retains_canonical_eye_neutral_strictness(self):
        bad = deepcopy(self.fixture.entry)
        registration = library.read(self.root/bad['eyecatch']['registration'])
        registration['frames'][0]['anchor_px'] = [23, 52]
        self.fixture.write(bad['eyecatch']['registration'], registration)
        bad['eyecatch']['registration_sha256'] = self.fixture.sha(bad['eyecatch']['registration'])
        self.configure([bad])
        with self.assertRaisesRegex(ValueError, 'neutral frame geometry differs'):
            library.build_index(self.root)

    def test_partial_entry_is_closed_known_adopted_unique_and_nonempty(self):
        variants = [[dict(self.entries[0], id='unknown')], [self.entries[0], self.entries[0]],
                    [dict(self.entries[1], status='candidate')],
                    [{'id': 'bear-beret', 'status': 'adopted', 'selection_evidence': self.entries[0]['selection_evidence']}],
                    [dict(self.entries[1], pose_set_selections=[])],
                    [dict(self.entries[1], pose_set_overrides=[])],
                    [dict(self.entries[1], neutral=self.cream)],
                    [dict(self.entries[1], pose_set_selections=[self.app, self.app])]]
        for entries in variants:
            with self.subTest(entries=entries):
                self.configure(entries)
                with self.assertRaises(ValueError):
                    library.build_index(self.root)

    def test_selection_binds_base_canonical_old_target_and_exact_namespace(self):
        for entry_index, field in [(0, 'expanded'), (1, 'pose_set_selections')]:
            variants = [lambda s: s.update(base_registration_sha256='0'*64),
                        lambda s: s.update(canonical_neutral={'path': self.fixture.rabbit['path'], 'sha256': self.fixture.rabbit['sha256']}),
                        lambda s: next(iter(s['replacements'].values())).update(sha256='0'*64),
                        lambda s: s['replacements'].update(neutral={k: self.old_neutral[k] for k in ('path', 'sha256')})]
            if entry_index == 1:
                variants += [lambda s: s.update(namespace='unknown'), lambda s: s.update(namespace='expanded')]
            for change in variants:
                entries = deepcopy(self.entries)
                selected = entries[entry_index][field]
                change(selected if entry_index == 0 else selected[0])
                self.configure(entries)
                with self.subTest(entry=entry_index, change=change), self.assertRaises(ValueError):
                    library.build_index(self.root)

    def test_mix_rejects_other_pose_sheet_clip_coverage_and_undeclared_changes(self):
        original = library.read(self.root/self.expanded['registration'])
        variants = [lambda d: d['frames'][2].update(anchor_px=[17, 42]),
                    lambda d: d['sheets'][0].update(reference_height_px=37),
                    lambda d: d['frames'].pop(),
                    lambda d: d['frames'].append(deepcopy(d['frames'][0])),
                    lambda d: d.update(clips={'test': ['neutral']}),
                    lambda d: d.update(scale_policy='new-policy'),
                    lambda d: d['sheets'].append(dict(d['sheets'][-1], id='unused')),
                    lambda d: d.update(status='candidate'),
                    lambda d: d.update(registration_candidate_only=True),
                    lambda d: d.update(current_adoption=False),
                    lambda d: d.update(character_id='rabbit-beret'),
                    lambda d: d.update(kind='generated-character-eyecatch-key-pose-stock')]
        for change in variants:
            self.fixture.write(self.expanded['registration'], original)
            self.change(self.expanded, change)
            self.configure()
            with self.subTest(change=change), self.assertRaises(ValueError):
                library.build_index(self.root)

    def test_live_writer_and_source_mutation_are_rejected_on_build_and_load(self):
        self.configure()
        self.fixture.write(library.INDEX, library.build_index(self.root))
        self.fixture.write(library.MANAGEMENT, {'schema_version': 1, 'batches': [], 'reservations': [{
            'id': 'writer', 'owner': 'test', 'status': 'active', 'root': str(Path(self.app['registration']).parent)}]})
        with self.assertRaisesRegex(ValueError, 'active generation tree'):
            library.load_pose(self.root, 'cream-companion', 'app/success_air')
        self.fixture.write(library.MANAGEMENT, {'schema_version': 1, 'batches': [], 'reservations': []})
        path = self.root/next(f for f in library.read(self.root/self.app['registration'])['frames'] if f['id']=='success_air')['path']
        with Image.open(path) as image:
            changed = image.copy()
        changed.putpixel((30, 30), (0, 0, 0, 255))
        changed.save(path)
        for operation in [lambda: library.build_index(self.root),
                          lambda: library.load_pose(self.root, 'cream-companion', 'app/success_air')]:
            with self.assertRaises(ValueError):
                operation()

    def test_stale_index_selection_geometry_or_removed_adoption_cannot_load(self):
        self.configure()
        index = library.build_index(self.root)
        for identity, pose in [('bear-beret', 'expanded/think'), ('cream-companion', 'app/success_air')]:
            self.fixture.write(library.INDEX, index)
            image, anchor, height = library.load_pose(self.root, identity, pose)
            self.assertEqual((image.size, height), ((64, 96), 72))
            changed = deepcopy(index)
            item = self.by_id(changed)[identity]
            block = item['expanded_key_poses'] if identity == 'bear-beret' else item['pose_sets'][0]
            block['poses'][pose.split('/')[1]]['anchor_px'] = [33, 84]
            self.fixture.write(library.INDEX, changed)
            with self.assertRaises(ValueError):
                library.load_pose(self.root, identity, pose)
            self.fixture.write(library.INDEX, index)
            self.configure([])
            with self.assertRaisesRegex(ValueError, 'no longer adopted'):
                library.load_pose(self.root, identity, pose)
            self.configure()

    def test_unchanged_namespaces_skip_full_native_validation_but_dispatch_detects_changes(self):
        rabbit_registration = self.registration('rabbit-beret', 'base-expanded-rabbit', self.fixture.rabbit,
                                                 self.expanded_names, expanded=True)
        expansion = library.read(self.root/library.EXPANSION)
        expansion['items'].append({'id': 'rabbit-beret', 'registration': rabbit_registration,
            'registration_sha256': self.fixture.sha(rabbit_registration),
            'preview': self.fixture.rabbit['path'], 'motion_preview': self.fixture.rabbit['path']})
        self.fixture.write(library.EXPANSION, expansion)
        supplement = library.read(self.root/library.SUPPLEMENT)
        supplement['items'][0]['pose_sets'].append({'namespace': 'idle-extra',
            'registration': self.old_app, 'registration_sha256': self.fixture.sha(self.old_app)})
        self.fixture.write(library.SUPPLEMENT, supplement)
        before = library.build_index(self.root)
        self.configure()
        self.fixture.write(library.INDEX, library.build_index(self.root))
        with patch.object(library, '_read_adoptions_locked', side_effect=AssertionError('Unrelated native decode')) as full:
            self.assertEqual(library.load_pose(self.root, 'rabbit-beret', 'expanded/think')[0].size, (32, 48))
            self.assertEqual(library.load_pose(self.root, 'cream-companion', 'idle-extra/success_air')[0].size, (32, 48))
            self.assertEqual(full.call_count, 0)
        self.configure([])
        self.fixture.write(library.INDEX, before)
        with patch.object(library, '_read_adoptions_locked', side_effect=AssertionError('Unrelated native decode')) as full:
            self.assertEqual(library.load_pose(self.root, 'bear-beret', 'expanded/think')[0].size, (32, 48))
            self.assertEqual(library.load_pose(self.root, 'cream-companion', 'app/success_air')[0].size, (32, 48))
            self.assertEqual(full.call_count, 0)
            self.configure()
            for identity, pose in [('bear-beret', 'expanded/think'), ('cream-companion', 'app/success_air')]:
                with self.assertRaisesRegex(ValueError, 'index binding'):
                    library.load_pose(self.root, identity, pose)
            self.configure([self.entries[0], self.entries[0]])
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                library.load_pose(self.root, 'cream-companion', 'app/success_air')
            self.assertEqual(full.call_count, 0)

    def test_current_aliases_change_exactly_two_pngs_and_public_closure_retains_bases(self):
        library.refresh(self.root)
        unified.build(self.root)
        before = {p.relative_to(self.root).as_posix(): p.read_bytes()
                  for p in self.root.glob('assets/library/characters/*/current/**/*.png')}
        self.configure()
        library.refresh(self.root)
        for identity in ['bear-beret', 'cream-companion']:
            shutil.rmtree(self.root/f'assets/library/characters/{identity}/current')
        unified.build(self.root)
        self.assertEqual(unified.verify(self.root)['assets'], 3)
        after = {p.relative_to(self.root).as_posix(): p.read_bytes()
                 for p in self.root.glob('assets/library/characters/*/current/**/*.png')}
        self.assertEqual(set(before), set(after))
        self.assertEqual({p for p in before if before[p] != after[p]}, {
            'assets/library/characters/bear-beret/current/poses/expanded/think.png',
            'assets/library/characters/cream-companion/current/poses/app/success_air.png'})
        required = library._required_current_library_paths_locked(self.root, [])
        for selected in (self.expanded, self.app):
            for path in [selected['registration'], selected['base_registration'],
                         *[r['path'] for r in selected['replacements'].values()]]:
                self.assertIn(path, required)
        library.refresh(self.root)
        self.assertEqual(library.verify(self.root)['characters'], 3)
        required.remove(self.old_app)
        self.fixture.write(library.PUBLICATION, {'schema_version': 1, 'scope': 'current-only-nonvideo',
            'files': sorted(required), 'character_library_files': sorted(required)})
        with self.assertRaisesRegex(ValueError, 'required adopted library source'):
            library.inventory_paths(self.root)


if __name__ == '__main__':
    unittest.main()
