import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { createReadStream } from "node:fs";
import { mkdir, readFile, writeFile, stat } from "node:fs/promises";
import path from "node:path";
import { parseArgs, promisify } from "node:util";
import { env, pipeline } from "@huggingface/transformers";

const execFileAsync = promisify(execFile);
const MODEL = "Xenova/whisper-tiny.en";
const MODEL_REVISION = "79fb389fc764e7c395bd330e9531d9d32ada7049";
const MODEL_FILES = [
  { file: "encoder_model_quantized.onnx", bytes: 10124913,
    sha256: "8cc3c6f8563d1b3fbd2c5af9f64c2bed8b020bc593c402d1ef53b9f08fbf1b90" },
  { file: "decoder_model_merged_quantized.onnx", bytes: 30727382,
    sha256: "dbb2e063b7fbc41d9803b9698f93ecb035c50cbb3fb87b56cb131e4a5eb99059" },
];
const sha256 = bytes => createHash("sha256").update(bytes).digest("hex");
const SMALL = new Map([
  ["zero", 0], ["one", 1], ["two", 2], ["three", 3], ["four", 4], ["five", 5],
  ["six", 6], ["seven", 7], ["eight", 8], ["nine", 9], ["ten", 10], ["eleven", 11],
  ["twelve", 12], ["thirteen", 13], ["fourteen", 14], ["fifteen", 15], ["sixteen", 16],
  ["seventeen", 17], ["eighteen", 18], ["nineteen", 19], ["twenty", 20], ["thirty", 30],
  ["forty", 40], ["fifty", 50], ["sixty", 60], ["seventy", 70], ["eighty", 80], ["ninety", 90],
]);

function underHundred(tokens) {
  if (tokens.length === 1 && SMALL.has(tokens[0])) return SMALL.get(tokens[0]);
  if (tokens.length === 2) {
    const tens = SMALL.get(tokens[0]);
    const units = SMALL.get(tokens[1]);
    if (tens >= 20 && tens % 10 === 0 && units >= 1 && units <= 9) return tens + units;
  }
  return null;
}

function underThousand(tokens) {
  const hundred = tokens.indexOf("hundred");
  if (hundred === -1) return underHundred(tokens);
  if (hundred !== 1 || tokens.lastIndexOf("hundred") !== hundred) return null;
  const units = tokens[0] === "a" ? 1 : SMALL.get(tokens[0]);
  if (!(units >= 1 && units <= 9)) return null;
  if (tokens.length === 2) return units * 100;
  const remainder = underHundred(tokens.slice(2));
  return remainder !== null && remainder > 0 ? units * 100 + remainder : null;
}

