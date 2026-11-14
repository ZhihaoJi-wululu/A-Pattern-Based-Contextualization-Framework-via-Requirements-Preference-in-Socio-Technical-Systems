"""Run the frozen P10 method on one isolated workbench case."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


SOURCE = Path(__file__).resolve().parents[1] / 'method'
METHOD_ID = 'apate.preferred-to.single-facet.checked.parallel.v2'
PROMPT_VERSION = 'P10'
FRAMEWORK_SHA256 = '5a98326f47acaebf5a38ca8c766b606723e33ed0f9b60de14c9a86d0212f0b12'
MANIFEST_SHA256 = '2c0a8f30c9dee60b848cb80782238c30cc8fc75f58222e0268ca25f40b774604'
PATTERN = 'materials/pattern_catalogue_v43.json'
VERSION_DIR = f'versions/{PROMPT_VERSION}'
CASE_ID = 'workbench'
OUTPUT_PATH = f'runs/{PROMPT_VERSION}-{CASE_ID}/output.json'
# Allow the P10 case window and an in-flight request to drain.
WORKER_TIMEOUT = 7500


class P10RuntimeError(RuntimeError):
    pass


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def _longpath(path):
    path = str(Path(path).resolve())
    if os.name == 'nt' and not path.startswith('\\\\?\\'):
        path = '\\\\?\\UNC\\' + path[2:] if path.startswith('\\\\') else '\\\\?\\' + path
    return Path(path)


def run_case(archive, case):
    """Use a fresh process so the P10 vendor modules cannot mix with the server's."""
    archive = _longpath(archive)
    archive.mkdir(parents=True, exist_ok=False)
    _write(archive / 'materials/inputs.json', {CASE_ID: case})
    try:
        with (archive / 'worker.log').open('wb') as log:
            subprocess.run(
                [sys.executable, '-I', '-B', '-X', f'pycache_prefix={archive / "pycache"}',
                 str(Path(__file__).resolve()), str(archive)],
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                check=True, timeout=WORKER_TIMEOUT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
    except subprocess.TimeoutExpired as exc:
        raise P10RuntimeError('The P10 worker exceeded its time limit.') from exc
    except subprocess.CalledProcessError as exc:
        error = archive / 'worker-error.txt'
        message = (error.read_text(encoding='utf-8') if error.is_file()
                   else 'The P10 worker stopped. See worker.log in the local run archive.')
        raise P10RuntimeError(message) from exc
    return json.loads((archive / 'workbench-output.json').read_text(encoding='utf-8'))


def _verified_source(relative, expected):
    try:
        data = (SOURCE / relative).read_bytes()
    except OSError as exc:
        raise P10RuntimeError(f'Missing P10 asset {relative}. Keep the bundled method directory with the workbench.') from exc
    if _sha(data) != expected:
        raise P10RuntimeError(f'The frozen P10 asset {relative} failed its integrity check.')
    return data


def _stage_method(archive):
    frozen = json.loads(_verified_source('release-seal.json', FRAMEWORK_SHA256))
    manifest_path = f'{VERSION_DIR}/manifest.json'
    manifest = json.loads(_verified_source(manifest_path, MANIFEST_SHA256))
    for relative, expected in frozen['files'].items():
        if relative.startswith('runtime/'):
            _verified_source(relative, expected)

    files = {
        PATTERN: frozen['files'][PATTERN],
        manifest_path: MANIFEST_SHA256,
        f'{VERSION_DIR}/prompt.txt': manifest['prompt_sha256'],
        f'{VERSION_DIR}/checker-prompt.txt': manifest['checker_prompt_sha256'],
    }
    for relative, expected in files.items():
        destination = archive / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(_verified_source(relative, expected))
    return manifest, files


def _run_worker(archive):
    manifest, files = _stage_method(archive)
    sys.path.insert(0, str(SOURCE / 'runtime'))
    import facet_runner as runner

    configuration = runner.public_config()
    # Bind this interactive case to the frozen algorithm and the workbench's
    # configured provider. The runner verifies the new case seal at each stage.
    expected = dict(manifest['configuration'])
    for key in ('base_url', 'model', 'timeout', 'credential_present'):
        expected[key] = configuration[key]
    if runner.METHOD != METHOD_ID or configuration != expected:
        raise P10RuntimeError('The P10 worker configuration differs from the bundled method.')
    files['materials/inputs.json'] = _sha((archive / 'materials/inputs.json').read_bytes())
    _write(archive / 'freeze.json', {'method_id': METHOD_ID, 'configuration': configuration,
                                   'files': files})
    ledger = runner.Ledger(archive, request_limit=None, case_limit=1)
    output = runner.run_case(archive, PROMPT_VERSION, CASE_ID, ledger)
    result = output['result']
    artifacts = output['artifacts']
    merged = artifacts['process_candidates']
    supports = []
    if result['is_final']:
        for support in merged['supports']:
            # Export the actual matched pair. The full search and stage
            # evidence stays in the run archive.
            witness = support['witness']
            supports.append({**support, 'witness': {key: witness[key] for key in
                ('schema', 'status', 'input_hash', 'termination_reason', 'witness_pair')}})
    facets = {facet: {key: record.get(key) for key in
              ('status', 'source_kind', 'physical_request_count', 'error')}
              for facet, record in artifacts['facet_results'].items()}
    with (archive / OUTPUT_PATH).open('rb') as raw_output:
        output_sha256 = hashlib.file_digest(raw_output, 'sha256').hexdigest()
    _write(archive / 'workbench-output.json', {
        'result': result,
        'supports': supports,
        'conflicts': merged['conflicts'] if result['is_final'] else [],
        'run': {
            'method_id': METHOD_ID, 'prompt_version': PROMPT_VERSION,
            'framework_revision': artifacts['framework_revision'],
            'framework_sha256': FRAMEWORK_SHA256,
            'pattern_file_sha256': files[PATTERN],
            'prompt_sha256': manifest['prompt_sha256'],
            'checker_prompt_sha256': manifest['checker_prompt_sha256'],
            'configuration': configuration,
            'facets': facets, 'not_dispatched': artifacts['not_dispatched'],
            'physical_request_count': artifacts['physical_request_count'],
            'wall_seconds': output['wall_seconds'],
            'output_path': OUTPUT_PATH,
            'output_sha256': output_sha256,
        },
    })


if __name__ == '__main__':
    run_directory = Path(sys.argv[1])
    try:
        _run_worker(run_directory)
    except P10RuntimeError as error:
        (run_directory / 'worker-error.txt').write_text(str(error), encoding='utf-8')
        raise SystemExit(1)
