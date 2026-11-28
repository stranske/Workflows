set -euo pipefail
context_file="$VERIFIER_CONTEXT_PATH"
diff_file="$VERIFIER_DIFF_PATH"
model="$VERIFIER_MODEL"
provider="$VERIFIER_PROVIDER"
if [ "$provider" = "auto" ]; then
  provider=""
fi

# Build args array
args=(--context-file "$context_file" --json)
if [ -n "$diff_file" ] && [ -f "$diff_file" ]; then
  args+=(--diff-file "$diff_file")
fi
if [ -n "$model" ]; then
  args+=(--model "$model")
fi
if [ -n "$provider" ] && [ "$provider" != "github-models" ]; then
  args+=(--provider "$provider")
fi
agent_label="${{ steps.agent.outputs.agent_label || '' }}"
from_label="${{ steps.agent.outputs.from_label || '' }}"
args+=(--create-issue)
if [ -n "$agent_label" ]; then
  args+=(--issue-label "$agent_label")
fi
if [ -n "$from_label" ]; then
  args+=(--issue-label "$from_label")
fi
args+=(--issue-label verify:evaluate)

# Run evaluator (stderr to separate file to avoid corrupting JSON)
evaluation_exit=0
python .workflows-lib/scripts/langchain/pr_verifier.py "${args[@]}" \
  > evaluation-raw.json 2> evaluation-raw-stderr.log || evaluation_exit=$?
export EVALUATION_EXIT_CODE="$evaluation_exit"

# Keep launch/transport failures distinct from an actual model decision.
# This stdlib receipt still runs if evaluator imports or argument parsing fail.
python3 - <<'PYRECEIPT' > evaluation-transport-outputs.env
import hashlib
import json
import os
from pathlib import Path

secret_names = ('GITHUB_TOKEN', 'GH_TOKEN', 'OPENAI_API_KEY',
                'CLAUDE_API_STRANSKE', 'ANTHROPIC_API_KEY', 'LANGSMITH_API_KEY',
                'LANGCHAIN_API_KEY', 'WORKFLOWS_APP_PRIVATE_KEY')
secrets = sorted({spelling.encode() for name in secret_names
                  if len(os.environ.get(name, '')) >= 8
                  for spelling in (os.environ[name], json.dumps(os.environ[name])[1:-1])},
                 key=len, reverse=True)
