import { createHash } from "node:crypto";
import { readFile, writeFile, mkdir, stat } from "node:fs/promises";
import path from "node:path";
import { parseArgs } from "node:util";

const digest = bytes => createHash("sha256").update(bytes).digest("hex");
const EVIDENCE_KINDS = new Set(["isolated-phoneme-asr", "isolated-acoustic-analysis", "human-listening"]);
const key = row => row.role === "number" ? `number:${row.number}` : `dialogue:${row.expected_text ?? row.spoken_text}`;
const rowsFromManifest = manifest => [
  ...manifest.numbers.map(row => ({ ...row, role: "number", expected_text: row.spoken_text })),
  ...manifest.dialogue.map(row => ({ ...row, role: "dialogue", expected_text: row.spoken_text })),
];

function indexed(rows, label) {
  if (!Array.isArray(rows)) throw new Error(`${label} requires a results array`);
  const result = new Map();
  for (const row of rows) {
    if (!["number", "dialogue"].includes(row.role)) throw new Error(`Invalid ${label} role`);
    const identity = key(row);
    if (result.has(identity)) throw new Error(`Duplicate ${label} row: ${identity}`);
    result.set(identity, row);
  }
  return result;
}

export function evaluateClip(clip, asr, review) {
  const failures = [];
  if (!asr) failures.push("missing-isolated-asr");
  else {
    if (asr.source_sha256 !== clip.sha256) failures.push("isolated-asr-source-hash-mismatch");
    if (asr.expected_text !== clip.spoken_text) failures.push("isolated-asr-text-mismatch");
    if (!["asr-match", "warning-review-listening"].includes(asr.status)) {
      failures.push("isolated-asr-status-invalid-context-resolution-not-accepted");
    }
  }
  if (!review) failures.push("missing-independent-pronunciation-review");
  else {
    if (review.source_sha256 !== clip.sha256) failures.push("pronunciation-source-hash-mismatch");
    if (review.expected_text !== clip.spoken_text) failures.push("pronunciation-text-mismatch");
    if (review.decision !== "pass") failures.push("pronunciation-review-not-passed");
    if (!Array.isArray(review.evidence) || review.evidence.length === 0) failures.push("missing-pronunciation-evidence");
    else {
      for (const item of review.evidence) {
        if (!EVIDENCE_KINDS.has(item.kind)) failures.push("context-or-unsupported-evidence-does-not-approve-pronunciation");
        if (typeof item.path !== "string" || !item.path || !/^[a-f0-9]{64}$/.test(item.sha256 ?? "")
            || typeof item.summary !== "string" || item.summary.trim().length < 12) {
          failures.push("incomplete-pronunciation-evidence");
        }
      }
    }
  }
  return { ...clip, accepted: failures.length === 0, failures,
    isolated_asr_status: asr?.status ?? null,
    isolated_asr_warning_reviewed: asr?.status === "warning-review-listening" && failures.length === 0,
    pronunciation_decision: review?.decision ?? null,
    pronunciation_evidence: review?.evidence ?? [] };
}

function selfTest() {
  const hash = "a".repeat(64);
  const clip = { role: "number", number: 6, spoken_text: "six", sha256: hash };
  const asr = { role: "number", number: 6, expected_text: "six", source_sha256: hash,
    status: "warning-review-listening" };
  const evidence = { path: "D:/temp/independent.json", sha256: "b".repeat(64),
    kind: "isolated-acoustic-analysis", summary: "Final /s/ has no following voiced vowel." };
  const review = { role: "number", number: 6, expected_text: "six", source_sha256: hash,
    decision: "pass", evidence: [evidence] };
  const assert = (condition, message) => { if (!condition) throw new Error(message); };
  assert(evaluateClip(clip, asr, review).accepted, "A hash-bound independent review should resolve a recognizer warning");
  assert(!evaluateClip(clip, asr, null).accepted, "A context/ASR result cannot substitute for a pronunciation review");
  assert(!evaluateClip(clip, asr, { ...review, decision: "reject" }).accepted, "Rejected pronunciation must block acceptance");
  assert(!evaluateClip(clip, asr, { ...review, source_sha256: "c".repeat(64) }).accepted, "A replaced clip needs fresh evidence");
  assert(!evaluateClip(clip, { ...asr, status: "resolved-by-context-asr" }, review).accepted, "Legacy context resolution must not pass");
  assert(!evaluateClip(clip, asr, { ...review, evidence: [{ ...evidence, kind: "context-asr" }] }).accepted,
    "Context recognition cannot approve pronunciation");
  assert(!evaluateClip(clip, { ...asr, status: "asr-match" }, null).accepted, "An ASR match alone does not approve pronunciation");
  assert(!evaluateClip(clip, asr, { ...review, evidence: [] }).accepted, "Unsubstantiated decisions must fail");
  let rejected = false;
  try { indexed([asr, asr], "test"); } catch { rejected = true; }
  assert(rejected, "Duplicate review coverage must fail");
  console.log(JSON.stringify({ speech_acceptance_cases_passed: 9 }));
}

async function load(file) {
  const absolute = path.resolve(file);
  const bytes = await readFile(absolute);
  return { path: absolute, sha256: digest(bytes), data: JSON.parse(bytes.toString("utf8")) };
}

