"""Bounded, injectable transport and durable event evidence for semantic stages.

This layer schedules physical requests only. The coordinator owns semantic
review, revisions, structural checks and publication of a final model.
"""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import time

from . import provider
from .live_budget import GuardedTransport, LiveBudgetError, environment_transport


class StageFailure(ValueError):
    def __init__(self, message, *, stage=None, reason='stage_failed'):
        super().__init__(message)
        self.stage = stage
        self.reason = reason


class RunStopped(StageFailure):
    def __init__(self, message='Modeling was stopped.', *, stage=None):
        super().__init__(message, stage=stage, reason='stopped')


class RunStale(StageFailure):
    def __init__(self, message='Workspace inputs changed during modeling.', *, stage=None):
        super().__init__(message, stage=stage, reason='stale')


@dataclass(frozen=True)
class Budget:
    max_tokens: int = 18000
    semantic_revisions: int = 2
    transport_attempts: int = 10
    retry_budget_seconds: float = 600
    backoff_base: float = 5
    backoff_cap: float = 30
    stage_timeout_seconds: float | None = None
    total_requests: int = 60

    def __post_init__(self):
        for name in ('max_tokens', 'transport_attempts', 'total_requests'):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(name + ' must be a positive integer.')
        if type(self.semantic_revisions) is not int or self.semantic_revisions < 0:
            raise ValueError('semantic_revisions must be a nonnegative integer.')
        for name in ('retry_budget_seconds', 'backoff_base', 'backoff_cap', 'stage_timeout_seconds'):
            value = getattr(self, name)
            if name == 'stage_timeout_seconds' and value is None:
                continue
            if (type(value) not in (int, float) or not 0 < value < float('inf')):
                raise ValueError(name + ' must be a finite positive number.')


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def _json_value(value, ancestors=None):
    """Validate injected Python data before it enters the durable JSON ledger."""
    if value is None or type(value) in (str, bool, int):
        if isinstance(value, str):
            value.encode('utf-8')
        return
    if type(value) is float:
        if math.isfinite(value):
            return
        raise ValueError('Non-finite JSON number.')
    if type(value) not in (list, dict):
        raise ValueError('Not a JSON value.')
    ancestors = set() if ancestors is None else ancestors
    if id(value) in ancestors:
        raise ValueError('Cyclic data is not JSON.')
    ancestors.add(id(value))
    try:
        if isinstance(value, dict):
            for key, child in value.items():
                if not isinstance(key, str):
                    raise ValueError('JSON object keys must be strings.')
                key.encode('utf-8')
                _json_value(child, ancestors)
        else:
            for child in value:
                _json_value(child, ancestors)
    finally:
        ancestors.remove(id(value))


def _forensic(value):
    """An explicit Python representation, never a claim of valid original JSON."""
    return {'format': 'python-repr-not-json',
            'python_type': type(value).__module__ + '.' + type(value).__qualname__,
            'representation': repr(value)}


