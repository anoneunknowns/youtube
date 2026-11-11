"""Recalculate and verify Fibonacci preproduction data without replacing originals.

The episode's checked-in narration.json is the authored English/Japanese source;
the three prose documents are editorial templates. This tool derives the integer
table, estimates and full script from those sources. Default/--check is read-only.
--out-dir requires a new directory; --qa-dir refuses existing report filenames.
No audio, image assets, global catalogs or production videos are written.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / 'design/fibonacci-counting-v1'
FILES = ('count-lines.json', 'narration.json', 'concept-and-scenario.txt',
         'script-and-sound-cues.txt', 'background-concepts.txt',
         'timing-plan.json', 'README.txt')
BASE_WPM = 150
CHECKPOINTS = (2, 8, 13, 18, 26, 39)
OEIS_TERMS = (
    0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987,
    1597, 2584, 4181, 6765, 10946, 17711, 28657, 46368, 75025, 121393,
    196418, 317811, 514229, 832040, 1346269, 2178309, 3524578, 5702887,
    9227465, 14930352, 24157817, 39088169, 63245986, 102334155,
)
ONES = ('zero one two three four five six seven eight nine ten eleven twelve '
        'thirteen fourteen fifteen sixteen seventeen eighteen nineteen').split()
TENS = ('', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy',
        'eighty', 'ninety')


def words(n):
    if not isinstance(n, int) or not 0 <= n < 1_000_000_000:
        raise ValueError('Expected a nonnegative integer below one billion')
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ('-' + ONES[n % 10] if n % 10 else '')
    if n < 1000:
        return ONES[n // 100] + ' hundred' + (' ' + words(n % 100) if n % 100 else '')
    for divisor, unit in ((1_000_000, 'million'), (1000, 'thousand')):
        if n >= divisor:
            return words(n // divisor) + ' ' + unit + (' ' + words(n % divisor) if n % divisor else '')
    raise ValueError(n)


def parse_cardinal(text):
    """Independent word-to-integer path; no use of the formatter's recursion."""
    small = dict(zip(ONES, range(20)))
    small.update(zip(TENS[2:], range(20, 100, 10)))
    total = group = 0
    for token in text.replace('-', ' ').split():
        if token in small:
            group += small[token]
        elif token == 'hundred':
            group *= 100
        elif token in ('thousand', 'million'):
            total += group * {'thousand': 1000, 'million': 1_000_000}[token]
            group = 0
        else:
            raise ValueError(f'Unexpected English cardinal token: {token}')
    return total + group


