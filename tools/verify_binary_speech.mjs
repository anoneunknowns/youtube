// Isolated zero/one and dialogue recognition. Binary rows never pass through
// decimal number parsing; no reference text is supplied to recognition.
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify, parseArgs } from 'node:util';
import path from 'node:path';
import { env, pipeline } from '@huggingface/transformers';

const exec = promisify(execFile);
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const modelId = 'Xenova/whisper-tiny.en';
const modelFiles = [
  ['encoder_model_quantized.onnx', '8cc3c6f8563d1b3fbd2c5af9f64c2bed8b020bc593c402d1ef53b9f08fbf1b90'],
  ['decoder_model_merged_quantized.onnx', 'dbb2e063b7fbc41d9803b9698f93ecb035c50cbb3fb87b56cb131e4a5eb99059'],
];
function normalize(text) {
  return text.normalize('NFKC').toLowerCase().replace(/\blet['’]s\b/g, 'let us')
    .replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ').trim();
}
async function main() {
  const { values } = parseArgs({ options: { manifest: { type: 'string' }, out: { type: 'string' } } });
  if (!values.manifest || !values.out) throw new Error('--manifest and --out required');
  const manifestPath = path.resolve(values.manifest), bytes = await readFile(manifestPath);
  const manifest = JSON.parse(bytes);
  if (manifest.schema_version !== 1 || manifest.measurement_status !== 'measured'
      || manifest.numbers.length !== 2 || !manifest.numbers.some(row => row.number === 0 && row.spoken_text === 'zero')
      || !manifest.numbers.some(row => row.number === 1 && row.spoken_text === 'one')) throw new Error('Expected binary zero/one manifest');
  env.cacheDir = 'D:/dev/caches/huggingface'; env.allowRemoteModels = false;
  for (const [file, expected] of modelFiles) {
    if (hash(await readFile(path.join(env.cacheDir, modelId, 'onnx', file))) !== expected) throw new Error(`Model integrity: ${file}`);
  }
  const recognizer = await pipeline('automatic-speech-recognition', modelId, {
    dtype: 'q8', device: 'cpu', session_options: { intra_op_num_threads: 2, inter_op_num_threads: 1 },
  });
  const rows = [...manifest.numbers.map(row => ({ ...row, role: 'number' })),
    ...manifest.dialogue.map(row => ({ ...row, role: 'dialogue' }))];
  const results = [];
  for (const row of rows) {
    const sourcePath = path.resolve(path.dirname(manifestPath), row.path), source = await readFile(sourcePath);
    if (hash(source) !== row.sha256) throw new Error(`Source hash: ${row.id}`);
    const { stdout } = await exec('D:/dev/FFmpeg/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe',
      ['-v', 'error', '-nostdin', '-i', sourcePath, '-f', 'f32le', '-ac', '1', '-ar', '16000', 'pipe:1'],
      { encoding: 'buffer', maxBuffer: 16 * 1024 * 1024, windowsHide: true });
    const raw = new Float32Array(stdout.buffer.slice(stdout.byteOffset, stdout.byteOffset + stdout.byteLength));
    const audio = new Float32Array(raw.length + 4800); audio.set(raw, 2400);
    const recognized = await recognizer(audio, { return_timestamps: false });
    const text = recognized.text.trim();
    // A solitary numeral is a legitimate recognizer transcription of one
    // isolated digit; a multi-digit numeral or sentence is never accepted here.
    const normalized = normalize(text);
    const digitToken = normalized === '0' ? 'zero' : normalized === '1' ? 'one' : normalized;
    const matches = row.role === 'number' ? digitToken === row.spoken_text : normalized === normalize(row.spoken_text);
    const result = { role: row.role, number: row.number ?? null, id: row.id,
      expected_text: row.spoken_text, source_sha256: row.sha256, source_path: sourcePath,
      recognized_text: text, status: matches ? 'asr-match' : 'warning-review-listening' };
    results.push(result); console.log(JSON.stringify(result));
  }
  const warnings = results.filter(row => row.status !== 'asr-match');
  const report = { schema_version: 1, kind: 'independent-local-asr-review',
    source_manifest: manifestPath, source_manifest_sha256: hash(bytes),
    model: { id: modelId, revision: '79fb389fc764e7c395bd330e9531d9d32ada7049', dtype: 'q8' },
    method: 'Independent isolated 16 kHz recognition without expected text or adjacent numbers. No decimal sequence parser. Recognizer-only 150 ms guard silence; source unchanged.',
    limitations: 'ASR is automated evidence, not human listening or a guarantee of pronunciation.',
    summary: { clips: results.length, asr_matches: results.length - warnings.length, warnings: warnings.length }, warnings, results };
  await mkdir(path.dirname(path.resolve(values.out)), { recursive: true });
  await writeFile(values.out, JSON.stringify(report, null, 2) + '\n', { flag: 'wx' });
  console.log(JSON.stringify({ completed: true, ...report.summary, out: values.out }));
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
