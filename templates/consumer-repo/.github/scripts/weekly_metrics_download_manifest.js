const fs = require('fs');
const path = require('path');

const DOWNLOAD_MANIFEST_SCHEMA = 'workflows-weekly-metrics-artifact-download-manifest/v1';

function cleanString(value) {
  if (value === null || value === undefined) return '';
  return String(value).trim();
}

function normalizeStatus(value, allowed, fallback) {
  const cleaned = cleanString(value).toLowerCase();
  return allowed.includes(cleaned) ? cleaned : fallback;
}

function readJsonFile(filePath, fallback = {}) {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch (_error) {
    return fallback;
  }
}

function writeJsonFile(filePath, payload) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
}

function safeArtifactPathSegment(value) {
  const sanitized = cleanString(value)
    .replace(/[\\/]+/g, '_')
    .replace(/[^A-Za-z0-9._-]/g, '_')
    .replace(/\.\.+/g, '_')
    .replace(/^\.{1,2}$/, '_');
  return sanitized || 'unknown';
}

function selectedArtifactsFromSelection(selection = {}) {
  return Array.isArray(selection.selected_artifacts) ? selection.selected_artifacts : [];
}

function compactSelectionDetails(selection = {}, selectionPath = '') {
  return {
    path: selectionPath,
    schema: cleanString(selection.schema),
    status: cleanString(selection.status || 'pass'),
    selected_count: selectedArtifactsFromSelection(selection).length,
    candidate_count: Number.isFinite(Number(selection.candidate_count))
      ? Number(selection.candidate_count)
      : 0,
    candidate_family_counts: selection.candidate_family_counts || {},
    selected_family_counts: selection.selected_family_counts || {},
    missing_priority_families: Array.isArray(selection.missing_priority_families)
      ? selection.missing_priority_families
      : [],
    priority_family_statuses: Array.isArray(selection.priority_family_statuses)
      ? selection.priority_family_statuses
      : [],
    latest_candidate_by_family: selection.latest_candidate_by_family || {},
  };
}

function defaultArtifactDir(root, artifact) {
  return path.posix.join(root, safeArtifactPathSegment(artifact.name), String(artifact.id || ''));
}

function defaultZipPath(root, artifact) {
  return path.posix.join(defaultArtifactDir(root, artifact), `${artifact.id}.zip`);
}

function buildInitialManifest(selection = {}, options = {}) {
  const artifactsRoot = cleanString(options.artifacts_root || options.artifactsRoot) || 'artifacts';
  const selectionPath = cleanString(options.selection_path || options.selectionPath);
  const selected = selectedArtifactsFromSelection(selection);
  const generatedAt = cleanString(options.generated_at || options.generatedAt) || new Date().toISOString();
  return {
    schema: DOWNLOAD_MANIFEST_SCHEMA,
    status: selection.status === 'error' ? 'error' : 'pending',
    generated_at: generatedAt,
    selection: compactSelectionDetails(selection, selectionPath),
    stats: {
      selected_count: selected.length,
      download_pass_count: 0,
      download_failed_count: 0,
      unzip_pass_count: 0,
      unzip_failed_count: 0,
      unzip_skipped_count: 0,
    },
    artifacts: selected.map((artifact, index) => ({
      id: artifact.id,
      name: cleanString(artifact.name),
      family: cleanString(artifact.family),
      created_at: cleanString(artifact.created_at),
      updated_at: cleanString(artifact.updated_at),
      selected_index: index,
      artifact_dir: defaultArtifactDir(artifactsRoot, artifact),
      zip_path: defaultZipPath(artifactsRoot, artifact),
      download: {
        status: 'pending',
        bytes: null,
        error: '',
      },
      unzip: {
        status: 'pending',
        path: defaultArtifactDir(artifactsRoot, artifact),
        error: '',
      },
    })),
  };
}

function findArtifact(manifest, id, name) {
  const cleanId = cleanString(id);
  const cleanName = cleanString(name);
  if (cleanId) {
    return (manifest.artifacts || []).find((artifact) => cleanString(artifact.id) === cleanId);
  }
  return (manifest.artifacts || []).find((artifact) => {
    return cleanName && cleanString(artifact.name) === cleanName;
  });
}