overlap = max((len(secret) for secret in secrets), default=0)
refs = {}
for name, source, limit, keep_tail in (
    ('evaluation.json', 'evaluation-raw.json', 8 * 1024 * 1024, False),
    ('evaluation-stderr.log', 'evaluation-raw-stderr.log', 1024 * 1024, True),
):
    path = Path(name)
    prefix, tail, count = b'', b'', 0
    digest = hashlib.sha256()
    error = None
    try:
        with Path(source).open('rb') as handle:
            while chunk := handle.read(64 * 1024):
                digest.update(chunk)
                count += len(chunk)
                if len(prefix) < limit + overlap:
                    prefix += chunk[:limit + overlap - len(prefix)]
                if keep_tail:
                    tail = (tail + chunk)[-(limit // 2 + overlap):]
    except OSError as exc:
        error = type(exc).__name__
    truncated = count > limit
    def redact(raw):
        for secret in secrets:
            # Preserve overlap positions until prefix/tail slicing is complete.
            raw = raw.replace(secret, b'*' * len(secret))
        return raw
    sanitized = redact(prefix)
    if truncated and keep_tail:
        marker = b'\n[diagnostic truncated]\n'
        prefix_limit = (limit - len(marker)) // 2
        tail_limit = limit - len(marker) - prefix_limit
        sanitized = sanitized[:prefix_limit] + marker + redact(tail)[-tail_limit:]
    else:
        sanitized = sanitized[:limit]
    text = sanitized.decode('utf-8', errors='replace')
    raw = text.encode()
    try:
        path.write_bytes(raw)
    except OSError as exc:
        error = type(exc).__name__
    refs[name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
                  'original_bytes': count, 'original_sha256': digest.hexdigest(),
                  'original_complete': error is None, 'truncated': truncated,
                  'redacted': any(secret in prefix or secret in tail for secret in secrets),
                  'retention_error_type': error}
    # Raw streams are never uploaded or printed, including on retention failure.
    try:
        Path(source).unlink(missing_ok=True)
    except OSError:
        pass
code = int(os.environ['EVALUATION_EXIT_CODE'])
data = None
validation_error_type = None
status = 'process_failed' if code else 'invalid_output'
if any(ref['retention_error_type'] for ref in refs.values()):
    status = 'retention_failed'
elif refs['evaluation.json']['truncated']:
    status = 'output_truncated'
elif code == 0:
    try:
        from scripts.langchain.pr_verifier import EvaluationResult
        data = EvaluationResult.model_validate(
            json.loads(Path('evaluation.json').read_text(encoding='utf-8')), strict=True
        ).model_dump()
        status = ('completed' if data['used_llm'] and not data.get('error')
                  and data['verdict'] in ('PASS', 'CONCERNS', 'FAIL')
                  else 'result_unavailable')
    except Exception as exc:
        validation_error_type = type(exc).__name__
identity_path = Path('verifier-input-manifest.json')
identity_ref = None
if identity_path.is_file():
    raw = identity_path.read_bytes()
    identity_ref = {'path': str(identity_path), 'sha256': hashlib.sha256(raw).hexdigest()}
receipt = {'schema': 'workflows-verifier-evaluation-execution/v1',
           'mode': 'evaluate', 'acceptance_authority': False,
           'status': status, 'exit_code': code, 'decision_available': status == 'completed',
           'validation_error_type': validation_error_type,
           'recoverable': status != 'completed', 'model_execution': 'unconfirmed',
           'remote_effects': 'unconfirmed', 'retry_authority': False,
           'repository': os.environ.get('GITHUB_REPOSITORY'),
           'source_run_id': os.environ.get('GITHUB_RUN_ID'),
           'source_run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
           'provider_requested': os.environ.get('VERIFIER_PROVIDER'),
           'model_requested': os.environ.get('VERIFIER_MODEL'),
           'input_manifest': identity_ref, 'outputs': refs}
Path('evaluation-execution.json').write_text(json.dumps(receipt, indent=2) + '\n')
print('execution_status=' + status)
print('verdict=' + (data['verdict'] if status == 'completed' else 'UNVERIFIABLE_INPUT'))
PYRECEIPT
cat evaluation-transport-outputs.env >> "$GITHUB_OUTPUT"
evaluation_status="$(grep '^execution_status=' evaluation-transport-outputs.env | cut -d= -f2-)"
if [ -s evaluation-stderr.log ]; then
  echo '::group::Evaluation stderr (secret values redacted)'
  cat evaluation-stderr.log
  echo '::endgroup::'
fi
if [ "$evaluation_status" != 'completed' ]; then
  printf '%s\n' '## LLM Evaluation Report' '' '**Verdict:** UNVERIFIABLE_INPUT' '' \
    "Evaluator execution status: $evaluation_status (exit $evaluation_exit)." \
    'No usable evaluation decision was returned. Provider execution is not established by this receipt.' \
    'Retained evaluation-execution.json and redacted stdout/stderr identify the recoverable failure.' \
    > evaluation-comment.md
  cat evaluation-comment.md
else
# Parse result
if [ -f evaluation.json ]; then
python3 - <<'PY' > evaluation-outputs.env 2>/dev/null || true
import json

try:
  with open('evaluation.json', encoding='utf-8') as handle:
    data = json.load(handle)
except Exception:
  data = {}

print(f"verdict={data.get('verdict', 'CONCERNS')}")
print(f"trace_id={data.get('langsmith_trace_id', '')}")
print(f"trace_url={data.get('langsmith_trace_url', '')}")
PY

  if [ -s evaluation-outputs.env ]; then
    cat evaluation-outputs.env >> "$GITHUB_OUTPUT"
    verdict="$(grep '^verdict=' evaluation-outputs.env | cut -d= -f2- || true)"
    trace_id="$(grep '^trace_id=' evaluation-outputs.env | cut -d= -f2- || true)"
    trace_url="$(grep '^trace_url=' evaluation-outputs.env | cut -d= -f2- || true)"
  else
    verdict="CONCERNS"
    trace_id=""
    trace_url=""
  fi

  echo "::debug::Evaluation verdict: $verdict"
  if [ -n "$trace_id" ]; then
    echo "::debug::LangSmith trace id: $trace_id"
  fi

  # Log trace URL for easy access from workflow logs
  if [ -n "$trace_url" ]; then
    echo "::notice title=LangSmith Trace::View trace: $trace_url"
  fi

  # Format output for comment
  python3 - <<'PYFORMAT'
import json
import sys

try:
    with open('evaluation.json') as f:
        data = json.load(f)

    coverage = data.get('input_coverage') or {}
    reviewed = coverage.get('files_complete', 0) if data.get('used_llm') else 0
    total = coverage.get('files_total', 0)
    lines = ["## LLM Evaluation Report", "", f"files reviewed {reviewed} of {total}", ""]
    if data.get('files_not_reviewed'):
        lines.append('files_not_reviewed: ' + json.dumps(data['files_not_reviewed']))
    lines.append(f"**Verdict:** {data.get('verdict', 'UNKNOWN')}")
    lines.append("")

    if data.get('summary'):
        lines.append(f"**Summary:** {data['summary']}")
        lines.append("")

    scores = data.get('scores')
    if scores:
        lines.append("### Scores")
        lines.append("| Criterion | Score |")
        lines.append("|-----------|-------|")
        for key in ['correctness', 'completeness', 'quality', 'testing', 'risks']:
            score = scores.get(key, 'N/A')
            lines.append(f"| {key.capitalize()} | {score}/10 |")
        lines.append("")

    concerns = data.get('concerns', [])
    if concerns:
        lines.append("### Concerns")
        for c in concerns:
            if c:
                lines.append(f"- {c}")
        lines.append("")

    # Add LangSmith trace link if available
    trace_url = data.get('langsmith_trace_url')
    if trace_url:
        lines.append("### 🔍 LangSmith Trace")
        lines.append(f"[View detailed evaluation trace]({trace_url})")
        lines.append("")

    if data.get('error'):
        lines.append(f"**Note:** {data['error']}")

    with open('evaluation-comment.md', 'w') as f:
        f.write('\n'.join(lines))
except Exception as e:
    with open('evaluation-comment.md', 'w') as f:
        f.write(f"## LLM Evaluation\n\nEvaluation encountered an error: {e}")
PYFORMAT

  cat evaluation-comment.md
else
  echo "verdict=CONCERNS" >> "$GITHUB_OUTPUT"
  printf "%s\n" \
    "## LLM Evaluation" \
    "" \
    "Evaluation could not run (missing output)." \
    > evaluation-comment.md
fi

fi
