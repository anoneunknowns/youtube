// Text-only G2P classification. This never generates or changes speech audio.
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { parseArgs } from 'node:util';
import { pathToFileURL } from 'node:url';
import path from 'node:path';
import { phonemize } from 'phonemizer';

const digest = bytes => createHash('sha256').update(bytes).digest('hex');
const TARGETS = new Set(['s', 'k', 't', 'f', 'θ', 'ʃ', 'p']);

export async function classifyManifest(manifestPath) {
  const source = path.resolve(manifestPath);
  const bytes = await readFile(source);
  const manifest = JSON.parse(bytes);
  if (manifest.schema_version !== 1 || manifest.measurement_status !== 'measured') {
    throw new Error('Expected a schema_version 1 measured speech manifest');
  }
  if (!Array.isArray(manifest.numbers) || !Array.isArray(manifest.dialogue)) {
    throw new Error('Manifest numbers and dialogue must be arrays');
  }
  const entries = [], numbers = new Set(), dialogue = new Set();
  for (const role of ['number', 'dialogue']) {
    for (const row of manifest[role === 'number' ? 'numbers' : 'dialogue']) {
      if (!row || typeof row !== 'object' || Array.isArray(row)) throw new Error('Invalid manifest row');
      if (role === 'number') {
        if (!Number.isSafeInteger(row.number) || row.number < 1 || numbers.has(row.number)) {
          throw new Error('Invalid or duplicate number');
        }
        numbers.add(row.number);
      }
      if (typeof row.spoken_text !== 'string' || !row.spoken_text.trim()) throw new Error('Missing spoken_text');
      if (role === 'dialogue') {
        if (dialogue.has(row.spoken_text)) throw new Error('Duplicate dialogue text');
        dialogue.add(row.spoken_text);
      }
      if (typeof row.duration_s !== 'number' || !Number.isFinite(row.duration_s) || row.duration_s <= 0) {
        throw new Error('duration_s must be a positive finite number');
      }
      if (typeof row.path !== 'string' || !row.path) throw new Error('Missing audio path');
      if (typeof row.sha256 !== 'string' || !/^[a-fA-F0-9]{64}$/u.test(row.sha256)) {
        throw new Error('Missing or invalid audio SHA256');
      }
      const phonemes = (await phonemize(row.spoken_text, 'en-us')).join(' ');
      const letters = Array.from(phonemes).filter(character => /\p{L}/u.test(character));
      if (!letters.length) throw new Error(`No G2P phonemes for ${row.spoken_text}`);
      const terminal = letters.at(-1);
      entries.push({
        role, number: role === 'number' ? row.number : null, spoken_text: row.spoken_text,
        phonemes, terminal_phoneme: terminal, target_voiceless_terminal: TARGETS.has(terminal),
        duration_s: row.duration_s, path: path.resolve(path.dirname(source), row.path),
        sha256: row.sha256.toLowerCase(),
      });
    }
  }
  if (!entries.length) throw new Error('Manifest has no speech entries');
  const counts = {};
  for (const row of entries) counts[row.terminal_phoneme] = (counts[row.terminal_phoneme] ?? 0) + 1;
  return {
    schema_version: 1, kind: 'read-only-terminal-phoneme-classification',
    source_manifest: source, source_manifest_sha256: digest(bytes), voice: manifest.voice ?? null,
    method: 'Installed phonemizer eSpeak-NG en-us; text to phonemes only, no speech synthesized.',
    classification_is_not_a_pronunciation_approval: true,
    summary: { total: entries.length, target_count: entries.filter(row => row.target_voiceless_terminal).length,
      terminal_counts: counts }, entries,
  };
}

async function main() {
  const { values } = parseArgs({ options: { manifest: { type: 'string' }, out: { type: 'string' } } });
  if (!values.manifest) throw new Error('--manifest is required');
  const report = await classifyManifest(values.manifest);
  const json = JSON.stringify(report, null, 2) + '\n';
  if (values.out) {
    await mkdir(path.dirname(path.resolve(values.out)), { recursive: true });
    await writeFile(values.out, json, { flag: 'wx' });
  } else {
    process.stdout.write(json);
  }
}
if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  main().catch(error => { console.error(error.message); process.exitCode = 1; });
}
