"""Verify the 0–200 revision: complete decimal narration, four-base values, timing and final AAC."""
from collections import Counter
import argparse
import json
from pathlib import Path
import re
import tempfile

from verify_octal_audio import find_ffmpeg, sample, sha256_file, source_references, verify_track


def words(text):
    return re.sub(r'[^a-z0-9]+', ' ', text.casefold()).strip()


def cardinal_value(text):
    """Parse English cardinal wording independently of the timeline builder."""
    small = dict(zip(('zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven',
                      'eight', 'nine', 'ten', 'eleven', 'twelve', 'thirteen', 'fourteen',
                      'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen'), range(20)))
    tens = dict(zip(('twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety'),
                    range(20, 100, 10)))

    def under_hundred(tokens):
        if len(tokens) == 1:
            return small.get(tokens[0], tens.get(tokens[0]))
        if len(tokens) == 2 and tokens[0] in tens and 1 <= small.get(tokens[1], -1) <= 9:
            return tens[tokens[0]] + small[tokens[1]]
        return None

    tokens = words(text).split()
    if len(tokens) >= 2 and tokens[1] == 'hundred' and 1 <= small.get(tokens[0], -1) <= 9:
        leading = small[tokens[0]] * 100
        if len(tokens) == 2:
            return leading
        tail = tokens[2:]
        if tail[0] == 'and':
            tail = tail[1:]
        remaining = under_hundred(tail)
        return leading + remaining if remaining is not None and remaining > 0 else None
    return under_hundred(tokens)


def validate_schedule(plan):
    assert sample(plan['duration_s']) >= sample(480), 'The requested final duration is at least eight minutes'
    assert plan['narration_base'] == 10
    assert plan['row_order'] == ['binary', 'decimal', 'octal', 'hexadecimal']
    assert set(plan['numeric_sources']) == {str(value) for value in range(201)}
    events = sorted(plan['events'], key=lambda row: row['start_s'])
    assert Counter(e['type'] for e in events) == {'number_voice': 202, 'dialogue': 13, 'sfx': 1}
    assert len({e['id'] for e in events}) == len(events)
    cursor = sample(.8)
    for e in events:
        start, end = sample(e['start_s']), sample(e['end_s'])
        assert cursor <= start < end <= sample(plan['duration_s']), e['id']
        cursor = end
    count = [e for e in events if e['type'] == 'number_voice' and e['phase'] == 'count']
    assert [e['decimal_value'] for e in count] == list(range(201))
    states = plan['counted_states']
    assert [e['decimal_value'] for e in states] == list(range(201))
    gaps = []
    for value, (event, state) in enumerate(zip(count, states, strict=True)):
        source = plan['numeric_sources'][str(value)]
        assert event['narration_base'] == 10
        assert cardinal_value(event['text']) == value, f'Wrong spoken number at {event["id"]}'
        assert cardinal_value(source['spoken_text']) == value, f'Wrong source number for {value}'
        assert cardinal_value(state['spoken_text']) == value, f'Wrong displayed reading for {value}'
        assert words(event['text']) == words(source['spoken_text'])
        assert event['source_path'] == state['source_path'] == source['path']
        assert event['source_sha256'] == state['source_sha256'] == source['sha256']
        assert sample(event['start_s']) == sample(state['estimated_display_start_s']) + sample(.12)
        assert sample(event['start_s']) == sample(state['estimated_voice_start_s'])
        assert sample(event['end_s']) == sample(state['estimated_voice_end_s'])
        assert sample(event['end_s'] - event['start_s']) == source['sample_frames'] * 2
        assert state['all_rows_update_together'] is True
        assert state['representations'] == {'binary': format(value, 'b'), 'decimal': str(value),
                                            'octal': format(value, 'o'), 'hexadecimal': format(value, 'X')}
        assert sample(state['estimated_display_end_s']) > sample(event['end_s'])
        if value < 200:
            assert sample(state['estimated_display_end_s']) == sample(states[value + 1]['estimated_display_start_s'])
        if value:
            gap = sample(event['start_s']) - sample(count[value - 1]['end_s'])
            assert gap == sample(5 if value - 1 in (8, 16, 64) else 2)
            gaps.append(gap)
    assert gaps.count(sample(2)) == 197 and gaps.count(sample(5)) == 3
    intro = [e for e in events if e['type'] == 'number_voice' and e['phase'] == 'intro']
    assert len(intro) == 1 and intro[0]['decimal_value'] == 10 and words(intro[0]['text']) == 'ten'
    follow = next(e for e in events if e['id'] == 'I04B')
    assert sample(follow['start_s']) - sample(intro[0]['end_s']) == sample(.30)
    assert sample(states[-1]['estimated_display_end_s']) - sample(count[-1]['end_s']) == sample(.28)
    assert states[-1]['decimal_value'] == 200 and cardinal_value(count[-1]['text']) == 200
    assert sample(states[-1]['estimated_display_end_s']) == sample(plan['finale']['estimated_start_s'])
    assert sample(plan['duration_s']) - sample(plan['finale']['estimated_start_s']) == sample(12)
    return events, {'counted_values': 201, 'four_base_representations_checked': 804,
                    'narration_base': 10, 'whole_number_voices': 201,
                    'ordinary_two_second_transitions': 197, 'teaching_five_second_transitions': 3,
                    'within_number_words_artificially_spaced': False,
                    'intro_ten_following_dialogue_gap_s': .30,
                    'independent_cardinal_meaning_checks': 603,
                    'canonical_representation_checks': 804,
                    'display_continuity_boundaries_checked': 200,
                    'final_value': 200, 'minimum_duration_s': 480}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeline', type=Path, required=True)
    parser.add_argument('--master', type=Path, required=True)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--ffmpeg')
    args = parser.parse_args()
    plan = json.loads(args.timeline.read_text(encoding='utf-8'))
    events, schedule = validate_schedule(plan)
    ffmpeg = find_ffmpeg(args.ffmpeg)
    with tempfile.TemporaryDirectory(prefix='fourbase-v002-audio-qa-', dir='D:/temp') as work:
        directory = Path(work)
        clips = source_references(events, ffmpeg, directory)
        master = verify_track(args.master, events, clips, sample(plan['duration_s']), ffmpeg, directory, lossy=False)
        encoded = verify_track(args.video, events, clips, sample(plan['duration_s']), ffmpeg, directory, lossy=True)
    report = {'passed': True, 'timeline_sha256': sha256_file(args.timeline),
              'schedule': schedule, 'master': master, 'encoded_audio': encoded}
    with args.out.open('x', encoding='utf-8') as out:
        json.dump(report, out, indent=2)
        out.write('\n')
    print(json.dumps({'passed': True, 'schedule': schedule,
                      'minimum_aac_speech_correlation': encoded['minimum_speech_correlation'],
                      'maximum_silent_interior_peak_pcm16': encoded['maximum_silent_interior_peak_pcm16']}))


if __name__ == '__main__':
    main()