function updateArtifactResult(manifest, result = {}) {
  const artifact = findArtifact(manifest, result.id, result.name);
  if (!artifact) {
    throw new Error(`Artifact is not present in manifest: ${cleanString(result.id || result.name)}`);
  }
  const artifactDir = cleanString(result.artifact_dir || result.artifactDir);
  const zipPath = cleanString(result.zip_path || result.zipPath);
  const zipBytes = Number.parseInt(cleanString(result.zip_bytes || result.zipBytes), 10);
  const downloadStatus = normalizeStatus(
    result.download_status || result.downloadStatus,
    ['pending', 'pass', 'failed', 'skipped'],
    artifact.download?.status || 'pending'
  );
  const unzipStatus = normalizeStatus(
    result.unzip_status || result.unzipStatus,
    ['pending', 'pass', 'failed', 'skipped'],
    artifact.unzip?.status || 'pending'
  );

  if (artifactDir) {
    artifact.artifact_dir = artifactDir;
    artifact.unzip.path = artifactDir;
  }
  if (zipPath) artifact.zip_path = zipPath;

  artifact.download = {
    status: downloadStatus,
    bytes: Number.isFinite(zipBytes) && zipBytes >= 0 ? zipBytes : artifact.download?.bytes ?? null,
    error: cleanString(result.download_error || result.downloadError),
  };
  artifact.unzip = {
    status: unzipStatus,
    path: artifact.unzip?.path || artifact.artifact_dir,
    error: cleanString(result.unzip_error || result.unzipError),
  };
  return artifact;
}

function finalizeManifest(manifest = {}) {
  const artifacts = Array.isArray(manifest.artifacts) ? manifest.artifacts : [];
  const stats = {
    selected_count: artifacts.length,
    download_pass_count: 0,
    download_failed_count: 0,
    unzip_pass_count: 0,
    unzip_failed_count: 0,
    unzip_skipped_count: 0,
  };

  for (const artifact of artifacts) {
    const downloadStatus = artifact.download?.status || 'pending';
    const unzipStatus = artifact.unzip?.status || 'pending';
    if (downloadStatus === 'pass') stats.download_pass_count += 1;
    if (downloadStatus === 'failed') stats.download_failed_count += 1;
    if (unzipStatus === 'pass') stats.unzip_pass_count += 1;
    if (unzipStatus === 'failed') stats.unzip_failed_count += 1;
    if (unzipStatus === 'skipped') stats.unzip_skipped_count += 1;
  }

  let status = 'pass';
  if (manifest.selection?.status === 'error') {
    status = 'error';
  } else if (
    stats.download_failed_count > 0 ||
    stats.unzip_failed_count > 0 ||
    artifacts.some((artifact) => artifact.download?.status === 'pending' || artifact.unzip?.status === 'pending')
  ) {
    status = 'warning';
  }

  manifest.status = status;
  manifest.stats = stats;
  manifest.finalized_at = new Date().toISOString();
  return manifest;
}

function markdownTableCell(value) {
  return cleanString(value).replace(/\r?\n/g, ' ').replace(/\|/g, '\\|');
}

