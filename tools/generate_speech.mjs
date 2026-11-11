import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile, stat } from "node:fs/promises";
import path from "node:path";
import { parseArgs } from "node:util";
import { KokoroTTS } from "kokoro-js";
import { env, AutoTokenizer, StyleTextToSpeech2Model } from "@huggingface/transformers";

async function main() {
  const { values } = parseArgs({
    options: {
      prep: { type: "string" },
      out: { type: "string" },
      manifest: { type: "string" },
      "approved-library": { type: "string", default: "assets/library/audio/speech/kokoro-af-heart/v002" },
      fresh: { type: "boolean", default: false },
      voice: { type: "string", default: "af_heart" },
      speed: { type: "string", default: "0.98" },
      dtype: { type: "string", default: "fp32" },
      cache: { type: "string", default: "D:/dev/caches/huggingface" },
      sample: { type: "boolean", default: false },
    },
  });
  if (!values.prep || !values.out) throw new Error("--prep and --out are required");
  const speed = Number(values.speed);
  if (!Number.isFinite(speed) || speed < 0.7 || speed > 1.3) throw new Error("Invalid speaking speed");
  if (!["fp32", "q8"].includes(values.dtype)) throw new Error("Use fp32 or q8");
  env.cacheDir = path.resolve(values.cache);
  await mkdir(env.cacheDir, { recursive: true });
  const prep = JSON.parse(await readFile(values.prep, "utf8"));
  const outDir = path.resolve(values.out);
  await mkdir(outDir, { recursive: true });
  const settings = {
    provider: "local-kokoro",
    model_id: "onnx-community/Kokoro-82M-v1.0-ONNX",
    library: "kokoro-js@1.2.1",
    voice_id: values.voice,
    dtype: values.dtype,
    generation_speed: speed,
    sample_rate: 24000,
    channels: 1,
    trim: { peak_threshold_dbfs: -50, guard_ms: 15, edge_fade_ms: 2 },
  };
  const libraryDir = path.resolve(values["approved-library"]);
  const approved = new Map();
  const rejected = new Set();
  try {
    const blocked = JSON.parse(await readFile(path.join(libraryDir, "rejected-source-hashes.json"), "utf8"));
    for (const row of blocked.sources) rejected.add(row.sha256);
  } catch (error) { if (error.code !== "ENOENT") throw error; }
  if (!values.fresh) {
    let libraryPresent = false;
    try {
      const bytes = await readFile(path.join(libraryDir, "measurements.json"));
      libraryPresent = true;
      const library = JSON.parse(bytes);
      const acceptance = JSON.parse(await readFile(path.join(libraryDir, "speech-acceptance.json"), "utf8"));
      if (acceptance.accepted !== true || acceptance.inputs?.manifest?.sha256 !== createHash("sha256").update(bytes).digest("hex")) {
        throw new Error("Approved speech library requires a current successful acceptance receipt");
      }
      if (["model_id", "voice_id", "dtype", "generation_speed"].every(key => library.voice[key] === settings[key])) {
        for (const row of [...library.numbers, ...library.dialogue]) approved.set(row.spoken_text, row);
      }
    } catch (error) {
      if (libraryPresent && error.code === "ENOENT") throw new Error("Existing speech library is missing its acceptance receipt");
      if (error.code !== "ENOENT") throw error;
    }
  }
  let tts;
  const manifest = {
    schema_version: 1,
    measurement_status: "measured",
    voice: settings,
    commercial_rights: {
      license: "Apache-2.0",
      model_source: "https://huggingface.co/hexgrad/Kokoro-82M",
      onnx_source: "https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX",
      note: "Local model and library use; no external voice clone or paid speech service.",
    },
    measurement_method: "Actual trimmed PCM sample count divided by 24000 Hz; no post-generation time stretching.",
    numbers: [], dialogue: [],
  };
  function trimAndEncode(samples, rate) {
    const threshold = 10 ** (-50 / 20);
    let first = 0, last = samples.length - 1;
    while (first <= last && Math.abs(samples[first]) < threshold) first++;
    while (last >= first && Math.abs(samples[last]) < threshold) last--;
    if (first >= last) throw new Error("Generated clip contains no audible speech");
    const guard = Math.round(rate * 0.015);
    first = Math.max(0, first - guard);
    last = Math.min(samples.length - 1, last + guard);
    const count = last - first + 1;
    const pcm = Buffer.alloc(44 + count * 2);
    pcm.write("RIFF"); pcm.writeUInt32LE(36 + count * 2, 4); pcm.write("WAVEfmt ", 8);
    pcm.writeUInt32LE(16, 16); pcm.writeUInt16LE(1, 20); pcm.writeUInt16LE(1, 22);
    pcm.writeUInt32LE(rate, 24); pcm.writeUInt32LE(rate * 2, 28);
    pcm.writeUInt16LE(2, 32); pcm.writeUInt16LE(16, 34); pcm.write("data", 36);
    pcm.writeUInt32LE(count * 2, 40);
    let peak = 0;
    for (let i = first; i <= last; i++) peak = Math.max(peak, Math.abs(samples[i]));
    const gain = peak > 0.85 ? 0.85 / peak : 1;
    const fade = Math.round(rate * 0.002);
    for (let i = 0; i < count; i++) {
      const envelope = Math.min(1, i / fade, (count - 1 - i) / fade);
      const sample = Math.max(-1, Math.min(1, samples[first + i] * gain * envelope));
      pcm.writeInt16LE(Math.round(sample * 32767), 44 + i * 2);
    }
    return {
      buffer: pcm, duration_s: count / rate, trimmed_start_s: first / rate,
      trimmed_end_s: (samples.length - 1 - last) / rate,
      raw_duration_s: samples.length / rate, peak_normalization_gain: gain,
    };
  }
  async function getClip(item, role) {
    const text = item.spoken_text;
    const adopted = approved.get(text);
    if (adopted) {
      const target = path.resolve(libraryDir, adopted.path);
      const actual = createHash("sha256").update(await readFile(target)).digest("hex");
      if (actual !== adopted.sha256 || rejected.has(actual)) throw new Error("Approved speech source changed or is rejected");
      return { ...adopted, path: target.replaceAll("\\", "/"), reused_from_approved_library: true };
    }
    const cacheKey = createHash("sha256").update(JSON.stringify({ settings, text })).digest("hex");
    const filename = role === "number"
      ? `number-${String(item.number).padStart(3, "0")}-${cacheKey.slice(0, 12)}.wav`
      : `dialogue-${cacheKey.slice(0, 16)}.wav`;
    const target = path.join(outDir, filename);
    const metadataFile = target + ".json";
    try {
      const metadata = JSON.parse(await readFile(metadataFile, "utf8"));
      const audio = await readFile(target);
      if (metadata.cache_key !== cacheKey || createHash("sha256").update(audio).digest("hex") !== metadata.sha256) {
        throw new Error("Cache checksum/settings mismatch");
      }
      if (rejected.has(metadata.sha256)) throw new Error(`Rejected speech take for ${text}; use a reviewed context take`);
      return metadata;
    } catch (error) {
      if (error.code !== "ENOENT") throw error;
      try { await stat(target); throw new Error("Refusing to replace an unregistered existing WAV"); }
      catch (fileError) { if (fileError.code !== "ENOENT") throw fileError; }
    }
    if (!tts) {
      console.log(JSON.stringify({ event: "loading_model", ...settings }));
      const [model, tokenizer] = await Promise.all([
        StyleTextToSpeech2Model.from_pretrained(settings.model_id, {
          dtype: values.dtype, device: "cpu",
          session_options: { intraOpNumThreads: 4, interOpNumThreads: 1 },
        }),
        AutoTokenizer.from_pretrained(settings.model_id),
      ]);
      tts = new KokoroTTS(model, tokenizer);
      if (!Object.hasOwn(tts.voices, values.voice)) throw new Error("Voice not present in installed model library");
    }
    const speech = await tts.generate(text + (/[.!?]$/.test(text) ? "" : "."), { voice: values.voice, speed });
    const result = trimAndEncode(speech.audio, speech.sampling_rate);
    if (rejected.has(createHash("sha256").update(result.buffer).digest("hex"))) {
      throw new Error(`Known rejected speech take for ${text}; use a reviewed context take`);
    }
    const metadata = {
      ...(role === "number" ? { number: item.number } : {}),
      spoken_text: text, duration_s: result.duration_s,
      path: target.replaceAll("\\", "/"), cache_key: cacheKey,
      sha256: createHash("sha256").update(result.buffer).digest("hex"),
      measurement_status: "measured",
      trim: { raw_duration_s: result.raw_duration_s, leading_s: result.trimmed_start_s, trailing_s: result.trimmed_end_s, peak_normalization_gain: result.peak_normalization_gain },
    };
    await writeFile(target, result.buffer, { flag: "wx" });
    await writeFile(metadataFile, JSON.stringify(metadata, null, 2) + "\n", { flag: "wx" });
    console.log(JSON.stringify({ event: "clip_ready", role, number: item.number, text, duration_s: result.duration_s }));
    return metadata;
  }
  const sampleNumbers = new Set([1, 10, 20, 50, 99, 100, 101, 150, 199, 200, 201, 250, 299, 300]);
  for (const item of prep.dialogue) {
    const row = await getClip(item, "dialogue");
    row.max_duration_s = item.max_duration_s;
    row.window_fit = row.duration_s <= item.max_duration_s + 1e-8;
    manifest.dialogue.push(row);
  }
  for (const item of prep.count_lines) {
    if (values.sample && !sampleNumbers.has(item.number)) continue;
    manifest.numbers.push(await getClip(item, "number"));
  }
  const targetManifest = values.manifest
    ? path.resolve(values.manifest)
    : path.join(outDir, values.sample ? "sample-measurements.json" : "measurements.json");
  const manifestText = JSON.stringify(manifest, null, 2) + "\n";
  let reusedManifest = false;
  try {
    const existing = await readFile(targetManifest, "utf8");
    if (existing !== manifestText) throw new Error("Existing manifest differs; supply --manifest with a new destination");
    reusedManifest = true;
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
    await mkdir(path.dirname(targetManifest), { recursive: true });
    await writeFile(targetManifest, manifestText, { flag: "wx" });
  }
  console.log(JSON.stringify({
    event: "completed", manifest: targetManifest, numbers: manifest.numbers.length,
    dialogue: manifest.dialogue.length, reused_manifest: reusedManifest,
    dialogue_window_overflows: manifest.dialogue.filter(row => !row.window_fit).map(row => ({ text: row.spoken_text, actual_s: row.duration_s, max_s: row.max_duration_s })),
  }));

}
main().catch(error => { console.error(error.message); process.exitCode = 1; });

