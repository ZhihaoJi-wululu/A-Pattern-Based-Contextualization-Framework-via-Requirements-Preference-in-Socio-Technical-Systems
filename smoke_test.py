"""Exercise the packaged workbench with a deterministic loopback provider."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from secrets import token_urlsafe
from shutil import copytree, ignore_patterns
from socket import socket
from subprocess import DEVNULL, Popen
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import URLError
from urllib.request import Request, build_opener, ProxyHandler
import json
import os
import sys
import time


ROOT = Path(__file__).resolve().parent
HTTP = build_opener(ProxyHandler({}))


def request(base, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    query = Request(base + path, data=data, headers={'Content-Type': 'application/json'})
    with HTTP.open(query, timeout=40) as response:
        body = response.read()
        return json.loads(body) if response.headers.get_content_type() == 'application/json' else body


class TestProvider(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != '/v1/chat/completions':
            self.send_error(404)
            return
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        assert body['response_format']['type'] == 'json_schema'
        payload = json.loads(body['messages'][-1]['content'])
        facet = payload['active_facet']
        if facet == 'Sociability':
            self.server.stages.append('check' if 'draft' in payload else 'generate')
        proposal = {
            'scope': 'G1', 'source': 'T1', 'target': 'T2',
            'rule_id': 'MS-SOC-01', 'outcome_id': 'MS-SOC-01.primary',
            'persona_quote': 'enjoys two-way conversation',
            'model_evidence': [
                {'node_id': 'T1', 'field': 'description', 'quote': 'two-way confirmation'},
                {'node_id': 'T2', 'field': 'label', 'quote': 'Read and adopt approved schedule alone'},
            ],
            'reason': 'Joint confirmation offers reciprocal conversation within the approved collection arrangements.',
        }
        content = json.dumps({'proposals': [proposal] if facet == 'Sociability' else []})
        response = json.dumps({'model': 'local-smoke-test', 'choices': [
            {'message': {'content': content}, 'finish_reason': 'stop'}]}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, *args):
        pass


def check_workbench(base, root, provider):
    for _ in range(60):
        try:
            assert request(base, '/api/health')['status'] == 'ok'
            break
        except URLError:
            time.sleep(0.1)
    else:
        raise RuntimeError('The workbench did not start.')
    assert b'Contextualize model' in request(base, '/')
    examples = request(base, '/api/workbench/bootstrap')['examples']
    assert any(row['id'] == 'directory_exchange' for row in examples)
    example = json.loads((root / 'examples/directory_exchange.json').read_text(encoding='utf-8'))
    ws = request(base, '/api/workbench/import', {'document': example, 'filename': 'directory_exchange.json'})
    ws_path = '/api/workbench/' + ws['id']
    persona = {**ws['persona'], 'facets': ['Sociability']}
    analyzed = request(base, ws_path + '/contextualize', {'revision': ws['revision'], 'persona': persona})
    result = analyzed['result']
    assert result['status'] == 'complete' and result['is_final'] is True, result
    assert [(p['source'], p['target']) for p in result['preferences']] == [('T1', 'T2')], result
    exported = request(base, ws_path + '/export')
    assert exported['source_document'] == example
    assert exported['result']['preferences'] == result['preferences']
    assert provider.stages == ['generate', 'check'], provider.stages


def main():
    with TemporaryDirectory(prefix='patpref-smoke-') as temporary:
        root = Path(temporary) / 'tool'
        copytree(ROOT, root, ignore=ignore_patterns('.git', '.env*', '__pycache__', '*.log',
                                                    'workspaces', 'sessions', 'runs', 'test-runs'))
        with ThreadingHTTPServer(('127.0.0.1', 0), TestProvider) as provider:
            provider.stages = []
            thread = Thread(target=provider.serve_forever, daemon=True)
            thread.start()
            try:
                env = {key: value for key, value in os.environ.items() if not key.upper().startswith(('PATPREF_API_', 'APATE_API_', 'PYTHONPATH'))}
                env.update(PATPREF_API_BASE_URL=f'http://127.0.0.1:{provider.server_port}/v1',
                           PATPREF_API_MODEL='local-smoke-test', PATPREF_API_KEY=token_urlsafe(24),
                           PATPREF_API_TIMEOUT='5', NO_PROXY='127.0.0.1,localhost')
                with socket() as reservation:
                    reservation.bind(('127.0.0.1', 0))
                    port = reservation.getsockname()[1]
                log_path = root / 'smoke.log'
                with log_path.open('wb') as log:
                    with Popen([sys.executable, '-B', 'run.py', '--port', str(port)], cwd=root, env=env,
                               stdin=DEVNULL, stdout=log, stderr=log) as app:
                        try:
                            check_workbench(f'http://127.0.0.1:{port}', root, provider)
                        except Exception:
                            print(log_path.read_text(encoding='utf-8', errors='replace'), file=sys.stderr)
                            raise
                        finally:
                            if app.poll() is None:
                                app.terminate()
                                app.wait(timeout=10)
            finally:
                provider.shutdown()
                thread.join()
    print('PATPREF smoke test passed: startup, import, P10 generation and checking, and JSON export.')


if __name__ == '__main__':
    main()