function formatMarkdown(manifest = {}) {
  const stats = manifest.stats || {};
  const lines = [
    '## Weekly Metrics Artifact Downloads',
    '',
    `- Schema: ${manifest.schema || DOWNLOAD_MANIFEST_SCHEMA}`,
    `- Status: ${manifest.status || 'pending'}`,
    `- Selected artifacts: ${stats.selected_count || 0}`,
    `- Downloads: ${stats.download_pass_count || 0} passed, ${stats.download_failed_count || 0} failed`,
    `- Unzip: ${stats.unzip_pass_count || 0} passed, ${stats.unzip_failed_count || 0} failed, ` +
      `${stats.unzip_skipped_count || 0} skipped`,
  ];

  const artifacts = Array.isArray(manifest.artifacts) ? manifest.artifacts : [];
  if (artifacts.length > 0) {
    lines.push('', '| Artifact | ID | Download | Unzip | Path |');
    lines.push('|----------|----|----------|-------|------|');
    for (const artifact of artifacts) {
      const download = artifact.download || {};
      const unzip = artifact.unzip || {};
      const downloadLabel = download.error
        ? `${download.status || 'pending'} (${download.error})`
        : download.status || 'pending';
      const unzipLabel = unzip.error
        ? `${unzip.status || 'pending'} (${unzip.error})`
        : unzip.status || 'pending';
      lines.push(
        `| ${markdownTableCell(artifact.name || 'unknown')} | ${markdownTableCell(
          artifact.id || ''
        )} | ${markdownTableCell(downloadLabel)} | ` +
          `${markdownTableCell(unzipLabel)} | ${markdownTableCell(artifact.artifact_dir || '')} |`
      );
    }
  }

  return `${lines.join('\n')}\n`;
}

function parseArgs(argv = process.argv.slice(2)) {
  const options = {
    mode: '',
    manifest: process.env.METRICS_ARTIFACT_DOWNLOAD_MANIFEST_JSON ||
      'artifacts/metric-artifact-download-manifest.json',
    markdown: process.env.METRICS_ARTIFACT_DOWNLOAD_MANIFEST_MD || '',
    selection: process.env.METRICS_ARTIFACT_SELECTION_JSON ||
      'artifacts/metric-artifacts-selection.json',
    artifacts_root: process.env.METRICS_ARTIFACTS_ROOT || 'artifacts',
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const next = argv[index + 1];
    if (arg === '--init' || arg === '--record' || arg === '--finalize') {
      options.mode = arg.slice(2);
    } else if (arg === '--manifest') {
      options.manifest = next;
      index += 1;
    } else if (arg === '--markdown') {
      options.markdown = next;
      index += 1;
    } else if (arg === '--selection') {
      options.selection = next;
      index += 1;
    } else if (arg === '--artifacts-root') {
      options.artifacts_root = next;
      index += 1;
    } else if (arg.startsWith('--')) {
      const key = arg.slice(2).replace(/-/g, '_');
      options[key] = next;
      index += 1;
    }
  }

  return options;
}

function writeMarkdownIfRequested(markdownPath, manifest) {
  if (!markdownPath) return;
  fs.mkdirSync(path.dirname(markdownPath), { recursive: true });
  fs.writeFileSync(markdownPath, formatMarkdown(manifest), 'utf8');
}

function main() {
  const options = parseArgs();
  if (options.mode === 'init') {
    const selection = readJsonFile(options.selection, { status: 'error', selected_artifacts: [] });
    const manifest = buildInitialManifest(selection, {
      artifacts_root: options.artifacts_root,
      selection_path: options.selection,
    });
    writeJsonFile(options.manifest, manifest);
    writeMarkdownIfRequested(options.markdown, manifest);
    return 0;
  }

  const manifest = readJsonFile(options.manifest, null);
  if (!manifest) {
    throw new Error(`Manifest does not exist or is invalid JSON: ${options.manifest}`);
  }

  if (options.mode === 'record') {
    updateArtifactResult(manifest, options);
    writeJsonFile(options.manifest, manifest);
    writeMarkdownIfRequested(options.markdown, manifest);
    return 0;
  }

  if (options.mode === 'finalize') {
    finalizeManifest(manifest);
    writeJsonFile(options.manifest, manifest);
    writeMarkdownIfRequested(options.markdown, manifest);
    return 0;
  }

  throw new Error('Expected one of --init, --record, or --finalize');
}

if (require.main === module) {
  try {
    process.exitCode = main();
  } catch (error) {
    console.error(error);
    process.exit(1);
  }
}

module.exports = {
  DOWNLOAD_MANIFEST_SCHEMA,
  buildInitialManifest,
  compactSelectionDetails,
  finalizeManifest,
  formatMarkdown,
  safeArtifactPathSegment,
  updateArtifactResult,
};
