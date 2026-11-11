// Produce a separate immutable binary-episode voice library with the first
// episode's exact voice profile. Pronunciation approval is a separate step.
import { readFile, writeFile, mkdir, cp, stat } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import { parseArgs } from 'node:util';
import path from 'node:path';

const jobs = [
  { id: 'binary-zero', text: 'Zero.' },
  { id: 'I01', text: "Hello, number explorers! Let's count in binary." },
  { id: 'I02', text: 'Binary uses only two digits: zero and one.' },
  { id: 'I03', text: 'We read each digit from left to right.' },
  { id: 'I04', text: 'This says one zero. Its value is two.' },
  { id: 'I05', text: 'The small number shows the value.' },
  { id: 'I06', text: 'Bright means one. Dark means zero.' },
  { id: 'I07', text: 'Blank places are not spoken.' },
  { id: 'I08', text: "Our example is finished. Now let's start at zero." },
  { id: 'PLACE_READY', text: 'A new place is ready.' },
  { id: 'SEVEN_PLACES', text: 'Seven places, all ones!' },
];
const reuse = [
  ['STRETCH', "Let's stretch."], ['READY', "Ready? Let's keep going!"],
  ['WE_DID_IT', 'We did it!'], ['THANKS', 'Thanks for counting with me!'],
  ['BYE', 'Bye for now!'],
];
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
async function run(args) {
  await new Promise((resolve, reject) => {
    const child = spawn(process.execPath, args, { stdio: 'inherit', windowsHide: true });
    child.on('error', reject);
    child.on('exit', code => code === 0 ? resolve() : reject(new Error(`Generator exited ${code}`)));
  });
}
async function main() {
  const { values } = parseArgs({ options: {
    candidates: { type: 'string' }, out: { type: 'string' }, 'adopt-only': { type: 'boolean' },
  } });
  if (!values.candidates || !values.out) throw new Error('--candidates and --out required');
  const candidates = path.resolve(values.candidates), out = path.resolve(values.out);
  try { await stat(out); throw new Error('Refusing to overwrite an existing library'); }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
  const priorDir = path.resolve('assets/library/audio/speech/kokoro-af-heart/v002');
  const priorBytes = await readFile(path.join(priorDir, 'measurements.json'));
  const prior = JSON.parse(priorBytes);
  const accepted = JSON.parse(await readFile(path.join(priorDir, 'speech-acceptance.json')));
  if (accepted.accepted !== true || accepted.inputs.manifest.sha256 !== sha(priorBytes)) {
    throw new Error('Prior speech library lacks a current successful receipt');
  }
  if (!values['adopt-only']) {
    await mkdir(candidates, { recursive: true });
    const jobsPath = path.join(candidates, 'jobs.json');
    await writeFile(jobsPath, JSON.stringify(jobs, null, 2) + '\n', { flag: 'wx' });
    await run(['tools/generate_speech_candidates.mjs', '--jobs', jobsPath, '--out', candidates]);
  }
  const takes = JSON.parse(await readFile(path.join(candidates, 'takes.json')));
  if (takes.length !== jobs.length) throw new Error('Candidate coverage mismatch');
  await mkdir(path.join(out, 'clips'), { recursive: true });
  await cp(path.join(priorDir, 'licenses'), path.join(out, 'licenses'), { recursive: true, force: false });
  for (const name of ['model-files.json', 'model-card.md', 'kokoro-js-source-readme.md']) {
    await cp(path.join(priorDir, name), path.join(out, name), { force: false });
  }
  const provenance = [];
  async function adopt(row, id, text, sourceBase, number = null) {
    const source = path.isAbsolute(row.path) ? row.path : path.resolve(sourceBase, row.path);
    const bytes = await readFile(source), hash = sha(bytes);
    if (hash !== row.sha256) throw new Error(`Source hash mismatch: ${id}`);
    if (bytes.toString('ascii', 0, 4) !== 'RIFF' || bytes.toString('ascii', 8, 12) !== 'WAVE'
      || bytes.readUInt16LE(20) !== 1 || bytes.readUInt16LE(22) !== 1
      || bytes.readUInt32LE(24) !== 24000 || bytes.readUInt16LE(34) !== 16
      || bytes.toString('ascii', 36, 40) !== 'data') throw new Error(`Noncanonical WAV: ${id}`);
    const duration = bytes.readUInt32LE(40) / 48000;
    if (Math.abs(duration - row.duration_s) > 1 / 24000) throw new Error(`Duration mismatch: ${id}`);
    const clipPath = `clips/${id}-${hash.slice(0, 12)}.wav`;
    const result = { id, ...(number === null ? {} : { number }), spoken_text: text,
      path: clipPath, duration_s: duration, sha256: hash, measurement_status: 'measured',
      generation: row.generation ?? { provider: 'local-kokoro', source: 'accepted-v002-reuse' },
      trim: row.trim ?? null };
    await writeFile(path.join(out, clipPath), bytes, { flag: 'wx' });
    await writeFile(path.join(out, clipPath + '.json'), JSON.stringify(result, null, 2) + '\n', { flag: 'wx' });
    provenance.push({ id, original_path: source, source_sha256: hash,
      origin: sourceBase === priorDir ? 'accepted-v002-reuse' : 'new-kokoro-candidate' });
    return result;
  }
  const zeroTake = takes.find(row => row.id === 'binary-zero');
  const oneSource = prior.numbers.find(row => row.number === 1 && row.spoken_text === 'one');
  if (!zeroTake || !oneSource) throw new Error('Missing zero/one');
  const numbers = [await adopt(zeroTake, 'binary-zero', 'zero', candidates, 0),
    await adopt(oneSource, 'binary-one', 'one', priorDir, 1)];
  const dialogue = [];
  for (const job of jobs.filter(row => row.id !== 'binary-zero')) {
    const take = takes.find(row => row.id === job.id && row.text === job.text);
    if (!take) throw new Error(`Missing exact text: ${job.id}`);
    dialogue.push(await adopt(take, job.id, job.text, candidates));
  }
  for (const [id, text] of reuse) {
    const row = prior.dialogue.find(row => row.spoken_text === text);
    if (!row) throw new Error(`Missing prior exact dialogue: ${id}`);
    dialogue.push(await adopt(row, id, text, priorDir));
  }
  const manifest = { schema_version: 1, measurement_status: 'measured',
    library_id: 'kokoro-af-heart-binary-en-us-v001', voice: prior.voice,
    commercial_rights: prior.commercial_rights,
    measurement_method: 'Actual PCM16 mono sample count / 24000 Hz; no time stretch.',
    storage_policy: 'Immutable separate binary library; pronunciation acceptance required before production.',
    numbers, dialogue };
  await writeFile(path.join(out, 'measurements.json'), JSON.stringify(manifest, null, 2) + '\n', { flag: 'wx' });
  await writeFile(path.join(out, 'provenance.json'), JSON.stringify({ schema_version: 1,
    prior_manifest_sha256: sha(priorBytes), prior_acceptance_path: path.join(priorDir, 'speech-acceptance.json'),
    reused_sources_require_prior_accepted_hash: true, clips: provenance }, null, 2) + '\n', { flag: 'wx' });
  console.log(JSON.stringify({ out, numbers: numbers.map(row => ({ id: row.id, duration_s: row.duration_s })),
    dialogue: dialogue.map(row => ({ id: row.id, duration_s: row.duration_s })), status: 'pending-independent-review' }));
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