export function parseRecognizedNumber(text) {
  if (typeof text !== "string") return null;
  const cleaned = text.normalize("NFKC").toLowerCase().trim()
    .replace(/^[\s"'“”‘’([{]+|[\s.!?;:"'“”‘’\])}]+$/g, "");
  if (/^\d{1,5}$/.test(cleaned) || /^\d{1,3}(,\d{3})+$/.test(cleaned)) {
    const numeric = Number(cleaned.replaceAll(",", ""));
    return Number.isSafeInteger(numeric) && numeric <= 10000 ? numeric : null;
  }
  if (!/^[a-z\s\-,]+$/.test(cleaned)) return null;
  const tokens = cleaned.replace(/[\-,]/g, " ").split(/\s+/).filter(token => token && token !== "and");
  const thousand = tokens.indexOf("thousand");
  if (thousand === -1) return underThousand(tokens);
  if (thousand < 1 || tokens.lastIndexOf("thousand") !== thousand) return null;
  const leading = tokens[0] === "a" && thousand === 1 ? 1 : underThousand(tokens.slice(0, thousand));
  const trailing = tokens.length === thousand + 1 ? 0 : underThousand(tokens.slice(thousand + 1));
  if (leading === null || trailing === null || leading < 1) return null;
  const value = leading * 1000 + trailing;
  return value <= 10000 ? value : null;
}

function normalizedDialogue(text) {
  return text.normalize("NFKC").toLowerCase().replace(/\blet['’]s\b/g, "let us")
    .replace(/[^a-z0-9\s]/g, " ").replace(/\s+/g, " ").trim();
}

// Context can help diagnose a recognizer failure, but cannot prove that an
// isolated word has no extra/missing phoneme. Preserve the isolated result.
export function withContextEvidence(row, context) {
  if (!context) return row;
  return { ...row, context_verification: context,
    pronunciation_status: "unresolved-requires-independent-review" };
}

function selfTest() {
  const cases = [
    ["One.", 1], ["13", 13], ["thirteen", 13], ["thirty", 30], ["forty", 40],
    ["twenty-one!", 21], ["one hundred and twenty-eight", 128], ["Two hundred ninety-nine.", 299],
    ["300.", 300], ["a hundred", 100], ["1,000", 1000], ["ten thousand", 10000],
    ["one two", null], ["1.2", null], ["100th", null], ["one hundred hundred", null],
    ["The number is thirteen", null], ["Twenty thirteen", null], ["", null],
  ];
  for (const [text, expected] of cases) {
    if (parseRecognizedNumber(text) !== expected) throw new Error(`Number comparison test failed: ${text}`);
  }
  if (normalizedDialogue("Let's keep going!") !== normalizedDialogue("Let us keep going.")) {
    throw new Error("Dialogue comparison test failed");
  }
  for (const [text, expected] of [
    ["Five, six, seven.", [5, 6, 7]],
    ["79, 80, 81.", [79, 80, 81]],
    ["one hundred eighty-seven, one hundred eighty-eight, one hundred eighty-nine", [187, 188, 189]],
  ]) {
    const parsed = recognizedSequences(text, 3);
    if (parsed.length !== 1 || parsed[0].some((value, index) => value !== expected[index])) {
      throw new Error(`Context comparison test failed: ${text}`);
    }
  }
  if (recognizedSequences("187 A-R-8 189", 3).length !== 0) {
    throw new Error("Context comparison accepted unrecognized letter tokens");
  }
  const isolatedWarning = { status: "warning-review-listening", recognized_text: "Sexy." };
  const contextualMatch = { sequence_matches: true };
  const reviewed = withContextEvidence(isolatedWarning, contextualMatch);
  if (reviewed.status !== isolatedWarning.status
      || reviewed.pronunciation_status !== "unresolved-requires-independent-review") {
    throw new Error("Context evidence incorrectly cleared an isolated speech warning");
  }
  console.log(JSON.stringify({ number_comparison_cases_passed: cases.length,
    dialogue_normalization_passed: true, context_comparison_cases_passed: 4,
    context_cannot_clear_pronunciation_warning: true }));
}

async function assertModelFiles(cacheDir) {
  for (const model of MODEL_FILES) {
    const file = path.join(cacheDir, MODEL, "onnx", model.file);
    const bytes = await readFile(file);
    if (bytes.length !== model.bytes || sha256(bytes) !== model.sha256) {
      throw new Error(`ASR model size/hash mismatch: ${model.file}`);
    }
  }
}

async function decodeAudio(file, ffmpeg, range = null) {
  const rangeBefore = range ? ["-ss", String(range.start_s)] : [];
  const rangeAfter = range ? ["-t", String(range.end_s - range.start_s)] : [];
  const { stdout } = await execFileAsync(ffmpeg, ["-v", "error", "-nostdin", ...rangeBefore, "-i", file, ...rangeAfter,
    "-f", "f32le", "-ac", "1", "-ar", "16000", "pipe:1"],
  { encoding: "buffer", maxBuffer: 16 * 1024 * 1024, windowsHide: true });
  if (stdout.length === 0 || stdout.length % 4 !== 0) throw new Error("Decoded audio has invalid float32 length");
  const audio = new Float32Array(stdout.buffer.slice(stdout.byteOffset, stdout.byteOffset + stdout.byteLength));
  if (audio.some(value => !Number.isFinite(value))) throw new Error("Decoded audio contains non-finite samples");
  // Padding exists only in the recognizer input; the production WAV is unchanged.
  const padding = 2400;
  const padded = new Float32Array(audio.length + 2 * padding);
  padded.set(audio, padding);
  return padded;
}

async function createRecognizer(cacheDir, clips) {
  await assertModelFiles(cacheDir);
  env.cacheDir = cacheDir;
  console.log(JSON.stringify({ event: "loading_local_asr", model: MODEL, clips }));
  return pipeline("automatic-speech-recognition", MODEL, {
    dtype: "q8", device: "cpu",
    session_options: { intra_op_num_threads: 2, inter_op_num_threads: 1 },
    progress_callback: progress => {
      if (progress.status === "done") console.log(JSON.stringify({ event: "model_file_ready", file: progress.file }));
    },
  });
}

function recognizedSequences(text, groupCount) {
  const tokens = text.normalize("NFKC").toLowerCase().replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/).filter(Boolean);
  if (tokens.length > 40) return [];
  const candidates = new Map();
  function visit(offset, values) {
    if (values.length === groupCount) {
      if (offset === tokens.length) candidates.set(values.join(","), values);
      return;
    }
    for (let end = offset + 1; end <= Math.min(tokens.length, offset + 8); end++) {
      const value = parseRecognizedNumber(tokens.slice(offset, end).join(" "));
      if (value !== null) visit(end, [...values, value]);
    }
  }
  visit(0, []);
  return [...candidates.values()];
}

async function hashFile(file) {
  const digest = createHash("sha256");
  for await (const chunk of createReadStream(file)) digest.update(chunk);
  return digest.digest("hex");
}

async function contextReview(values, outPath) {
  if (!values.timeline || !values.master) throw new Error("Context review requires --timeline and --master");
  const initialPath = path.resolve(values["context-review"]);
  const rawInitial = await readFile(initialPath);
  const initial = JSON.parse(rawInitial.toString("utf8"));
  if (initial.kind !== "independent-local-asr-review") {
    throw new Error("Context review requires the original isolated-ASR report");
  }
  const rawTimeline = await readFile(path.resolve(values.timeline));
  const timeline = JSON.parse(rawTimeline.toString("utf8"));
  const masterPath = path.resolve(values.master);
  const receipt = JSON.parse(await readFile(masterPath.replace(/\.[^.]+$/, ".mix.json"), "utf8"));
  if (receipt.speech_manifest_sha256 !== initial.source_manifest_sha256) {
    throw new Error("Master speech manifest does not match the initial recognition review");
  }
  const numberEvents = timeline.events.filter(event => event.kind === "speech" && event.role === "number");
  const byNumber = new Map(numberEvents.map(event => [event.number, event]));
  const warnings = initial.warnings.filter(row => row.role === "number");
  const recognizer = await createRecognizer(path.resolve(values.cache), warnings.length);
  const verified = [];
  try {
    for (const warning of warnings) {
      const expected = [warning.number - 1, warning.number, warning.number + 1].filter(value => byNumber.has(value));
      const first = byNumber.get(expected[0]);
      const last = byNumber.get(expected.at(-1));
      const range = { start_s: Math.max(0, first.start_s - 0.08),
        end_s: Math.min(timeline.duration_s, last.end_s + 0.08) };
      const audio = await decodeAudio(masterPath, values.ffmpeg, range);
      const response = await recognizer(audio, { max_new_tokens: 64, do_sample: false, num_beams: 1 });
      const transcript = response.text?.trim() ?? "";
      const candidates = recognizedSequences(transcript, expected.length);
      const sequenceMatches = candidates.length === 1 && candidates[0].every((value, index) => value === expected[index]);
      const item = { number: warning.number, expected_sequence: expected, recognized_text: transcript,
        parsed_sequence_candidates: candidates, range_s: range,
        expected_text_used_as_recognition_prompt: false, sequence_matches: sequenceMatches,
        resolves_pronunciation_warning: false };
      verified.push(item);
      console.log(JSON.stringify({ event: "context_asr", ...item }));
    }
  } finally {
    await recognizer.dispose();
  }
  const verifiedByNumber = new Map(verified.map(row => [row.number, row]));
  const results = initial.results.map(row => {
    const context = row.role === "number" ? verifiedByNumber.get(row.number) : undefined;
    return withContextEvidence(row, context);
  });
  const remaining = results.filter(row => row.status === "warning-review-listening");
  const report = { ...initial, kind: "independent-local-asr-context-review",
    initial_review: { path: initialPath, sha256: sha256(rawInitial), summary: initial.summary },
    context_source: { master_path: masterPath, master_sha256: await hashFile(masterPath),
      timeline_path: path.resolve(values.timeline), timeline_sha256: sha256(rawTimeline),
      method: "Recognize actual master intervals with neighboring spoken numbers; no reference prompt or audio modification." },
    summary: { ...initial.summary, initial_warnings: initial.warnings.length,
      context_reviewed: verified.length,
      context_sequence_matches: verified.filter(row => row.sequence_matches).length,
      context_resolved: 0, asr_matches: initial.summary.asr_matches, warnings: remaining.length },
    acceptance: { accepted: false,
      reason: "Context recognition does not resolve isolated pronunciation warnings. Use the separate hash-bound pronunciation acceptance gate." },
    warnings_history: initial.warnings, context_verifications: verified,
    warnings: remaining, results };
  await mkdir(path.dirname(outPath), { recursive: true });
  await writeFile(outPath, JSON.stringify(report, null, 2) + "\n", { flag: "wx" });
  console.log(JSON.stringify({ event: "context_review_complete", ...report.summary, out: outPath }));
}

async function main() {
  const { values } = parseArgs({ options: {
    manifest: { type: "string", default: "assets/library/audio/speech/kokoro-af-heart/v002/measurements.json" },
    out: { type: "string" },
    cache: { type: "string", default: "D:/dev/caches/huggingface" },
    ffmpeg: { type: "string", default: "ffmpeg" },
    "numbers-only": { type: "boolean", default: false },
    "self-test": { type: "boolean", default: false },
    "context-review": { type: "string" },
    timeline: { type: "string" },
    master: { type: "string" },
  } });
  if (values["self-test"]) { selfTest(); return; }
  if (!values.out) throw new Error("--out with a new report path is required");
  const manifestPath = path.resolve(values.manifest);
  const outPath = path.resolve(values.out);
  try { await stat(outPath); throw new Error("Refusing to overwrite an existing recognition review"); }
  catch (error) { if (error.code !== "ENOENT") throw error; }
  if (values["context-review"]) { await contextReview(values, outPath); return; }
  const rawManifest = await readFile(manifestPath);
  const manifest = JSON.parse(rawManifest.toString("utf8"));
  if (manifest.schema_version !== 1 || manifest.measurement_status !== "measured") {
    throw new Error("Expected a measured schema_version 1 speech manifest");
  }
  if (!Array.isArray(manifest.numbers) || !Array.isArray(manifest.dialogue)) {
    throw new Error("Speech manifest requires numbers and dialogue arrays");
  }
  const seenNumbers = new Set();
  const seenDialogue = new Set();
  const clips = [];
  for (const row of manifest.numbers) {
    if (!Number.isInteger(row.number) || row.number < 1 || row.number > 10000 || seenNumbers.has(row.number)) {
      throw new Error("Invalid or duplicate speech number");
    }
    seenNumbers.add(row.number);
    if (parseRecognizedNumber(row.spoken_text) !== row.number) throw new Error(`Expected number text mismatch: ${row.number}`);
    clips.push({ ...row, role: "number" });
  }
  const ordered = [...seenNumbers].sort((left, right) => left - right);
  if (ordered.length !== 150 || ordered.some((value, index) => value !== index * 2 + 1)) throw new Error("Expected all 150 odd integers one through 299");
  if (!values["numbers-only"]) {
    for (const row of manifest.dialogue) {
      if (typeof row.spoken_text !== "string" || !row.spoken_text.trim() || seenDialogue.has(row.spoken_text)) {
        throw new Error("Invalid or duplicate dialogue text");
      }
      seenDialogue.add(row.spoken_text);
      clips.push({ ...row, role: "dialogue" });
    }
  }
  if (clips.length === 0) throw new Error("Speech manifest contains no clips");
  const cacheDir = path.resolve(values.cache);
  const recognizer = await createRecognizer(cacheDir, clips.length);
  const started = Date.now();
  const results = [];
  try {
    for (const clip of clips) {
      if (typeof clip.path !== "string" || !clip.path || !Number.isFinite(clip.duration_s) || clip.duration_s <= 0) {
        throw new Error("Speech clip requires a path and positive finite measured duration");
      }
      const file = path.isAbsolute(clip.path) ? clip.path : path.resolve(path.dirname(manifestPath), clip.path);
      const bytes = await readFile(file);
      const digest = sha256(bytes);
      if (clip.sha256 && clip.sha256 !== digest) throw new Error(`Source speech hash mismatch: ${clip.number ?? clip.spoken_text}`);
      const audio = await decodeAudio(file, values.ffmpeg);
      const recognized = await recognizer(audio, { max_new_tokens: 64, do_sample: false, num_beams: 1 });
      const transcript = recognized.text?.trim() ?? "";
      const interpreted = clip.role === "number" ? parseRecognizedNumber(transcript) : null;
      const matches = clip.role === "number" ? interpreted === clip.number
        : normalizedDialogue(transcript) === normalizedDialogue(clip.spoken_text);
      results.push({ role: clip.role, number: clip.number ?? null, expected_text: clip.spoken_text,
        recognized_text: transcript, interpreted_number: interpreted,
        status: matches ? "asr-match" : "warning-review-listening", path: file,
        source_sha256: digest, source_duration_s: clip.duration_s });
      if (!matches || results.length % 20 === 0 || results.length === clips.length) {
        console.log(JSON.stringify({ event: "asr_progress", completed: results.length, total: clips.length,
          warnings: results.filter(row => row.status !== "asr-match").length,
          current: clip.number ?? clip.spoken_text, transcript }));
      }
    }
  } finally {
    await recognizer.dispose();
  }
  const warnings = results.filter(row => row.status !== "asr-match");
  const report = {
    schema_version: 1, kind: "independent-local-asr-review", source_manifest: manifestPath,
    source_manifest_sha256: sha256(rawManifest), automatic_regeneration: false,
    model: { id: MODEL, repository_revision_at_verification: MODEL_REVISION, dtype: "q8",
      runtime: "@huggingface/transformers@3.8.1", intra_op_threads: 2, inter_op_threads: 1,
      model_card: "https://huggingface.co/Xenova/whisper-tiny.en", model_license: "Apache-2.0",
      original_code_license: "https://github.com/openai/whisper/blob/main/LICENSE",
      checked_onnx_files: MODEL_FILES },
    method: { sampling_rate: 16000, channels: 1, input_format: "float32",
      recognizer_only_edge_padding_s: 0.15, source_audio_modified: false,
      expected_text_used_as_recognition_prompt: false, numeric_comparison: "cardinal numeric value",
      dialogue_comparison: "case/punctuation normalization, expanding let's to let us",
      limitations: "Tiny ASR can misrecognize isolated numbers. Numeric/text matches check recognized meaning, not correct articulation. Context matches never clear isolated pronunciation warnings. Independent pronunciation review is required; automated checks do not replace final listening." },
    acceptance: { accepted: false,
      reason: "An ASR match alone is not pronunciation approval. Use the separate hash-bound pronunciation acceptance gate." },
    summary: { clips: results.length, numbers: results.filter(row => row.role === "number").length,
      dialogue: results.filter(row => row.role === "dialogue").length, asr_matches: results.length - warnings.length,
      warnings: warnings.length, elapsed_s: (Date.now() - started) / 1000 },
    warnings, results,
  };
  await mkdir(path.dirname(outPath), { recursive: true });
  await writeFile(outPath, JSON.stringify(report, null, 2) + "\n", { flag: "wx" });
  console.log(JSON.stringify({ event: "asr_review_complete", ...report.summary, out: outPath }));
}

main().catch(error => { console.error(error.message); process.exitCode = 1; });
