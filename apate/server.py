"""Loopback-only JSON API and static browser workbench (Python standard library)."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, unquote
import json
import mimetypes
import re
import traceback
import hashlib
from . import __version__
from . import store
from .schema import FACETS, ModelError

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'web'
MAX_BODY = 10 * 1024 * 1024
SESSION_PATH = re.compile(r'^/api/session/([a-f0-9]{32})(?:/([a-z_]+))?$')
WORKBENCH_PATH = re.compile(r'^/api/workbench/([a-f0-9]{32})(?:/(contextualize|export))?$')


def frontend_revision():
    """Bind the entry document to the current local frontend assets."""
    digest = hashlib.sha256()
    for name in ('index.html', 'app.js', 'style.css', 'istar-routing.js', 'istar-viewer.js', 'vendor/pistar/manifest.json'):
        source = WEB / name
        if source.is_file():
            digest.update(source.read_bytes())
    return digest.hexdigest()[:12]

def _modules():
    from . import compiler, planner, contextualize, patterns
    return compiler, planner, contextualize, patterns

def example_list():
    result = []
    labels = {'small': 'Small service: choices, optional work and evidence',
              'seerware': 'SeerWare: multi-role preference requirements',
              'temporal_service': 'Maintenance: temporal preferences and plan comparison',
              'dependency_demo': 'Service coordination: four dependency types'}
    for path in sorted((ROOT / 'examples').glob('*.json')):
        if path.name.endswith('.candidates.json'): continue
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
            if 'model' not in payload: continue
            result.append({'id': path.stem, 'label': labels.get(path.stem, payload.get('label', payload.get('name', path.stem)))})
        except (ValueError, OSError): continue
    return result

def example_load(name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', name):
        raise ValueError('Invalid example ID.')
    path = ROOT / 'examples' / (name + '.json')
    if not path.exists(): raise KeyError('Example not found.')
    value = json.loads(path.read_text(encoding='utf-8'))
    value['example_id'] = name
    return value

class Handler(BaseHTTPRequestHandler):
    server_version = 'PATPREFWorkbench/' + __version__

    def log_message(self, fmt, *args):
        # Standard messages contain no request bodies or model credentials.
        print('%s %s' % (self.address_string(), fmt % args), flush=True)

    def _json(self, status, value, filename=None):
        raw = json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if filename: self.send_header('Content-Disposition', 'attachment; filename="' + filename + '"')
        self.end_headers()
        self.wfile.write(raw)

    def _body(self):
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + self.headers.get('Host', ''):
            raise ValueError('Only same-origin local workbench requests are accepted.')
        if 'application/json' not in self.headers.get('Content-Type', ''):
            raise ValueError('The request must use application/json.')
        length = int(self.headers.get('Content-Length', '0'))
        if length < 0 or length > MAX_BODY: raise ModelError('The request exceeds the 10 MiB limit.')
        if self.headers.get('Transfer-Encoding'): raise ValueError('Chunked requests are not supported.')
        raw = self.rfile.read(length)
        value = json.loads(raw.decode('utf-8')) if raw else {}
        if not isinstance(value, dict): raise ValueError('The request body must be a JSON object.')
        return value

    def _error(self, exc):
        if isinstance(exc, store.SessionConflict): code, label = 409, 'session_changed'
        elif isinstance(exc, KeyError): code, label = 404, 'not_found'
        elif isinstance(exc, (ValueError, ModelError, json.JSONDecodeError)): code, label = 400, 'validation_error'
        else: code, label = 500, 'internal_error'
        from .provider import ProviderError
        if isinstance(exc, ProviderError): code, label = 502, 'provider_error'
        self._json(code, {'error': {'code': label, 'message': str(exc), 'details': getattr(exc, 'details', [])}})
        if code == 500: traceback.print_exc()

    def do_GET(self):
        try:
            path = urlsplit(self.path).path
            if path == '/api/workbench/bootstrap':
                from .workbench import bootstrap
                return self._json(200, bootstrap())
            workbench_match = WORKBENCH_PATH.fullmatch(path)
            if workbench_match:
                from . import workbench
                if workbench_match[2] == 'export':
                    return self._json(200, workbench.export_workspace(workbench_match[1]), 'PATPREF-contextualized-model.json')
                if workbench_match[2] is None:
                    from .three_input import public_three_input_workspace
                    return self._json(200, public_three_input_workspace(workbench.get_workspace(workbench_match[1])))
                raise KeyError('Endpoint not found.')
            if path == '/api/health':
                return self._json(200, {'status': 'ok', 'version': __version__, 'bind': '127.0.0.1',
                                        'frontend_revision': frontend_revision()})
            if path == '/api/provider':
                from .provider import public_status
                return self._json(200, public_status())
            if path == '/api/bootstrap':
                _, planner, _, patterns = _modules()
                from .presentation import english_catalogue
                from .provider import public_status
                catalogue = english_catalogue(patterns.load_catalogue())
                entries = catalogue.get('patterns', []) if isinstance(catalogue, dict) else catalogue
                return self._json(200, {'version': __version__, 'examples': example_list(),
                    'patterns': [{'id': p['id'], 'name': p['name'], 'facets': p['facets'], 'rule_ids':p['rule_ids']} for p in entries],
                    'catalogue_overview': patterns.catalogue_overview(),
                    'facets': FACETS, 'engine': planner.engine_status(),
                    'provider': public_status()})
            if path == '/api/patterns':
                _,_,_,patterns=_modules()
                catalogue=patterns.load_catalogue()
                catalogue['machine_contracts']=patterns.machine_contracts()
                catalogue['rule_contracts']=patterns.rule_contracts()
                catalogue['catalogue_overview']=patterns.catalogue_overview()
                from .presentation import english_catalogue
                return self._json(200,english_catalogue(catalogue))
            match = SESSION_PATH.fullmatch(path)
            if match:
                session = store.get_session(match[1])
                if match[2] == 'pattern_usage':
                    from .pattern_usage import build_pattern_usage
                    from .presentation import english_usage
                    return self._json(200,english_usage(build_pattern_usage(session)))
                if match[2] == 'export': return self._json(200, session, 'apate-session.json')
                if match[2] is None:
                    from .presentation import english_session
                    return self._json(200, english_session(session))
                raise KeyError('Endpoint not found.')
            if path.startswith('/api/'): raise KeyError('Endpoint not found.')
            relative = unquote(path).lstrip('/') or 'index.html'
            target = (WEB / relative).resolve()
            if not target.is_relative_to(WEB.resolve()) or not target.is_file(): raise KeyError('Static file not found.')
            raw = target.read_bytes()
            if target == (WEB / 'index.html').resolve():
                raw = raw.replace(b'{{FRONTEND_REVISION}}', frontend_revision().encode('ascii'))
            self.send_response(200)
            self.send_header('Content-Type', (mimetypes.guess_type(str(target))[0] or 'application/octet-stream') + ('; charset=utf-8' if target.suffix in {'.html', '.js', '.css'} else ''))
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store, max-age=0')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError): pass
        except Exception as exc: self._error(exc)

    def do_PUT(self):
        try:
            match = SESSION_PATH.fullmatch(urlsplit(self.path).path)
            if not match or match[2] is not None: raise KeyError('Endpoint not found.')
            from .presentation import english_session
            self._json(200, english_session(store.update_session(match[1], self._body())))
        except Exception as exc: self._error(exc)

    def do_POST(self):
        try:
            payload = self._body()
            path = urlsplit(self.path).path
            if path == '/api/workbench/import':
                from .workbench import import_workspace
                from .three_input import public_three_input_workspace
                return self._json(201, public_three_input_workspace(import_workspace(payload.get('document'), payload.get('filename'))))
            if path == '/api/workbench/example':
                from .workbench import example_workspace
                from .three_input import public_three_input_workspace
                return self._json(201, public_three_input_workspace(example_workspace(payload.get('example_id'))))
            workbench_match = WORKBENCH_PATH.fullmatch(path)
            if workbench_match and workbench_match[2] == 'contextualize':
                from .p10_workbench import contextualize_workspace
                return self._json(200, contextualize_workspace(workbench_match[1], payload))
            if path == '/api/model/import':
                from .model_import import import_goal_model
                return self._json(200, import_goal_model(payload.get('document'), payload.get('root_id')))
            if path == '/api/model/validate':
                from .modeling import validate_workspace_model
                return self._json(200, validate_workspace_model(payload.get('model', {})))
            if path == '/api/session':
                source = example_load(payload['example_id']) if 'example_id' in payload else payload
                from .presentation import english_session
                return self._json(201, english_session(store.create_session(source)))
            match = SESSION_PATH.fullmatch(path)
            if not match or not match[2]: raise KeyError('Endpoint not found.')
            sid, action = match.groups()
            session = store.get_session(sid)
            compiler, planner, contextualize, _ = _modules()
            from .workflow import compile_session,rank_session,invalidate_after_contextualization
            if action == 'generate':
                from .provider import generate_candidates
                return self._json(200, generate_candidates(session))
            if action == 'compile':
                result = compile_session(session,payload)
            elif action == 'plan':
                compilation = compile_session(session,payload)
                limit = min(10, max(1, int(payload.get('max_plans', 3))))
                timeout = min(30, max(1, int(payload.get('timeout', 15))))
                result = planner.run_planner(compilation, max_plans=limit, timeout=timeout)
                session['compilation'], session['planner_result'] = compilation, result
            elif action == 'rank':
                result=rank_session(session,payload)
            elif action == 'prompt':
                result = contextualize.export_prompt(session)
                if isinstance(result, str): result = {'prompt': result}
                return self._json(200, result)
            elif action == 'contextualize':
                bundle = payload.get('candidate_bundle', payload if 'candidates' in payload else None)
                if bundle is not None: session['candidate_bundle'] = bundle
                result = contextualize.contextualize_session(session, bundle)
                session['result'] = result
                invalidate_after_contextualization(session)
            elif action == 'withdraw':
                if not session.get('result'): raise ValueError('There is no active support to withdraw.')
                result = contextualize.withdraw_support(session['result'], payload.get('support_id', ''))
                session['result'] = result
                invalidate_after_contextualization(session)
            else: raise KeyError('Endpoint not found.')
            store.save_session(session)
            return self._json(200, result)
        except (BrokenPipeError, ConnectionResetError): pass
        except Exception as exc: self._error(exc)

def serve(port=8765):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    print(f'PATPREF Workbench: http://127.0.0.1:{port} (local only)', flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
