"""A live new batch must not stale or conceal frozen portable-library art."""
from contextlib import ExitStack, contextmanager
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from PIL import Image

from tools import character_library as library
from tools import manage_character_assets as management


@contextmanager
def reject_writer_probes(active):
    """Use case-insensitive lexical boundaries, without resolving live paths."""
    prefixes = {os.path.abspath(active).casefold(),
                os.path.abspath(active.parent.resolve() / active.name).casefold()}
    def guarded(original):
        def call(path, *args, **kwargs):
            if not isinstance(path, int):
                value = os.path.abspath(os.fsdecode(path)).casefold()
                if any(value == prefix or value.startswith(prefix + os.sep) for prefix in prefixes):
                    raise AssertionError(f'Active writer path was probed by {original.__name__}: {path}')
            return original(path, *args, **kwargs)
        return call
    with ExitStack() as stack:
        for name in ('stat', 'open', 'resolve', 'is_symlink', 'is_file', 'is_dir'):
            stack.enter_context(patch.object(Path, name, guarded(getattr(Path, name))))
        for name in ('lstat', 'scandir'):
            stack.enter_context(patch.object(os, name, guarded(getattr(os, name))))
        yield


class AssetInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'catalogs').mkdir()
        self.live = 'assets/library/characters/kangaroo/generation-batches/task-a-unique'
        (self.root/self.live).mkdir(parents=True)
        self.frozen = self.root/'assets/library/characters/kangaroo/sources/v002/neutral.png'
        self.frozen.parent.mkdir(parents=True)
        self.frozen.write_bytes(b'unchanged original')
        self.write_config(self.live)

    def write_config(self, path):
        (self.root/library.MANAGEMENT).write_text(json.dumps({'schema_version':1,
            'batches':[], 'reservations':[{'id':'task-a', 'owner':'writer-a',
            'root':path, 'status':'active'}]}))

    def inventory(self):
        with patch.object(library,'SCOPES',['assets/library/characters']), patch.object(library,'EXTRAS',[]):
            return library.inventory_paths(self.root)

    def test_live_new_files_are_pending_and_frozen_files_remain_visible(self):
        before = self.inventory()
        (self.root/self.live/'still-generating.png').write_bytes(b'incomplete current output')
        self.assertEqual(self.inventory(),before)
        self.assertEqual(before,[self.frozen.relative_to(self.root).as_posix()])

    def test_case_alias_readable_source_rejected_before_any_probe(self):
        private = self.live + '/unfinished.json'
        (self.root / private).write_text('{private incomplete output')
        alias = private.replace('task-a-unique', 'TASK-A-UNIQUE')
        with reject_writer_probes(self.root / self.live):
            pending = library.pending_generation_roots(self.root)
            with self.assertRaisesRegex(ValueError, 'active generation tree'):
                library.readable_source(self.root, alias, pending)

    def test_readable_source_uses_normalized_parts_without_probing_a_raw_writer_segment(self):
        finished = self.root / self.live / '../finished.json'
        finished.write_text('{"finished": true}')
        with reject_writer_probes(self.root / self.live):
            pending = library.pending_generation_roots(self.root)
            path = library.readable_source(self.root, self.live + '/../finished.json', pending)
            self.assertEqual(json.loads(path.read_text()), {'finished': True})

    def test_reverse_case_reservation_prunes_inventory_before_any_probe(self):
        private = self.live + '/unfinished.png'
        (self.root / private).write_bytes(b'private incomplete output')
        alias = self.live.replace('task-a-unique', 'TASK-A-UNIQUE')
        self.write_config(alias)
        with reject_writer_probes(self.root / self.live), \
                patch.object(library, 'SCOPES', ['assets/library/characters', alias]), \
                patch.object(library, 'EXTRAS', [private]):
            paths = library.inventory_paths(self.root)
        self.assertEqual(paths, [self.frozen.relative_to(self.root).as_posix()])

    def test_case_alias_reservation_cannot_hide_frozen_inventory(self):
        relative = self.frozen.relative_to(self.root).as_posix()
        (self.root / library.FILES).write_text(json.dumps({'files': [{'path': relative}]}))
        batch = self.frozen.parent.relative_to(self.root).as_posix()
        self.write_config(batch.replace('v002', 'V002'))
        with reject_writer_probes(self.frozen.parent):
            with self.assertRaisesRegex(ValueError, 'cannot hide'):
                library.pending_generation_roots(self.root)

    def test_live_input_reference_symlink_remains_outside_frozen_inventory(self):
        (self.root/self.live/'identity-reference.png').symlink_to(self.frozen)
        self.assertEqual(self.inventory(),[self.frozen.relative_to(self.root).as_posix()])

    def test_reference_outside_a_live_tree_cannot_follow_its_unfinished_content(self):
        live_image = self.root/self.live/'unfinished.png'
        live_image.write_bytes(b'unfinished generated output')
        (self.frozen.parent/'live-reference.png').symlink_to(live_image)
        with self.assertRaisesRegex(ValueError, 'source file must not be a symlink'):
            self.inventory()

    def test_reservation_cannot_hide_existing_inventoried_source(self):
        relative = self.frozen.relative_to(self.root).as_posix()
        (self.root/library.FILES).write_text(json.dumps({'files':[{'path':relative}]}))
        self.write_config(self.frozen.parent.relative_to(self.root).as_posix())
        with self.assertRaisesRegex(ValueError,'cannot hide'):
            self.inventory()

    def test_released_batch_is_included_without_changing_frozen_source(self):
        image = self.root/self.live/'final.png'
        image.write_bytes(b'completed generated output')
        config = json.loads((self.root/library.MANAGEMENT).read_text())
        config['reservations'][0]['status']='released'
        (self.root/library.MANAGEMENT).write_text(json.dumps(config))
        self.assertIn(image.relative_to(self.root).as_posix(),self.inventory())
        self.assertEqual(self.frozen.read_bytes(),b'unchanged original')

    def test_escape_and_broad_character_reservations_are_rejected(self):
        for path in ['../outside','assets/library/characters']:
            self.write_config(path)
            with self.assertRaises(ValueError):
                self.inventory()

    def refresh_fixture(self):
        config = self.root / library.MANAGEMENT
        config.write_text(json.dumps({'schema_version': 1, 'batches': [], 'reservations': []}))
        index, files = self.root / library.INDEX, self.root / library.FILES
        index.write_text('{"previous":"index"}')
        files.write_text('{"files":[]}')
        return index, files

    def refresh_patches(self):
        return (patch.object(library, 'SCOPES', ['assets/library/characters']),
                patch.object(library, 'EXTRAS', [library.MANAGEMENT, library.INDEX]),
                patch.object(library, '_build_index_locked', return_value={'characters': []}))

    def build_source_fixture(self, selected=False):
        for relative in (library.MANAGEMENT, library.INDEX, library.FILES,
                         library.STOCK, library.MOTIONS, library.STYLE,
                         'neutral-manifest.json', 'metadata-registration.json'):
            path = self.root / relative
            if path.is_symlink():
                path.unlink()
        self.refresh_fixture()
        self.write_config(self.live)
        if self.frozen.is_symlink():
            self.frozen.unlink()
        Image.new('RGBA', (8, 10), (80, 100, 50, 255)).save(self.frozen)
        neutral = self.frozen.relative_to(self.root).as_posix()
        style = {'records': [{'id': 'kangaroo', 'path': neutral, 'sha256': library.sha(self.frozen),
            'body_bbox_px': [0, 0, 8, 10], 'anchor_px': [4, 10], 'height_px': 10}]}
        stock, motions = {'items': []}, {'items': []}
        if selected:
            library.write(self.root/'neutral-manifest.json', {})
            stock['items'].append({'id': 'kangaroo', 'source_version': 'v001',
                'source_manifest_path': 'neutral-manifest.json', 'source_manifest_sha256': library.sha(self.root/'neutral-manifest.json')})
            library.write(self.root/'metadata-registration.json', {'frames': [], 'common_reference_height_px': 10})
            motions['items'].append({'id': 'kangaroo', 'registration': 'metadata-registration.json',
                'registration_sha256': library.sha(self.root/'metadata-registration.json'),
                'preview': 'preview.png', 'motion_preview': 'motion.gif'})
        for relative, data in ((library.STOCK, stock), (library.MOTIONS, motions), (library.STYLE, style)):
            library.write(self.root/relative, data)
        return style, stock, motions

    def assert_build_rejects_before_any_live_read(self):
        live = (self.root/self.live).parent.resolve() / Path(self.live).name
        old_outputs = {path: path.read_bytes() for path in (self.root/library.INDEX, self.root/library.FILES)
                       if not path.is_symlink()}
        image_open, read = library.Image.open, library.read
        def guarded_image(path, *args, **kwargs):
            if Path(path).resolve().is_relative_to(live):
                self.fail('Image.open attempted to read active generation content')
            return image_open(path, *args, **kwargs)
        def guarded_read(path):
            if Path(path).resolve().is_relative_to(live):
                self.fail('JSON reader attempted to read active generation content')
            return read(path)
        with patch.object(library, 'NAMES', {'kangaroo': ('カンガルー', 'Kangaroo')}), \
                patch.object(library, 'SCOPES', ['assets/library/characters']), \
                patch.object(library, 'EXTRAS', [library.MANAGEMENT, library.INDEX, library.STOCK, library.MOTIONS, library.STYLE]), \
                patch.object(library.Image, 'open', side_effect=guarded_image), \
                patch.object(library, 'read', side_effect=guarded_read):
            with self.assertRaisesRegex(ValueError, 'active generation tree|must not contain a symlink'):
                library.refresh(self.root)
        for path, data in old_outputs.items():
            self.assertEqual(path.read_bytes(), data)
        self.assertEqual(list((self.root/'catalogs').glob('*.lock')), [])

    def test_build_rejects_live_neutral_and_neutral_alias_before_image_open(self):
        for alias in (False, True):
            with self.subTest(alias=alias):
                style, _, _ = self.build_source_fixture()
                unfinished = self.root/self.live/'unfinished.png'
                unfinished.write_bytes(b'private incomplete image')
                if alias:
                    self.frozen.unlink()
                    self.frozen.symlink_to(unfinished)
                else:
                    style['records'][0]['path'] = unfinished.relative_to(self.root).as_posix()
                    library.write(self.root/library.STYLE, style)
                self.assert_build_rejects_before_any_live_read()

    def test_build_rejects_case_alias_neutral_before_any_probe(self):
        style, _, _ = self.build_source_fixture()
        unfinished = self.root / self.live / 'unfinished.png'
        unfinished.write_bytes(b'private incomplete image')
        style['records'][0]['path'] = (self.live + '/unfinished.png').replace('task-a-unique', 'TASK-A-UNIQUE')
        library.write(self.root / library.STYLE, style)
        with reject_writer_probes(self.root / self.live):
            self.assert_build_rejects_before_any_live_read()

    def test_build_rejects_manifest_aliases_before_json_read(self):
        for relative in (library.STOCK, library.MOTIONS, library.STYLE):
            with self.subTest(manifest=relative):
                self.build_source_fixture()
                private = self.root/self.live/'private-manifest.json'
                private.write_text('{}')
                path = self.root/relative
                path.unlink()
                path.symlink_to(private)
                self.assert_build_rejects_before_any_live_read()

    def test_build_rejects_live_registration_and_alias_before_json_read(self):
        for alias in (False, True):
            with self.subTest(alias=alias):
                _, _, motions = self.build_source_fixture(selected=True)
                private = self.root/self.live/'private-registration.json'
                private.write_text('{"frames":[]}')
                if alias:
                    path = self.root/'metadata-registration.json'
                    path.unlink()
                    path.symlink_to(private)
                else:
                    motions['items'][0]['registration'] = private.relative_to(self.root).as_posix()
                    library.write(self.root/library.MOTIONS, motions)
                self.assert_build_rejects_before_any_live_read()

    def test_build_cannot_select_frames_from_a_live_registration_source(self):
        self.build_source_fixture(selected=True)
        library.write(self.root/'metadata-registration.json', {'source_sheet': self.frozen.relative_to(self.root).as_posix(),
            'common_reference_height_px': 10, 'frames': [{'id': 'blink',
                'path': self.live+'/unfinished.png', 'sha256': '0'*64, 'size_px': [8, 10],
                'anchor_px': [4, 10], 'body_bbox_px': [0, 0, 8, 10], 'tail_bbox_px': None, 'reference_height_px': 10}]})
        self.assert_build_rejects_before_any_live_read()

    def test_control_file_aliases_are_rejected_before_config_or_inventory_read(self):
        for relative in (library.MANAGEMENT, library.FILES):
            with self.subTest(control=relative):
                self.build_source_fixture()
                private = self.root/self.live/'private-control.json'
                private.write_text('{}')
                path = self.root/relative
                path.unlink()
                path.symlink_to(private)
                self.assert_build_rejects_before_any_live_read()

    def test_refresh_blocks_new_reservations_during_scan_and_publication(self):
        self.refresh_fixture()
        original_inventory, original_replace = library._inventory_paths_locked, library.os.replace
        observed = []
        def claim(phase):
            observed.append(phase)
            with self.assertRaisesRegex(ValueError, 'writer lock exists'):
                management.reserve(self.root, self.root / library.MANAGEMENT, self.live,
                                   'parallel-writer', 'claim-' + str(len(observed)))
        def enumerate_sources(root):
            result = original_inventory(root)
            claim('scan')
            return result
        def publish(source, target):
            claim('publish')
            return original_replace(source, target)
        scopes, extras, builder = self.refresh_patches()
        with scopes, extras, builder, patch.object(library, '_inventory_paths_locked', side_effect=enumerate_sources), \
                patch.object(library.os, 'replace', side_effect=publish):
            self.assertEqual(library.refresh(self.root)['status'], 'pass')
        self.assertEqual(observed, ['scan', 'scan', 'publish', 'publish'])
        management.reserve(self.root, self.root / library.MANAGEMENT, self.live, 'parallel-writer', 'after-publication')
        self.assertEqual(management.read_config(self.root, self.root / library.MANAGEMENT)[2][0]['id'], 'after-publication')

    @contextmanager
    def completed_library_fixture(self):
        self.build_source_fixture()
        self.refresh_fixture()
        with patch.object(library, 'NAMES', {'kangaroo': ('カンガルー', 'Kangaroo')}), \
                patch.object(library, 'SCOPES', ['assets/library/characters']), \
                patch.object(library, 'EXTRAS', [library.MANAGEMENT, library.INDEX,
                                               library.STOCK, library.MOTIONS, library.STYLE]):
            library.refresh(self.root)
            yield

    def test_optional_local_videos_do_not_change_portable_inventory_or_zip(self):
        with self.completed_library_fixture():
            videos = []
            for extension in sorted(library.LOCAL_VIDEO_EXTENSIONS):
                video = self.frozen.parent / ('historical-motion' + extension.upper())
                video.write_bytes(b'optional local video evidence')
                videos.append(video)
            audio = self.frozen.parent / 'source-audio.mp3'
            audio.write_bytes(b'published audio fixture')
            library.refresh(self.root)
            original_index = (self.root / library.INDEX).read_bytes()
            original_inventory = (self.root / library.FILES).read_bytes()
            with_videos = library.verify(self.root)
            first_zip = self.root / 'with-local-video.zip'
            library.export(self.root, first_zip)
            with zipfile.ZipFile(first_zip) as archive:
                first_members = {name: archive.read(name) for name in archive.namelist()}
            self.assertFalse(any(Path(name).suffix.lower() in library.LOCAL_VIDEO_EXTENSIONS
                                 for name in first_members))
            png_member = 'character-library/' + self.frozen.relative_to(self.root).as_posix()
            audio_member = 'character-library/' + audio.relative_to(self.root).as_posix()
            self.assertEqual(first_members[png_member], self.frozen.read_bytes())
            self.assertEqual(first_members[audio_member], audio.read_bytes())
            for video in videos:
                video.unlink()
            self.assertEqual(library.verify(self.root), with_videos)
            second_zip = self.root / 'without-local-video.zip'
            library.export(self.root, second_zip)
            with zipfile.ZipFile(second_zip) as archive:
                self.assertEqual({name: archive.read(name) for name in archive.namelist()}, first_members)
            library.refresh(self.root)
            self.assertEqual((self.root / library.INDEX).read_bytes(), original_index)
            self.assertEqual((self.root / library.FILES).read_bytes(), original_inventory)

    def test_optional_video_exclusion_preserves_required_png_hash_checks(self):
        with self.completed_library_fixture():
            video = self.frozen.parent / 'historical-motion.mp4'
            video.write_bytes(b'optional evidence')
            library.refresh(self.root)
            video.unlink()
            self.frozen.write_bytes(b'changed adopted PNG')
            with self.assertRaisesRegex(ValueError, 'Missing or changed library file'):
                library.verify(self.root)
            with self.assertRaisesRegex(ValueError, 'Missing or changed library file'):
                library.export(self.root, self.root / 'rejected.zip')
            self.assertFalse((self.root / 'rejected.zip').exists())

    def write_current_publication(self, paths=None):
        if paths is None:
            paths = [entry['path'] for entry in library.read(self.root / library.FILES)['files']]
        selected = sorted(set(paths) | {library.PUBLICATION})
        library.write(self.root / library.PUBLICATION, {
            'schema_version': 1, 'scope': 'current-only-nonvideo',
            'files': sorted(set(selected) | {library.FILES}),
            'character_library_files': selected,
        })

    def test_current_publication_keeps_adopted_v001_and_ignores_other_local_trials(self):
        self.frozen.unlink()
        self.frozen = self.root / 'assets/library/characters/kangaroo/sources/v001/neutral.png'
        self.frozen.parent.mkdir(parents=True)
        with self.completed_library_fixture():
            self.write_current_publication()
            library.refresh(self.root)
            original_inventory = (self.root / library.FILES).read_bytes()
            original_index = (self.root / library.INDEX).read_bytes()
            expected = library.verify(self.root)
            unselected = self.frozen.parent.parent / 'v999' / 'neutral.png'
            unselected.parent.mkdir()
            unselected.write_bytes(b'higher version is an unselected local trial')
            candidate = self.frozen.parent / 'candidates' / 'rejected.png'
            candidate.parent.mkdir()
            candidate.write_bytes(b'rejected trial inside current source folder')
            self.assertEqual(library.verify(self.root), expected)
            library.refresh(self.root)
            self.assertEqual((self.root / library.FILES).read_bytes(), original_inventory)
            self.assertEqual((self.root / library.INDEX).read_bytes(), original_index)
            self.assertEqual(library.read(self.root / library.INDEX)['characters'][0]['neutral']['path'],
                             self.frozen.relative_to(self.root).as_posix())
            output = self.root / 'current-only.zip'
            library.export(self.root, output)
            with zipfile.ZipFile(output) as archive:
                self.assertIn('character-library/' + library.PUBLICATION, archive.namelist())
                self.assertNotIn('character-library/' + unselected.relative_to(self.root).as_posix(), archive.namelist())
                self.assertNotIn('character-library/' + candidate.relative_to(self.root).as_posix(), archive.namelist())
                extracted = self.root / 'extracted'
                archive.extractall(extracted)
            self.assertEqual(library.verify(extracted / 'character-library'), expected)
            unselected.unlink()
            candidate.unlink()
            self.assertEqual(library.verify(self.root), expected)

    def test_current_publication_cannot_hide_an_adopted_neutral(self):
        with self.completed_library_fixture():
            paths = [entry['path'] for entry in library.read(self.root / library.FILES)['files']
                     if entry['path'] != self.frozen.relative_to(self.root).as_posix()]
            self.write_current_publication(paths)
            with self.assertRaisesRegex(ValueError, 'omits required adopted library source'):
                library.refresh(self.root)

    def test_current_publication_requires_registered_source_sheet(self):
        self.build_source_fixture(selected=True)
        source = self.root / 'current-source-sheet.png'
        source.write_bytes(self.frozen.read_bytes())
        registration_path = self.root / 'metadata-registration.json'
        registration = library.read(registration_path)
        registration.update(source_sheet=source.relative_to(self.root).as_posix(), source_sheet_sha256=library.sha(source))
        library.write(registration_path, registration)
        for relative in ('preview.png', 'motion.gif'):
            (self.root / relative).write_bytes(b'current preview fixture')
        with patch.object(library, 'NAMES', {'kangaroo': ('カンガルー', 'Kangaroo')}), \
                patch.object(library, 'SCOPES', ['assets/library/characters']), \
                patch.object(library, 'EXTRAS', [library.MANAGEMENT, library.INDEX, library.STOCK,
                                               library.MOTIONS, library.STYLE, 'neutral-manifest.json',
                                               'metadata-registration.json', 'preview.png', 'motion.gif']):
            paths = library.inventory_paths(self.root)
            self.write_current_publication(paths)
            with self.assertRaisesRegex(ValueError, 'omits required adopted library source: current-source-sheet.png'):
                library.inventory_paths(self.root)

    def test_current_publication_rejects_unsafe_video_and_candidate_paths(self):
        with self.completed_library_fixture():
            paths = [entry['path'] for entry in library.read(self.root / library.FILES)['files']]
            for bad, message in [('../outside.png', 'canonical and root-relative'),
                                 ('/outside.png', 'canonical and root-relative'),
                                 ('assets/library/local.MP4', 'Video media'),
                                 ('assets/library/characters/kangaroo/candidates/trial.png', 'Unselected candidate')]:
                with self.subTest(path=bad):
                    self.write_current_publication([*paths, bad])
                    with self.assertRaisesRegex(ValueError, message):
                        library.inventory_paths(self.root)

    def test_public_read_operations_block_reservations_through_the_last_source_read(self):
        with self.completed_library_fixture():
            attempted = []
            def attempt(phase):
                attempted.append(phase)
                with self.assertRaisesRegex(ValueError, 'writer lock exists'):
                    management.reserve(self.root, self.root / library.MANAGEMENT, self.live, 'parallel', 'racing-claim')
            original_pending, original_walk = library.pending_generation_roots, library.os.walk
            original_image, original_record = library.Image.open, management.file_record
            original_zip = library.zipfile.ZipFile.write
            def pending(*args):
                attempt('reservation-snapshot')
                return original_pending(*args)
            def walk(*args, **kwargs):
                attempt('walk')
                return original_walk(*args, **kwargs)
            def image(*args, **kwargs):
                attempt('image-read')
                return original_image(*args, **kwargs)
            def record(*args):
                attempt('file-read')
                return original_record(*args)
            def zip_write(archive, *args, **kwargs):
                attempt('zip-source-read')
                return original_zip(archive, *args, **kwargs)
            operations = [lambda: library.inventory_paths(self.root),
                          lambda: library.build_index(self.root),
                          lambda: library.snapshot_files(self.root, (self.root / library.INDEX).read_bytes()),
                          lambda: library.load_pose(self.root, 'kangaroo'),
                          lambda: library.verify_pose_registration(self.root, {'frames': []}, 'kangaroo'),
                          lambda: library.verify(self.root),
                          lambda: library.preview(self.root, 'kangaroo', 'neutral', 20, self.root / 'preview.png', 'transparent'),
                          lambda: library.export(self.root, self.root / 'bundle.zip')]
            with patch.object(library, 'pending_generation_roots', side_effect=pending), \
                    patch.object(library.os, 'walk', side_effect=walk), \
                    patch.object(library.Image, 'open', side_effect=image), \
                    patch.object(management, 'file_record', side_effect=record), \
                    patch.object(library.zipfile.ZipFile, 'write', new=zip_write):
                for operation in operations:
                    before = len(attempted)
                    self.assertIsNotNone(operation())
                    self.assertGreater(len(attempted), before)
            self.assertIn('zip-source-read', attempted)
            self.assertIn('image-read', attempted)
            self.assertEqual(library.read(self.root / library.MANAGEMENT)['reservations'], [])
            self.assertEqual(list((self.root / 'catalogs').glob('*.lock')), [])

    def test_existing_config_lock_is_not_stolen_by_library_readers(self):
        with self.completed_library_fixture():
            path = (self.root / library.MANAGEMENT).with_suffix('.json.lock')
            path.write_text('existing-owner')
            operations = [lambda: library.inventory_paths(self.root),
                          lambda: library.build_index(self.root),
                          lambda: library.snapshot_files(self.root, b'{}'),
                          lambda: library.load_pose(self.root, 'kangaroo'),
                          lambda: library.verify_pose_registration(self.root, {'frames': []}, 'kangaroo'),
                          lambda: library.verify(self.root),
                          lambda: library.preview(self.root, 'kangaroo', 'neutral', 20, self.root / 'blocked.png', 'transparent'),
                          lambda: library.export(self.root, self.root / 'blocked.zip'),
                          lambda: library.refresh(self.root)]
            with patch.object(library.Image, 'open', side_effect=AssertionError('Image read while locked')):
                for operation in operations:
                    with self.assertRaisesRegex(ValueError, 'writer lock exists'):
                        operation()
                    self.assertEqual(path.read_text(), 'existing-owner')
            self.assertFalse((self.root / 'blocked.png').exists())
            self.assertFalse((self.root / 'blocked.zip').exists())

    def test_load_and_preview_reject_active_case_aliases_before_source_probes(self):
        private = self.live + '/unfinished.png'
        (self.root / private).write_bytes(b'private unfinished source')
        alias = private.replace('task-a-unique', 'TASK-A-UNIQUE')
        library.write(self.root / library.INDEX, {'characters': [{'id': 'kangaroo', 'neutral': {
            'path': alias, 'image_region_px': [0, 0, 8, 10], 'anchor_px': [4, 10], 'reference_height_px': 10}}]})
        with reject_writer_probes(self.root / self.live):
            with self.assertRaisesRegex(ValueError, 'active generation tree'):
                library.load_pose(self.root, 'kangaroo')
            with self.assertRaisesRegex(ValueError, 'active generation tree'):
                library.preview(self.root, 'kangaroo', 'neutral', 20, self.root / 'preview.png', 'transparent')

    def test_direct_snapshot_rejects_extra_symlink_to_active_before_following(self):
        private = self.root / self.live / 'unfinished.json'
        private.write_text('{incomplete private output')
        alias = self.root / 'extra.json'
        alias.symlink_to(private)
        with reject_writer_probes(self.root / self.live), \
                patch.object(library, 'SCOPES', ['assets/library/characters']), \
                patch.object(library, 'EXTRAS', ['extra.json']):
            with self.assertRaisesRegex(ValueError, 'must not contain a symlink'):
                library.snapshot_files(self.root, b'{}')

    def test_refresh_does_not_overwrite_concurrent_control_edits(self):
        for name in (library.MANAGEMENT, library.INDEX, library.FILES):
            with self.subTest(control=name):
                index, files = self.refresh_fixture()
                before = {index: index.read_bytes(), files: files.read_bytes()}
                target = self.root / name
                parallel = json.loads(target.read_text())
                parallel['parallel-edit'] = True
                changed = json.dumps(parallel).encode()
                calls = 0
                def build(_root):
                    nonlocal calls
                    calls += 1
                    if calls == 2:
                        target.write_bytes(changed)
                    return {'characters': []}
                scopes, extras, _ = self.refresh_patches()
                with scopes, extras, patch.object(library, '_build_index_locked', side_effect=build):
                    with self.assertRaisesRegex(ValueError, 'Concurrent library/config edit'):
                        library.refresh(self.root)
                self.assertEqual(target.read_bytes(), changed)
                for path, data in before.items():
                    if path != target:
                        self.assertEqual(path.read_bytes(), data)

    def test_refresh_rejects_source_changes_between_scans(self):
        index, files = self.refresh_fixture()
        before = {index: index.read_bytes(), files: files.read_bytes()}
        original = library._snapshot_files_locked
        calls = 0
        def changing(root, payload):
            nonlocal calls
            result = original(root, payload)
            calls += 1
            if calls == 1:
                (self.frozen.parent / 'new-source.png').write_bytes(b'concurrent source addition')
            return result
        scopes, extras, builder = self.refresh_patches()
        with scopes, extras, builder, patch.object(library, '_snapshot_files_locked', side_effect=changing):
            with self.assertRaisesRegex(ValueError, 'sources changed during scan'):
                library.refresh(self.root)
        for path, data in before.items():
            self.assertEqual(path.read_bytes(), data)

    def test_refresh_prepares_complete_json_before_replacing_outputs(self):
        index, files = self.refresh_fixture()
        before = {index.resolve(): index.read_bytes(), files.resolve(): files.read_bytes()}
        original = library.os.replace
        published = []
        def replace(source, target):
            target = Path(target)
            self.assertEqual(target.read_bytes(), before[target])
            json.loads(Path(source).read_bytes())
            if not published:
                self.assertEqual(len(list(index.parent.glob('*.tmp-*'))), 2)
            published.append(target.name)
            return original(source, target)
        scopes, extras, builder = self.refresh_patches()
        with scopes, extras, builder, patch.object(library.os, 'replace', side_effect=replace):
            library.refresh(self.root)
        self.assertEqual(published, [index.name, files.name])
        self.assertEqual(list(index.parent.glob('*.tmp-*')), [])
        self.assertEqual(list(index.parent.glob('*.lock')), [])

    def test_failed_staging_leaves_previous_catalogs_and_no_temporary_files(self):
        index, files = self.refresh_fixture()
        before = {index: index.read_bytes(), files: files.read_bytes()}
        original = library.os.fsync
        calls = 0
        def fail_on_second(stream):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('Injected staging failure')
            return original(stream)
        scopes, extras, builder = self.refresh_patches()
        with scopes, extras, builder, patch.object(library.os, 'fsync', side_effect=fail_on_second):
            with self.assertRaisesRegex(OSError, 'Injected staging failure'):
                library.refresh(self.root)
        for path, data in before.items():
            self.assertEqual(path.read_bytes(), data)
        self.assertEqual(list(index.parent.glob('*.tmp-*')), [])
        self.assertEqual(list(index.parent.glob('*.lock')), [])

    def test_refresh_cannot_publish_through_a_catalog_symlink_to_art(self):
        index, _ = self.refresh_fixture()
        index.unlink()
        index.symlink_to(self.frozen)
        original = self.frozen.read_bytes()
        with self.assertRaisesRegex(ValueError, 'publication path must not contain a symlink'):
            library.refresh(self.root)
        self.assertEqual(self.frozen.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
