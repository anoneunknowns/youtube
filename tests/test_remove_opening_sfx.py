"""Keep speech and later SFX byte-identical when removing an isolated intro cue."""
import json
from pathlib import Path
import tempfile
import unittest
import wave
from tools.remove_opening_sfx import data_region, remove_opening_sfx


class OpeningSoundTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir='D:/temp' if Path('D:/temp').is_dir() else None)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.master, self.timeline, self.output = (self.root / name for name in ['master.wav', 'timeline.json', 'edited.wav'])
        pcm = bytearray(96000 * 6)
        pcm[4800 * 6:24000 * 6] = b'\x00\x20\x00' * (19200 * 2)
        pcm[48000 * 6:60000 * 6] = b'\x00\x40\x00' * (12000 * 2)
        with wave.open(str(self.master), 'wb') as target:
            target.setparams((2, 3, 48000, 0, 'NONE', 'not compressed'))
            target.writeframes(pcm)
        self.events = [dict(kind='sfx', source='intro', id='SE_WIND', start_s=.1, end_s=.5),
                       dict(kind='speech', source='intro', start_s=1, end_s=1.25)]

    def run_edit(self):
        self.timeline.write_text(json.dumps({'events': self.events}), encoding='utf-8')
        return remove_opening_sfx(self.master, self.timeline, self.output)

    def test_removes_only_sound_and_preserves_header_speech_and_later_samples(self):
        receipt = self.run_edit()
        offset, _ = data_region(self.master)
        original, changed = self.master.read_bytes(), self.output.read_bytes()
        self.assertNotEqual(original, changed)
        self.assertEqual(original[:offset], changed[:offset])
        self.assertEqual(changed[offset:offset + 144000], bytes(144000))
        self.assertEqual(original[offset + 144000:], changed[offset + 144000:])
        self.assertTrue(all(receipt['verification'].values()))

    def test_refuses_window_overlapping_another_audio_event(self):
        self.events[1]['start_s'] = .4
        with self.assertRaises(ValueError):
            self.run_edit()
        self.assertFalse(self.output.exists())

    def test_refuses_to_silence_a_speech_first_timeline(self):
        self.events = self.events[1:]
        with self.assertRaises(ValueError):
            self.run_edit()
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