def word_count(text):
    return len(re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", text.replace('-', ' ')))


def sequence():
    values = [0, 1]
    for _ in range(39):
        values.append(values[-2] + values[-1])
    return values


def count_lines():
    values = sequence()
    rows = []
    for n, value in enumerate(values):
        a, b = (values[n - 2], values[n - 1]) if n >= 2 else (None, None)
        rows.append({
            'id': f'N{n:03}', 'index': n, 'ordinal': n + 1, 'value': value,
            'display_value': f'{value:,}', 'text': words(value), 'a': a, 'b': b,
            'a_index': n - 2 if n >= 2 else None,
            'b_index': n - 1 if n >= 2 else None,
            'a_text': words(a) if a is not None else None,
            'b_text': words(b) if b is not None else None,
            'equation_text': f'{a:,} + {b:,} = {value:,}' if n >= 2 else None,
            'formula_prefix_text': words(a) + ' plus ' + words(b) + ' equals' if n >= 2 else None,
            'formula_narration_id': f'E{n:03}' if n >= 2 else None,
            'count_narration_id': f'N{n:03}', 'is_seed': n < 2,
            'result_spoken_only_in_count_event': True,
            'equation_layout_mode': ('short' if n <= 20 else 'wide') if n >= 2 else 'seed',
            'equation_font_size_px': (88 if n <= 20 else 47) if n >= 2 else None,
            'main_result_font_size_px': (126 if n <= 20 else 112) if n >= 2 else None,
        })
    return rows


def retime(authored):
    rows = json.loads(json.dumps(authored, ensure_ascii=False))
    cursor = .8
    for i, row in enumerate(rows):
        duration = word_count(row['text']) * 60 / BASE_WPM
        row.update(word_count_for_estimate=word_count(row['text']),
                   planning_window_seconds=[round(cursor, 3), round(cursor + duration, 3)],
                   time_reference='episode_start_estimate_at_150_wpm',
                   timing_status='provisional_not_audio_measured')
        cursor += duration
        kind = row['kind']
        if kind in ('intro', 'outro'):
            cursor += .6
        elif kind == 'formula_prefix':
            cursor += .16
        elif kind == 'count':
            cursor += .6 if row['index'] in CHECKPOINTS or row['index'] == 40 else 2
        elif kind == 'explanation':
            cursor += .6
            if i + 1 < len(rows) and rows[i + 1]['kind'] != 'explanation':
                cursor += 2
        else:
            raise ValueError(f'Unknown narration kind: {kind}')
    cursor += 1.4
    total = sum(row['word_count_for_estimate'] for row in rows)
    fixed = round(cursor - total * 60 / BASE_WPM, 3)
    return rows, fixed


def script_text(rows, narration, plan):
    text = '''Num-Num Numbers — Fibonacci Numbers
英語台本・日本語訳・編集キュー v001（前工程案）

F₀=0、F₁=1。n≥2でFₙ=Fₙ₋₂+Fₙ₋₁。F₀〜F₄₀の41項、39回の加算。
キャラクターはユーザー指定のシャム猫。背景第一案は「雲の上の風の郵便局」。
音声未生成・未実測。以下の編集枠は150語/分による仮の動画開始からの相対秒。
自然な米国英語。数詞にandを入れない。式前半Eは結果を含まず、結果Nで数詞を一度だけ読む。
前半末尾equalsから結果発話まで0.16秒を仮置きし、結果はNの0.12秒前に表示する。
通常境界は結果Nの終わり→次の式Eの開始2.00秒。数詞単体N→Nが2秒という仕様ではない。
チェックポイントではREPLAYとして説明し、読み終えた項の進捗を二重に増やさない。
式はOLDER / NEWER / NEWの横三列の数値窓。F₂₁から同一47pxの9桁対応モードへ一度切替。
下に大きい結果と同一32px・最大2行の英語読みを置く。導入では最終値を先出ししない。

'''
    for row in narration:
        start, end = row['planning_window_seconds']
        text += (f"{row['id']} | {start:.3f}–{end:.3f}s（仮） | {row['scene_id']}\n"
                 f"EN: {row['text']}\nJA: {row['translation_ja']}\n"
                 f"画面: {row['visual_cue_ja']}\n\n")
    text += '全項対応表（式の表示結果はここで確認できる。音声Eは結果を含まない）\n'
    for row in rows:
        text += (f"F_{row['index']} | 通算{row['ordinal']}/41 | {row['display_value']} | "
                 f"{row['text']} | {row['equation_text'] or 'INITIAL VALUE'}\n")
    low, high = plan['rough_duration_estimate_seconds']
    text += (f"\n概算総語数{plan['word_count']['total']}、固定遷移"
             f"{plan['estimated_fixed_transition_seconds']:.2f}秒、130〜150語/分で"
             f"約{low / 60:.2f}〜{high / 60:.2f}分。詳細と未実施項目はtiming-plan.json。\n")
    return text


def build_bundle(source):
    counts = count_lines()
    narration, fixed = retime(json.loads((source / 'narration.json').read_text()))
    plan = json.loads((source / 'timing-plan.json').read_text())
    main = sum(r['word_count_for_estimate'] for r in narration
               if r['kind'] in ('formula_prefix', 'count'))
    total = sum(r['word_count_for_estimate'] for r in narration)
    durations = [round(total * 60 / wpm + fixed, 3) for wpm in (150, 130)]
    plan.update(word_count={'formula_prefixes_and_results': main,
                            'intro_explanations_outro': total - main, 'total': total},
                estimated_fixed_transition_seconds=fixed,
                duration_formula_seconds=f'S_all_adopted_utterances + {fixed:.3f}; replace provisional speech windows using measured PCM, then revise editorial fit',
                rough_duration_estimate_seconds=durations,
                rough_duration_estimate_minutes=[round(d / 60, 2) for d in durations],
                minimum_at_fast_estimate_met=durations[0] >= 480)
    bundle = {name: (source / name).read_text() for name in FILES}
    for name, value in (('count-lines.json', counts), ('narration.json', narration),
                        ('timing-plan.json', plan)):
        bundle[name] = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    bundle['script-and-sound-cues.txt'] = script_text(counts, narration, plan)
    summary = (f"  現台本は全{len(narration)}発話、概算{total}語。130〜150語/分と"
               f"固定遷移{fixed:.2f}秒で約{durations[0] / 60:.2f}〜{durations[1] / 60:.2f}分。")
    bundle['concept-and-scenario.txt'] = re.sub(
        r'^  現台本は全.*$', summary, bundle['concept-and-scenario.txt'], flags=re.M)
    bundle['README.txt'] = re.sub(
        r'^概算:.*$',
        f'概算: {total}語、固定遷移{fixed:.2f}秒、130〜150語/分で{durations[0] / 60:.2f}〜{durations[1] / 60:.2f}分。',
        bundle['README.txt'], flags=re.M)
    return bundle


def carry_trace(a, b):
    carry = 0
    result = []
    for position in range(max(len(str(a)), len(str(b)))):
        digit_a, digit_b = a // 10 ** position % 10, b // 10 ** position % 10
        summed = digit_a + digit_b + carry
        result.append({'power_of_ten': position, 'a_digit': digit_a, 'b_digit': digit_b,
                       'carry_in': carry, 'column_sum': summed,
                       'result_digit': summed % 10, 'carry_out': summed // 10})
        carry = summed // 10
    reconstructed = sum(r['result_digit'] * 10 ** r['power_of_ten'] for r in result)
    reconstructed += carry * 10 ** len(result)
    assert reconstructed == a + b
    return {'a': a, 'b': b, 'result': reconstructed, 'columns': result,
            'new_leading_carry': carry, 'passed': True}


def verify(source, bundle):
    failures = []
    checks = []

    def check(name, passed):
        checks.append({'name': name, 'passed': bool(passed)})
        if not passed:
            failures.append(name)

    for name in FILES:
        check(f'recalculated_file_matches/{name}', (source / name).read_text() == bundle[name])
    rows = json.loads(bundle['count-lines.json'])
    narration = json.loads(bundle['narration.json'])
    plan = json.loads(bundle['timing-plan.json'])
    values = [r['value'] for r in rows]
    independent = [0] + [sum(math.comb(n - k - 1, k)
                            for k in range((n - 1) // 2 + 1)) for n in range(1, 41)]
    check('41_terms_recurrence_vs_independent_binomial_sum', values == independent)
    check('41_terms_vs_official_OEIS_search_result', tuple(values) == OEIS_TERMS)
    check('initial_values_and_distinct_repeated_one_entries', values[:3] == [0, 1, 1])
    check('first_term_above_100_million', values[-2] < 100_000_000 < values[-1])
    by_id = {r['id']: r for r in narration}
    check('104_unique_narration_ids', len(by_id) == len(narration) == 104)
    check('41_result_events_and_39_prefix_events',
          sum(r['kind'] == 'count' for r in narration) == 41
          and sum(r['kind'] == 'formula_prefix' for r in narration) == 39)
    item_checks = []
    for n, row in enumerate(rows):
        passed = (parse_cardinal(row['text']) == row['value']
                  and row['index'] == n and row['ordinal'] == n + 1
                  and by_id[row['id']]['text'] == row['text']
                  and by_id[row['id']]['index'] == n
                  and ' and ' not in row['text'])
        if n >= 2:
            prefix = row['formula_prefix_text']
            left, right = prefix.removesuffix(' equals').split(' plus ')
            passed = (passed and row['a'] == values[n - 2] and row['b'] == values[n - 1]
                      and row['a'] + row['b'] == row['value']
                      and row['a_index'] == n - 2 and row['b_index'] == n - 1
                      and parse_cardinal(left) == row['a'] and parse_cardinal(right) == row['b']
                      and prefix.endswith(' equals')
                      and by_id[row['formula_narration_id']]['text'] == prefix)
        item_checks.append({'index': n, 'value': row['value'], 'parsed_english_value': parse_cardinal(row['text']),
                            'equation': row['equation_text'], 'passed': bool(passed)})
    check('all_values_English_operands_indices_and_voice_ID_mappings', all(r['passed'] for r in item_checks))
    check('all_provisional_speech_windows_nonoverlapping',
          all(a['planning_window_seconds'][1] <= b['planning_window_seconds'][0]
              for a, b in zip(narration, narration[1:])))
    for row in rows[2:-1]:
        n = row['index']
        if n not in CHECKPOINTS:
            gap = by_id[f'E{n + 1:03}']['planning_window_seconds'][0] - by_id[row['id']]['planning_window_seconds'][1]
            check(f'normal_boundary_2_seconds_after_F{n}', abs(gap - 2) <= .0011)
    check('one_equation_font_mode_switch_at_F21',
          all(r['equation_font_size_px'] == (88 if r['index'] <= 20 else 47) for r in rows[2:]))
    check('I07_describes_number_windows', 'Number windows' in by_id['I07']['text']
          and 'postcard' not in by_id['I07']['text'].lower())
    check('minimum_8_minutes_at_150_wpm_estimate', plan['rough_duration_estimate_seconds'][0] >= 480)
    traces = [carry_trace(a, b) for a, b in ((8, 13), (89, 144), (987, 1597), (39088169, 63245986))]
    check('independent_digit_by_digit_carry_traces', all(t['passed'] for t in traces))
    hashes = {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in FILES}
    return {
        'schema_version': 1, 'status': 'PASS' if not failures else 'FAIL',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'Preproduction mathematical content, English labels, voice-ID mapping and unmeasured timing estimates only. Not raster, animation, audio or completed-video QA.',
        'verification_command': '.venv/bin/python tools/prepare_fibonacci_design.py --check',
        'source_sha256': hashes, 'checks': checks, 'failed_checks': failures,
        'terms': item_checks, 'carry_examples': traces,
        'source_reference': plan['math_source'], 'estimated_word_count': plan['word_count'],
        'estimated_duration_seconds': plan['rough_duration_estimate_seconds'],
        'measured_audio_duration_seconds': None,
    }


def report_text(report):
    lines = [f"Fibonacci preproduction content: {report['status']}", report['scope'],
             '41 terms F0..F40; 39 additions; 104 narration events.',
             f"Estimated words: {report['estimated_word_count']['total']}",
             f"Estimated duration seconds: {report['estimated_duration_seconds']}",
             'Audio has not been generated or measured.',
             'OEIS A000045 checked 2026-11-11 through official search results; direct HTTP requests returned403.', '']
    lines += [f"{'PASS' if c['passed'] else 'FAIL'} {c['name']}" for c in report['checks']]
    lines += ['', 'Per-term independent arithmetic/English/ID checks:']
    lines += [f"F{r['index']} = {r['value']:,}: {'PASS' if r['passed'] else 'FAIL'}" for r in report['terms']]
    return '\n'.join(lines) + '\n'


def write_reports(directory, report):
    names = ('content-verification.json', 'content-verification.txt')
    if any((directory / name).exists() for name in names):
        raise FileExistsError('QA evidence already exists; use a new --qa-dir')
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in zip(names, (json.dumps(report, ensure_ascii=False, indent=2) + '\n', report_text(report))):
        with (directory / name).open('x') as stream:
            stream.write(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--check', action='store_true', help='Read-only verification (also the default)')
    parser.add_argument('--out-dir', type=Path, help='Export the recalculated seven-file bundle to a new directory')
    parser.add_argument('--qa-dir', type=Path, help='Write new evidence; existing report filenames are refused')
    args = parser.parse_args()
    if args.check and args.out_dir:
        parser.error('--check and --out-dir are mutually exclusive')
    source = args.source_dir.resolve()
    bundle = build_bundle(source)
    if args.out_dir:
        output = args.out_dir.resolve()
        if output.exists():
            parser.error('--out-dir must not exist; original design documents will never be overwritten')
        output.mkdir(parents=True, exist_ok=False)
        for name, content in bundle.items():
            with (output / name).open('x') as stream:
                stream.write(content)
        source = output
    report = verify(source, bundle)
    if args.qa_dir:
        write_reports(args.qa_dir.resolve(), report)
    print(json.dumps({'status': report['status'], 'checks': len(report['checks']),
                      'failures': report['failed_checks'], 'word_count': report['estimated_word_count'],
                      'estimated_duration_seconds': report['estimated_duration_seconds']}, ensure_ascii=False))
    if report['failed_checks']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
