"""Opt-in, durable dispatch reservations for one supervised live experiment.

No provider configuration or credentials are read here. SQLite counts every
reservation permanently, including failed and interrupted requests. The
supervisor creates the ledger and reserves a fresh run before starting a worker.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time

from . import provider


class LiveBudgetError(provider.ProviderError):
    def __init__(self, reason):
        super().__init__('Live experiment dispatch refused: ' + reason + '.', retryable=False)
        self.reason = reason


@dataclass(frozen=True)
class Limits:
    method_versions: int = 6
    case_attempts: int = 120
    physical_requests: int = 4802
    case_requests: int = 80
    probe_requests: int = 2
    global_seconds: float = 86400
    case_seconds: float = 7200

    def __post_init__(self):
        ceilings = dict(method_versions=6, case_attempts=120, physical_requests=4802,
                        case_requests=80, probe_requests=2,
                        global_seconds=86400, case_seconds=7200)
        for key, value in asdict(self).items():
            if (type(value) not in (int, float) or not 0 < value <= ceilings[key]
                    or (key not in ('global_seconds', 'case_seconds') and type(value) is not int)):
                raise ValueError('Invalid live limit: ' + key)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()


class Ledger:
    def __init__(self, path, *, clock=time.time):
        self.path = Path(path).resolve()
        self.clock = clock

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(str(self.path), timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA busy_timeout=30000')
        connection.execute('PRAGMA synchronous=FULL')
        try:
            with connection:
                connection.execute('BEGIN IMMEDIATE')
                yield connection
        finally:
            connection.close()

    def initialize(self, plan_sha256, started_at_epoch, *, limits=None, stop_path=None):
        limits = limits or Limits()
        if (not isinstance(plan_sha256, str) or len(plan_sha256) != 64
                or type(started_at_epoch) not in (int, float)
                or not 0 < started_at_epoch < float('inf')):
            raise ValueError('A plan hash and finite original UTC epoch are required.')
        config = {'plan_sha256': plan_sha256, 'started_at_epoch': started_at_epoch,
                  'limits': asdict(limits),
                  'stop_path': str(Path(stop_path).resolve()) if stop_path else None}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as con:
            con.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            existing = con.execute("SELECT value FROM metadata WHERE key='configuration'").fetchone()
            if existing:
                if json.loads(existing['value']) != config:
                    raise ValueError('Existing live plan, limits and original start time are immutable.')
                return
            con.execute('CREATE TABLE methods (version TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, registered_at REAL NOT NULL)')
            con.execute('''CREATE TABLE runs (run_id TEXT PRIMARY KEY, kind TEXT NOT NULL,
                case_id TEXT, method_version TEXT, revision TEXT NOT NULL, started_at REAL NOT NULL,
                status TEXT NOT NULL, triggered_at REAL, stop_reason TEXT, finished_at REAL,
                details TEXT NOT NULL)''')
            con.execute('''CREATE TABLE requests (request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL, run_number INTEGER NOT NULL, reserved_at REAL NOT NULL,
                status TEXT NOT NULL, finished_at REAL, owner_pid INTEGER NOT NULL,
                request_json TEXT NOT NULL, request_sha256 TEXT NOT NULL,
                result_json TEXT, error_json TEXT, reported_model TEXT, usage_json TEXT)''')
            con.execute('''CREATE TABLE wire_events (event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL, observed_at REAL NOT NULL, event_json TEXT NOT NULL,
                event_sha256 TEXT NOT NULL)''')
            for key, value in [('configuration', config), ('state', {'status': 'running',
                                      'triggered_at': None, 'reason': None})]:
                con.execute('INSERT INTO metadata VALUES (?,?)', (key, _json(value)))

    @staticmethod
    def _configuration(con):
        row = con.execute("SELECT value FROM metadata WHERE key='configuration'").fetchone()
        if row is None:
            raise ValueError('The supervisor must initialize the live budget first.')
        return json.loads(row['value'])

    def _gate(self, con, run_id=None, revision=None):
        config = self._configuration(con)
        state = json.loads(con.execute("SELECT value FROM metadata WHERE key='state'").fetchone()['value'])
        observed = self.clock()
        reason = state['reason'] if state['status'] != 'running' else None
        if reason is None and config['stop_path'] and Path(config['stop_path']).exists():
            reason = 'user_or_supervisor_stop'
        if reason is None and observed >= config['started_at_epoch'] + config['limits']['global_seconds']:
            reason = 'global_wall_clock_limit'
        if reason is not None:
            if state['status'] == 'running':
                state.update(status='stopped', reason=reason, triggered_at=observed)
                con.execute("UPDATE metadata SET value=? WHERE key='state'", (_json(state),))
            if run_id is not None:
                con.execute("""UPDATE runs SET status='stopped',triggered_at=?,stop_reason=?
                    WHERE run_id=? AND status='running'""", (state['triggered_at'], reason, run_id))
            return LiveBudgetError(reason)
        if run_id is None:
            return None
        row = con.execute('SELECT * FROM runs WHERE run_id=?', (run_id,)).fetchone()
        if row is None:
            return LiveBudgetError('unreserved_run')
        if revision is not None and row['revision'] != str(revision):
            return LiveBudgetError('stale_revision')
        if row['status'] != 'running':
            return LiveBudgetError(row['stop_reason'] or 'run_already_terminal')
        if row['kind'] == 'case' and observed >= row['started_at'] + config['limits']['case_seconds']:
            con.execute("UPDATE runs SET status='stopped',triggered_at=?,stop_reason=? WHERE run_id=?",
                        (observed, 'case_wall_clock_limit', run_id))
            return LiveBudgetError('case_wall_clock_limit')
        return None

    def check(self, run_id=None, revision=None):
        with self._connection() as con:
            error = self._gate(con, run_id, revision)
        if error:
            raise error

    def register_method(self, version, fingerprint):
        with self._connection() as con:
            error = self._gate(con)
            row = con.execute('SELECT fingerprint FROM methods WHERE version=?', (version,)).fetchone()
            if not error and row and row['fingerprint'] != fingerprint:
                error = LiveBudgetError('frozen_method_identity_changed')
            if not error and not row:
                limit = self._configuration(con)['limits']['method_versions']
                if con.execute('SELECT COUNT(*) FROM methods').fetchone()[0] >= limit:
                    error = LiveBudgetError('method_version_limit')
                else:
                    con.execute('INSERT INTO methods VALUES (?,?,?)', (version, fingerprint, self.clock()))
        if error:
            raise error

    def _reserve_run(self, run_id, kind, case_id, method_version, revision, metadata):
        with self._connection() as con:
            error = self._gate(con)
            if not error and con.execute('SELECT 1 FROM runs WHERE run_id=?', (run_id,)).fetchone():
                error = LiveBudgetError('run_id_already_reserved')
            if not error and kind == 'case':
                config = self._configuration(con)
                if not con.execute('SELECT 1 FROM methods WHERE version=?', (method_version,)).fetchone():
                    error = LiveBudgetError('unregistered_method')
                elif con.execute("SELECT COUNT(*) FROM runs WHERE kind='case'").fetchone()[0] >= config['limits']['case_attempts']:
                    error = LiveBudgetError('case_attempt_limit')
                elif con.execute('SELECT COUNT(*) FROM requests').fetchone()[0] >= config['limits']['physical_requests']:
                    error = LiveBudgetError('global_physical_request_limit')
            if not error:
                con.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,NULL,NULL,NULL,?)',
                            (run_id, kind, case_id, method_version, str(revision), self.clock(),
                             'running', _json(metadata or {})))
        if error:
            raise error

    def reserve_case(self, run_id, case_id, method_version, *, revision='1', metadata=None):
        self._reserve_run(run_id, 'case', case_id, method_version, revision, metadata)

    def reserve_probe(self, run_id, *, revision='1', metadata=None):
        self._reserve_run(run_id, 'probe', None, None, revision, metadata)

    def set_revision(self, run_id, revision):
        """Supervisor invalidation; old in-flight replies remain in their own run."""
        with self._connection() as con:
            cursor = con.execute('UPDATE runs SET revision=? WHERE run_id=?', (str(revision), run_id))
            if cursor.rowcount != 1:
                raise ValueError('Unknown live run.')

    def reserve_request(self, run_id, revision, arguments):
        with self._connection() as con:
            error = self._gate(con, run_id, revision)
            config = self._configuration(con)
            run = con.execute('SELECT * FROM runs WHERE run_id=?', (run_id,)).fetchone()
            if not error and con.execute("SELECT 1 FROM requests WHERE status='reserved' LIMIT 1").fetchone():
                error = LiveBudgetError('another_physical_request_in_flight')
            if not error and con.execute('SELECT COUNT(*) FROM requests').fetchone()[0] >= config['limits']['physical_requests']:
                error = LiveBudgetError('global_physical_request_limit')
            count = con.execute('SELECT COUNT(*) FROM requests WHERE run_id=?', (run_id,)).fetchone()[0]
            if not error and run['kind'] == 'case' and count >= config['limits']['case_requests']:
                error = LiveBudgetError('case_physical_request_limit')
            if not error and run['kind'] == 'probe':
                probes = con.execute("SELECT COUNT(*) FROM requests JOIN runs USING(run_id) WHERE runs.kind='probe'").fetchone()[0]
                if probes >= config['limits']['probe_requests']:
                    error = LiveBudgetError('capability_probe_request_limit')
            if not error:
                cursor = con.execute('''INSERT INTO requests
                    (run_id,run_number,reserved_at,status,owner_pid,request_json,request_sha256)
                    VALUES (?,?,?,'reserved',?,?,?)''',
                    (run_id, count + 1, self.clock(), os.getpid(), _json(arguments), _digest(arguments)))
                request_id = cursor.lastrowid
        if error:
            raise error
        return request_id

    def wire(self, request_id, event):
        # Forwarding to the normal archive happens separately. Invalid injected
        # data is retained explicitly without pretending it was original JSON.
        try:
            raw = _json(event)
            raw.encode('utf-8')
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raw = json.dumps({'format': 'python-repr-not-json', 'representation': repr(event)},
                             ensure_ascii=True, sort_keys=True)
        with self._connection() as con:
            con.execute('INSERT INTO wire_events(request_id,observed_at,event_json,event_sha256) VALUES (?,?,?,?)',
                        (request_id, self.clock(), raw, hashlib.sha256(raw.encode('utf-8')).hexdigest()))

    def finish_request(self, request_id, *, result=None, error=None):
        observed = self.clock()
        # The raw wire remains the authority. Transport-level return is a
        # separate working representation, and may not be serializable.
        try:
            result_json = _json(list(result) if isinstance(result, tuple) else result)
            result_json.encode('utf-8')
        except (ValueError, TypeError, UnicodeError, RecursionError):
            result_json = json.dumps({'format': 'python-repr-not-json', 'representation': repr(result)}, ensure_ascii=True)
        with self._connection() as con:
            events = [json.loads(row[0]) for row in con.execute(
                'SELECT event_json FROM wire_events WHERE request_id=? ORDER BY event_id', (request_id,))]
            envelope = next((e['envelope'] for e in reversed(events)
                             if e.get('event') == 'response_envelope' and isinstance(e.get('envelope'), dict)), {})
            cursor = con.execute('''UPDATE requests SET status=?,finished_at=?,result_json=?,error_json=?,
                reported_model=?,usage_json=? WHERE request_id=? AND status='reserved' ''',
                ('error' if error else 'success', observed, result_json,
                 _json(error) if error else None, envelope.get('model'),
                 _json(envelope.get('usage')) if envelope.get('usage') is not None else None, request_id))
            if cursor.rowcount != 1:
                raise ValueError('Request is missing or already finished; reservations are immutable.')

    def finish_run(self, run_id, status, *, details=None):
        with self._connection() as con:
            # Inspect stop/deadline before a caller can mark a late result
            # complete. Completed earlier runs are not changed by this gate.
            self._gate(con, run_id)
            row = con.execute('SELECT * FROM runs WHERE run_id=?', (run_id,)).fetchone()
            if row is None or row['finished_at'] is not None:
                raise ValueError('Run is missing or already finished.')
            values = json.loads(row['details'])
            values.update(details or {})
            values['observed_terminal_status'] = status
            values['observed_wall_clock_seconds'] = self.clock() - row['started_at']
            config = self._configuration(con)
            deadline = (row['started_at'] + config['limits']['case_seconds']
                        if row['stop_reason'] == 'case_wall_clock_limit' else
                        config['started_at_epoch'] + config['limits']['global_seconds']
                        if row['stop_reason'] == 'global_wall_clock_limit' else row['triggered_at'])
            values['deadline_at_epoch'] = deadline
            values['overrun_seconds'] = max(0, self.clock() - deadline) if deadline is not None else 0
            con.execute('UPDATE runs SET status=?,finished_at=?,details=? WHERE run_id=?',
                        (row['status'] if row['stop_reason'] else status, self.clock(), _json(values), run_id))

    def mark_request_uncertain(self, request_id, reason):
        """Explicit recovery after supervisor checks a dead worker/HTTP timeout.

        This never refunds a slot or repeats a request. The supervisor must log
        its recovery evidence; remote completion/usage remain unknown.
        """
        with self._connection() as con:
            cursor = con.execute("UPDATE requests SET status='uncertain',error_json=? WHERE request_id=? AND status='reserved'",
                                 (_json({'reason': reason, 'remote_completion': None, 'usage': None}), request_id))
            if cursor.rowcount != 1:
                raise ValueError('Only an unresolved reservation can become uncertain.')

    def snapshot(self):
        with self._connection() as con:
            config = self._configuration(con)
            state = json.loads(con.execute("SELECT value FROM metadata WHERE key='state'").fetchone()['value'])
            methods = [dict(row) for row in con.execute('SELECT * FROM methods ORDER BY registered_at,version')]
            runs = [dict(row) for row in con.execute('SELECT * FROM runs ORDER BY started_at,run_id')]
            requests = [dict(row) for row in con.execute('''SELECT request_id,run_id,run_number,reserved_at,status,
                finished_at,owner_pid,request_sha256,reported_model,usage_json,error_json
                FROM requests ORDER BY request_id''')]
        return {'configuration': config, 'state': state, 'methods': methods, 'runs': runs,
                'requests': requests, 'counts': {'method_versions': len(methods),
                    'case_attempts': sum(row['kind'] == 'case' for row in runs),
                    'physical_requests': len(requests),
                    'uncertain_requests': sum(row['status'] in ('reserved', 'uncertain') for row in requests)}}


class GuardedTransport:
    def __init__(self, transport, ledger, run_id, revision):
        self.transport, self.ledger = transport, ledger
        self.run_id, self.revision = run_id, str(revision)

    def check(self):
        self.ledger.check(self.run_id, self.revision)

    def reserve(self, instruction, payload, **options):
        arguments = {'instruction': instruction, 'payload': deepcopy(payload), 'options': deepcopy(options)}
        return self.ledger.reserve_request(self.run_id, self.revision, arguments)

    def __call__(self, instruction, payload, **options):
        request_id = self.reserve(instruction, payload, **options)
        return self.invoke_reserved(request_id, instruction, payload, **options)

    def invoke_reserved(self, request_id, instruction, payload, **options):
        outer = provider._REQUEST_AUDIT.get()
        def capture(event):
            self.ledger.wire(request_id, event)
            if outer is not None:
                outer(deepcopy(event))
        result, error = None, None
        try:
            with provider.request_audit(capture):
                result = self.transport(instruction, deepcopy(payload), **deepcopy(options))
            return result
        except BaseException as exc:
            # Error text from arbitrary code can contain credentials; only the
            # adapter's bounded errors may supply a message to the ledger.
            error = {'type': type(exc).__name__,
                     'message': str(exc) if isinstance(exc, provider.ProviderError) else None,
                     'retryable': bool(getattr(exc, 'retryable', False))}
            raise
        finally:
            self.ledger.finish_request(request_id, result=result, error=error)
            # Deadline/stop/stale inspection is intentionally performed by the
            # caller after saving the returned response and its raw wire.


def environment_transport(transport):
    """Wrap only when explicitly bound to a pre-reserved supervisor run."""
    if isinstance(transport, GuardedTransport):
        return transport
    db = os.environ.get('APATE_LIVE_BUDGET_DB')
    run_id = os.environ.get('APATE_LIVE_RUN_ID')
    if not db and not run_id:
        return transport
    if not db or not run_id:
        raise LiveBudgetError('incomplete_live_budget_environment')
    revision = os.environ.get('APATE_LIVE_REVISION', '1')
    ledger = Ledger(db)
    if not ledger.path.is_file():
        raise LiveBudgetError('missing_supervisor_budget_database')
    return GuardedTransport(transport, ledger, run_id, revision)