async function main() {
  const { values } = parseArgs({ options: {
    manifest: { type: "string" }, asr: { type: "string" }, pronunciation: { type: "string" },
    out: { type: "string" }, "prior-manifest": { type: "string" }, "self-test": { type: "boolean" },
  } });
  if (values["self-test"]) { selfTest(); return; }
  if (!values.manifest || !values.asr || !values.pronunciation || !values.out) {
    throw new Error("--manifest, --asr, --pronunciation, and --out are required");
  }
  const outPath = path.resolve(values.out);
  try { await stat(outPath); throw new Error("Refusing to overwrite an existing speech acceptance report"); }
  catch (error) { if (error.code !== "ENOENT") throw error; }
  const [manifest, asr, pronunciation] = await Promise.all([
    load(values.manifest), load(values.asr), load(values.pronunciation),
  ]);
  if (manifest.data.schema_version !== 1 || manifest.data.measurement_status !== "measured") {
    throw new Error("Expected a measured schema_version 1 speech manifest");
  }
  if (asr.data.kind !== "independent-local-asr-review" || asr.data.source_manifest_sha256 !== manifest.sha256) {
    throw new Error("Isolated ASR report must refer to the exact current manifest; context reports are not accepted");
  }
  if (pronunciation.data.schema_version !== 1 || pronunciation.data.kind !== "speech-pronunciation-review"
      || pronunciation.data.source_manifest_sha256 !== manifest.sha256) {
    throw new Error("Pronunciation receipt must refer to the exact current manifest");
  }
  const clips = rowsFromManifest(manifest.data);
  const manifestRows = indexed(clips, "manifest");
  const asrRows = indexed(asr.data.results, "ASR");
  const reviewRows = indexed(pronunciation.data.results, "pronunciation");
  for (const [label, rows] of [["ASR", asrRows], ["pronunciation", reviewRows]]) {
    if (rows.size !== manifestRows.size || [...rows.keys()].some(identity => !manifestRows.has(identity))) {
      throw new Error(`${label} coverage must match the full current manifest exactly`);
    }
  }
  const verifiedEvidence = new Map();
  const results = [];
  for (const clip of clips) {
    const identity = key(clip);
    const sourcePath = path.isAbsolute(clip.path) ? clip.path : path.resolve(path.dirname(manifest.path), clip.path);
    const source = await readFile(sourcePath);
    if (digest(source) !== clip.sha256) throw new Error(`Production source hash mismatch: ${identity}`);
    const result = evaluateClip(clip, asrRows.get(identity), reviewRows.get(identity));
    for (const evidence of result.pronunciation_evidence) {
      if (!evidence.path || !evidence.sha256) continue;
      const evidencePath = path.isAbsolute(evidence.path) ? evidence.path : path.resolve(path.dirname(pronunciation.path), evidence.path);
      let evidenceHash = verifiedEvidence.get(evidencePath);
      if (!evidenceHash) {
        evidenceHash = digest(await readFile(evidencePath));
        verifiedEvidence.set(evidencePath, evidenceHash);
      }
      if (evidenceHash !== evidence.sha256) throw new Error(`Pronunciation evidence hash mismatch: ${evidencePath}`);
    }
    results.push(result);
  }
  let replacements = [];
  let priorManifest = null;
  if (values["prior-manifest"]) {
    priorManifest = await load(values["prior-manifest"]);
    const prior = indexed(rowsFromManifest(priorManifest.data), "prior manifest");
    replacements = results.filter(row => prior.has(key(row)) && prior.get(key(row)).sha256 !== row.sha256)
      .map(row => ({ role: row.role, number: row.number ?? null, expected_text: row.spoken_text,
        previous_source_sha256: prior.get(key(row)).sha256, source_sha256: row.sha256,
        current_source_accepted: row.accepted }));
  }
  const unresolved = results.filter(row => !row.accepted);
  const report = {
    schema_version: 1, kind: "hash-bound-speech-acceptance",
    accepted: unresolved.length === 0,
    scope: "Checks documented isolated recognition, independent pronunciation-review coverage, and exact artifact hashes. It does not certify human listening or prove that an automatic phoneme recognizer is infallible.",
    policy: { context_recognition_can_clear_pronunciation_warning: false,
      isolated_asr_match_alone_approves_pronunciation: false,
      independent_pronunciation_evidence_required_for_every_clip: true,
      changed_source_requires_fresh_hash_bound_review: true },
    inputs: { manifest: { path: manifest.path, sha256: manifest.sha256 },
      isolated_asr: { path: asr.path, sha256: asr.sha256 },
      pronunciation: { path: pronunciation.path, sha256: pronunciation.sha256 },
      prior_manifest: priorManifest ? { path: priorManifest.path, sha256: priorManifest.sha256 } : null },
    summary: { clips: clips.length, numbers: manifest.data.numbers.length, dialogue: manifest.data.dialogue.length,
      independent_evidence_files: verifiedEvidence.size, accepted: results.length - unresolved.length,
      unresolved: unresolved.length, isolated_asr_warnings_reviewed: results.filter(row => row.isolated_asr_warning_reviewed).length,
      replacements: replacements.length },
    unresolved, replacements, results,
  };
  await mkdir(path.dirname(outPath), { recursive: true });
  await writeFile(outPath, JSON.stringify(report, null, 2) + "\n", { flag: "wx" });
  const { accepted: acceptedClips, ...summaryCounts } = report.summary;
  console.log(JSON.stringify({ event: "speech_acceptance_complete", accepted: report.accepted,
    accepted_clips: acceptedClips, ...summaryCounts, out: outPath }));
  if (!report.accepted) process.exitCode = 2;
}

main().catch(error => { console.error(error.message); process.exitCode = 1; });