class StageRunner:
    def __init__(self, transport=None, budget=None, stop=None, revision_valid=None,
                 record=None, clock=time.monotonic, sleep=time.sleep):
        self.transport = environment_transport(transport if transport is not None else provider.request_json)
        self.budget = budget if budget is not None else Budget()
        self.stop = stop
        self.revision_valid = revision_valid
        self.record = record
        self.clock = clock
        self.sleep = sleep
        self.calls = []
        self.events = []
        self.started = self.clock()
        self.requests = 0
        self.stages = 0
        self._mechanical_guard_checked_at = float('-inf')

    def _emit(self, event, stage, **fields):
        value = {'event': event, 'stage': stage,
                 'run_elapsed_seconds': self.clock() - self.started, **fields}
        self.events.append(deepcopy(value))
        if self.record is not None:
            self.record(deepcopy(value))

    def _check(self, stage):
        if isinstance(self.transport, GuardedTransport):
            try:
                self.transport.check()
            except LiveBudgetError as exc:
                self._emit('run_terminated', stage, reason=exc.reason)
                if exc.reason == 'stale_revision':
                    raise RunStale(str(exc), stage=stage) from exc
                raise StageFailure(str(exc), stage=stage, reason=exc.reason) from exc
        if self.stop is not None and self.stop():
            self._emit('run_terminated', stage, reason='stopped')
            raise RunStopped(stage=stage)
        if self.revision_valid is not None and not self.revision_valid():
            self._emit('run_terminated', stage, reason='stale')
            raise RunStale(stage=stage)

    def stopping(self):
        """Cooperative search guard; full _check restores the precise reason.

        A search can examine 50,000 prefixes. Its existing local stop callback
        stays immediate; persisted deadlines and revisions are inspected at
        least every 100ms without opening a SQLite transaction per prefix.
        """
        if self.stop is not None and self.stop():
            return True
        now = self.clock()
        if now - self._mechanical_guard_checked_at < .1:
            return False
        self._mechanical_guard_checked_at = now
        if isinstance(self.transport, GuardedTransport):
            try:
                self.transport.check()
            except LiveBudgetError:
                return True
        return bool(self.revision_valid is not None and not self.revision_valid())

    def _fail(self, stage, reason, message, stage_started):
        self._emit('stage_failed', stage, reason=reason,
                   stage_elapsed_seconds=self.clock() - stage_started)
        raise StageFailure(message, stage=stage, reason=reason)

    def _timeout(self, stage, started):
        limit = self.budget.stage_timeout_seconds
        if limit is not None and self.clock() - started >= limit:
            self._fail(stage, 'stage_timeout', 'The semantic stage time budget was exhausted.', started)

    def request(self, stage, instruction, payload, schema):
        """Return one physical success, or raise with every attempt retained.

        Time budgets govern scheduling and acceptance after an in-flight call;
        they do not interrupt or extend the provider's configured HTTP timeout.
        Every invocation is a semantic stage; retries keep its stage index.
        """
        self.stages += 1
        stage_started = self.clock()
        self._emit('stage_started', stage, stage_index=self.stages)
        options = {'max_tokens': self.budget.max_tokens, 'response_schema': deepcopy(schema)}
        arguments = {'instruction': instruction, 'payload': deepcopy(payload), 'options': deepcopy(options)}
        arguments_hash = _hash(arguments)
        for attempt in range(1, self.budget.transport_attempts + 1):
            self._check(stage)
            self._timeout(stage, stage_started)
            if self.requests >= self.budget.total_requests:
                self._fail(stage, 'total_request_budget', 'The run physical request budget was exhausted.', stage_started)
            reservation_id = None
            if isinstance(self.transport, GuardedTransport):
                try:
                    reservation_id = self.transport.reserve(instruction, deepcopy(payload), **deepcopy(options))
                except LiveBudgetError as exc:
                    self._fail(stage, exc.reason, str(exc), stage_started)
            self.requests += 1
            call_started = self.clock()
            call = {'stage': stage, 'stage_index': self.stages, 'attempt': attempt,
                    'physical_request': self.requests, 'status': 'started',
                    **deepcopy(arguments), 'request_sha256': arguments_hash,
                    'actual_max_tokens': self.budget.max_tokens,
                    'wire_capture': False, 'wire_events': [],
                    'model_reported': None, 'requested_model': None, 'snapshot': None,
                    'deployment': None, 'usage': None, 'response_sha256': None,
                    'retry_scheduled': False, 'backoff_seconds': 0}
            if reservation_id is not None:
                call['global_reservation_id'] = reservation_id
            self.calls.append(call)
            self._emit('request_started', stage, call=deepcopy(call))

            def wire(event):
                call['wire_capture'] = True
                try:
                    _json_value(event)
                except (ValueError, TypeError, RecursionError):
                    safe_event = {'event': 'invalid_wire_event', 'forensic': _forensic(event)}
                    call['wire_events'].append(safe_event)
                    self._emit('wire_captured', stage, physical_request=call['physical_request'], wire=safe_event)
                    raise provider.ProviderError('The provider wire envelope was not valid finite JSON.') from None
                call['wire_events'].append(deepcopy(event))
                self._emit('wire_captured', stage, physical_request=call['physical_request'], wire=event)

            failure = None
            try:
                with provider.request_audit(wire):
                    if reservation_id is not None:
                        result = self.transport.invoke_reserved(reservation_id, instruction,
                                                               deepcopy(payload), **deepcopy(options))
                    else:
                        result = self.transport(instruction, deepcopy(payload), **deepcopy(options))
                try:
                    # The transport API uses a tuple; its response/metadata and
                    # every nested value must still inhabit the JSON domain.
                    _json_value(list(result) if type(result) is tuple else result)
                except (ValueError, TypeError, RecursionError):
                    call['transport_forensic'] = _forensic(result)
                    raise provider.ProviderError('Semantic transport returned data outside finite JSON.') from None
                call['raw_transport_result'] = deepcopy(result)
                if (not isinstance(result, tuple) or len(result) != 2
                        or not isinstance(result[0], dict) or not isinstance(result[1], dict)):
                    raise provider.ProviderError('Semantic transport must return an object and metadata.')
                response, metadata = result
                call.update(response=deepcopy(response), provider=deepcopy(metadata))
                call.update(status='success', response_sha256=_hash(response))
                envelopes = [e['envelope'] for e in call['wire_events']
                             if e.get('event') == 'response_envelope' and isinstance(e.get('envelope'), dict)]
                bodies = [e['body'] for e in call['wire_events']
                          if e.get('event') == 'request' and isinstance(e.get('body'), dict)]
                evidence = envelopes[-1] if envelopes else metadata
                call['model_reported'] = (evidence.get('model') if envelopes else evidence.get('model_reported'))
                call['requested_model'] = bodies[-1].get('model') if bodies else metadata.get('requested_model')
                if bodies:
                    call['actual_max_tokens'] = bodies[-1].get('max_tokens')
                call['usage'] = deepcopy(evidence.get('usage')) or None
                call['snapshot'] = metadata.get('snapshot')
            except provider.ProviderError as exc:
                failure = exc
                call.update(status='error', error=str(exc), retryable=exc.retryable)
            except Exception as exc:
                # Transport contract failures are not transient network failures.
                failure = exc
                call.update(status='error', error=type(exc).__name__ + ': ' + str(exc), retryable=False)
            finally:
                call.update(elapsed_seconds=self.clock() - call_started,
                            stage_elapsed_seconds=self.clock() - stage_started,
                            run_elapsed_seconds=self.clock() - self.started)
                self._emit('request_finished', stage, call=deepcopy(call))
            self._check(stage)
            self._timeout(stage, stage_started)
            if failure is None:
                self._emit('stage_completed', stage, stage_index=self.stages,
                           stage_elapsed_seconds=self.clock() - stage_started)
                return deepcopy(response), deepcopy(metadata)
            if not isinstance(failure, provider.ProviderError) or not failure.retryable:
                reason = failure.reason if isinstance(failure, LiveBudgetError) else 'transport_protocol_error'
                self._fail(stage, reason, str(failure), stage_started)
            delay = min(self.budget.backoff_cap, self.budget.backoff_base * 2 ** (attempt - 1))
            if attempt >= self.budget.transport_attempts:
                self._fail(stage, 'transport_attempts_exhausted', str(failure), stage_started)
            if self.requests >= self.budget.total_requests:
                self._fail(stage, 'total_request_budget', str(failure), stage_started)
            if self.clock() - stage_started + delay > self.budget.retry_budget_seconds:
                self._fail(stage, 'retry_budget_exhausted', str(failure), stage_started)
            if (self.budget.stage_timeout_seconds is not None
                    and self.clock() - stage_started + delay >= self.budget.stage_timeout_seconds):
                self._fail(stage, 'stage_timeout', str(failure), stage_started)
            self._check(stage)
            call.update(retry_scheduled=True, backoff_seconds=delay)
            self._emit('retry_scheduled', stage, call=deepcopy(call))
            self.sleep(delay)
            self._check(stage)
            self._timeout(stage, stage_started)
            self._emit('retry_wait_completed', stage, stage_elapsed_seconds=self.clock() - stage_started)
