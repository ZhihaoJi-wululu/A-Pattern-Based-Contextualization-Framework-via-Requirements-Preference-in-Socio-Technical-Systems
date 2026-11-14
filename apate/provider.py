"""Small synchronous adapter for the configured OpenAI-compatible provider.

Preference candidates are staged against the imported goal model. The
independent contextualization service retains ownership of acceptance.
"""
from copy import deepcopy
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler
import json
import base64
import hashlib
import math
import os
import re
import time

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / '.env.local'
GENERATION_MAX_TOKENS = 12000
_REQUEST_AUDIT = ContextVar('apate_provider_request_audit', default=None)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A redirect would issue an unreserved second HTTP request. Surface
        # it as a non-retryable HTTP failure under the frozen policy instead.
        return None


urlopen = build_opener(_NoRedirect()).open


@contextmanager
def request_audit(callback):
    """Capture this context's wire evidence without exposing request headers.

    Constructing or entering this context does not inspect provider settings.
    Nested and concurrent callers restore their own hooks independently.
    """
    token = _REQUEST_AUDIT.set(callback)
    try:
        yield
    finally:
        _REQUEST_AUDIT.reset(token)


def _audit_request(event):
    callback = _REQUEST_AUDIT.get()
    if callback is not None:
        callback(deepcopy(event))


class ProviderError(ValueError):
    """A bounded, user-readable model request failure."""

    def __init__(self, message, *, retryable=False):
        super().__init__(message)
        self.retryable = bool(retryable)


def configuration():
    values = {}
    if ENV_FILE.is_file():
        for line in ENV_FILE.read_text(encoding='utf-8-sig').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key, value = line.split('=', 1)
                values[key.strip()] = value.strip().strip('\"\'')
    def get(name, default=''):
        return os.environ.get(name, values.get(name, default))
    try:
        timeout = min(180, max(5, int(get('PATPREF_API_TIMEOUT', '90'))))
    except ValueError:
        timeout = 90
    return {'base_url': get('PATPREF_API_BASE_URL').rstrip('/'),
            'model': get('PATPREF_API_MODEL'),
            'key': get('PATPREF_API_KEY'), 'timeout': timeout}


def public_status():
    cfg = configuration()
    return {'kind': 'openai-compatible', 'model': cfg['model'], 'base_url': cfg['base_url'],
            'configured': all(cfg[key] for key in ('base_url', 'model', 'key')), 'automatic_api_calls': False,
            'invocation': 'Explicit preference-candidate generation only', 'timeout_seconds': cfg['timeout'],
            'temperature': 0, 'candidate_workers': 3, 'maximum_concerns_per_worker': 4,
            'generation_max_tokens': GENERATION_MAX_TOKENS}


def _strict_json_loads(content):
    """Decode actual JSON without duplicate keys or non-finite numbers."""
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('Duplicate provider JSON key.')
            value[key] = item
        return value
    def finite_constant(value):
        raise ValueError('Non-finite provider JSON constant.')
    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError('Provider JSON number overflowed the finite range.')
        return number
    return json.loads(content, object_pairs_hook=unique, parse_constant=finite_constant,
                      parse_float=finite_float)


def parse_object(content):
    if isinstance(content, list):
        content = ''.join(p.get('text', '') for p in content if isinstance(p, dict))
    if not isinstance(content, str) or not content.strip():
        raise ProviderError('The provider returned no text. Try the request again.')
    content = content.strip()
    if content.startswith('```'):
        content = re.sub(r'^```(?:json)?\s*|\s*```$', '', content, flags=re.I)
    try:
        value = _strict_json_loads(content)
    except (ValueError, TypeError):
        raise ProviderError('The provider response is not a complete JSON object. No preference candidates were applied.') from None
    if not isinstance(value, dict):
        raise ProviderError('The provider must return one JSON object.')
    return value


def request_json(instruction, payload, *, max_tokens=12000, response_schema=None):
    cfg = configuration()
    if not all(cfg[key] for key in ('base_url', 'model', 'key')):
        raise ProviderError('Set PATPREF_API_BASE_URL, PATPREF_API_MODEL and PATPREF_API_KEY in .env.local.')
    if not cfg['base_url'].startswith(('https://', 'http://127.0.0.1:', 'http://localhost:')):
        raise ProviderError('Use an HTTPS provider URL or a local loopback endpoint.')
    body = {'model': cfg['model'], 'messages': [
        {'role': 'system', 'content': instruction + '\nReturn only a valid JSON object. All explanatory text and labels must be English.'},
        {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
        'max_tokens': max_tokens, 'stream': False, 'temperature': 0}
    if response_schema is not None:
        body['response_format'] = {'type': 'json_schema', 'json_schema': {
            'name': 'apate_goal_model_completion', 'strict': True, 'schema': response_schema}}
    request_bytes = json.dumps(body).encode('utf-8')
    _audit_request({'event': 'request', 'body': body,
                    'body_utf8': request_bytes.decode('utf-8'),
                    'body_sha256': hashlib.sha256(request_bytes).hexdigest(),
                    'timeout_seconds': cfg['timeout']})
    req = Request(cfg['base_url'] + '/chat/completions',
                  data=request_bytes,
                  headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                           'Authorization': 'Bearer ' + cfg['key']}, method='POST')
    start = time.monotonic()
    try:
        with urlopen(req, timeout=cfg['timeout']) as response:
            raw = response.read(4 * 1024 * 1024 + 1)
        _audit_request({'event': 'response_bytes',
                        'raw_response_base64': base64.b64encode(raw).decode('ascii'),
                        'raw_response_sha256': hashlib.sha256(raw).hexdigest(),
                        'elapsed_seconds': time.monotonic() - start})
        if len(raw) > 4 * 1024 * 1024:
            raise ProviderError('The provider response exceeded the prototype response limit.')
        try:
            envelope = _strict_json_loads(raw)
        except (ValueError, TypeError):
            raise ProviderError('The provider returned an unexpected response format.') from None
        _audit_request({'event': 'response_envelope', 'envelope': envelope,
                        'elapsed_seconds': time.monotonic() - start})
        choices = envelope.get('choices', [])
        if not choices:
            raise ProviderError('The provider returned no completion choices.')
        if choices[0].get('finish_reason') == 'length':
            raise ProviderError('The provider response was truncated. Use a smaller candidate scope.')
        value = parse_object(choices[0].get('message', {}).get('content'))
    except HTTPError as exc:
        # Keep private failure evidence while public errors remain bounded.
        # Some gateways echo the supplied key; never retain that plaintext.
        try:
            error_raw = exc.read(4 * 1024 * 1024 + 1)
            key_bytes = cfg['key'].encode('utf-8')
            redacted = bool(key_bytes and key_bytes in error_raw)
            stored = error_raw.replace(key_bytes, b'[REDACTED]') if redacted else error_raw
            _audit_request({'event': 'http_error_response_bytes', 'status_code': exc.code,
                            'response_base64': base64.b64encode(stored).decode('ascii'),
                            'response_sha256': hashlib.sha256(error_raw).hexdigest(),
                            'stored_sha256': hashlib.sha256(stored).hexdigest(),
                            'credential_redacted': redacted,
                            'capture_limit_exceeded': len(error_raw) > 4 * 1024 * 1024,
                            'elapsed_seconds': time.monotonic() - start})
        except (OSError, TypeError, AttributeError):
            _audit_request({'event': 'http_error_body_unavailable', 'status_code': exc.code})
        _audit_request({'event': 'http_error', 'status_code': exc.code,
                        'elapsed_seconds': time.monotonic() - start})
        messages = {401: 'Provider authentication failed.', 403: 'The provider denied access.',
                    402: 'The provider account has insufficient credits.', 429: 'The provider is rate limited.'}
        raise ProviderError(messages.get(exc.code, f'The provider returned HTTP {exc.code}.'),
                            retryable=exc.code in (408, 429) or exc.code >= 500) from None
    except (TimeoutError, URLError, OSError) as exc:
        cause = exc.reason if isinstance(exc, URLError) else exc
        _audit_request({'event': 'network_error', 'exception_type': type(exc).__name__,
                        'cause_type': type(cause).__name__,
                        'errno': getattr(cause, 'errno', None),
                        'winerror': getattr(cause, 'winerror', None),
                        'timeout_seconds': cfg['timeout'],
                        'elapsed_seconds': time.monotonic() - start})
        raise ProviderError('The provider could not be reached within the configured time limit.', retryable=True) from None
    except (json.JSONDecodeError, AttributeError, IndexError, TypeError, KeyError):
        raise ProviderError('The provider returned an unexpected response format.') from None
    metadata = {'kind': 'openai-compatible', 'model_reported': envelope.get('model'),
                'requested_model': cfg['model'], 'snapshot': None,
                'request_id': envelope.get('id'), 'elapsed_seconds': round(time.monotonic()-start, 3),
                'usage': envelope.get('usage') or None, 'temperature': 0}
    if response_schema is not None:
        metadata['response_format'] = 'json_schema'
    return value, metadata


def _referenced_sources(session):
    """Send every cited span once; retain the complete sources in the workspace."""
    needed = {}
    def visit(value):
        if isinstance(value, dict):
            source, span = value.get('source_id'), value.get('span_id')
            if isinstance(source, str) and isinstance(span, str):
                needed.setdefault(source, set()).add(span)
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    for field in ('persona', 'context', 'concerns'):
        visit(session.get(field, {}))
    output = {}
    for key, spans in needed.items():
        source = session.get('sources', {}).get(key, {})
        output[key] = {field: deepcopy(source[field]) for field in ('kind', 'label') if field in source}
        if source.get('kind') == 'user_provided_persona_context':
            # Completion must see omitted statements too, not only the spans
            # already selected by the first extraction pass.
            spans = set(source.get('spans', {}))
        output[key]['spans'] = {span: deepcopy(source.get('spans', {}).get(span)) for span in sorted(spans)}
    return output


def _decision_points(session, *, include_unassigned=False):
    """Expose existing implementations and optional work within the active role."""
    from .contextualize import _ModelView
    view = _ModelView(session['model'])
    role = (session.get('persona', {}).get('role_ids') or [None])[0]
    choices = []
    for parent, refinement in view.refs.items():
        if refinement['kind'] != 'OR' or view.nodes[parent]['kind'] != 'goal':
            continue
        children = refinement['children']
        authorized = all(view.authorized(role, child) for child in children)
        if authorized or include_unassigned:
            choices.append({'parent': parent, 'alternatives': list(children),
                            'implementation_tasks': {child: sorted(view.leaves(child)) for child in children},
                            'within_active_role': authorized})
    optional = [key for key, node in view.nodes.items()
                if node['kind'] in ('goal', 'task')
                and view.optional_scope(key) is not None
                and (include_unassigned or view.authorized(role, key))]
    optional_scopes = {}
    for key in optional:
        optional_scopes.setdefault(view.optional_scope(key), []).append(key)
    return {'role_id': role, 'choices': choices, 'optional_elements': optional,
            'optional_scopes': [{'scope': scope, 'available_anchors': anchors}
                                for scope, anchors in optional_scopes.items()],
            'current_work': deepcopy(session.get('context', {}).get('current_work', {}))}


def _quality_concern_references(session):
    """Resolve an existing quality ID only through its registered criterion."""
    choices = {}
    for identity, concern in session.get('concerns', {}).items():
        if not isinstance(concern, dict) or concern.get('origin') != 'imported_quality_contributions':
            continue
        quality = concern.get('quality_id')
        if (isinstance(quality, str) and quality in session['model']['nodes']
                and session['model']['nodes'][quality]['kind'] in ('softgoal', 'hard_preference')
                and isinstance(concern.get('ast'), dict)):
            choices.setdefault(quality, []).append(identity)
    return {quality: ids[0] for quality, ids in choices.items() if len(ids) == 1}


def generate_candidates(session):
    from .provider_partition import complete_partitions
    return complete_partitions(session, _generate_candidates_single)


def _unique_candidate_ids(candidates, reviews, reference_bindings):
    """Disambiguate opaque output IDs without changing any candidate binding."""
    reserved = {c.get('id') for c in candidates if isinstance(c, dict) and isinstance(c.get('id'), str)}
    used = set()
    mapping = {}
    trace = []
    for candidate in candidates:
        if not isinstance(candidate, dict) or not isinstance(candidate.get('id'), str):
            continue
        original = candidate['id']
        identity = original
        suffix = 2
        while identity in used:
            identity = original + '__' + str(suffix)
            suffix += 1
            if identity in reserved:
                identity = original
        used.add(identity)
        candidate['id'] = identity
        mapping.setdefault((original, candidate.get('concern_id')), []).append(identity)
        if identity != original:
            trace.append({'original_candidate_id': original, 'candidate_id': identity,
                          'concern_id': candidate.get('concern_id')})
    rewritten = deepcopy(reviews)
    if isinstance(rewritten, dict):
        for concern, review in rewritten.items():
            if isinstance(review, dict) and isinstance(review.get('candidate_ids'), list):
                review['candidate_ids'] = [new for old in review['candidate_ids']
                    for new in mapping.get((old, concern), [old])]
    bindings = []
    for binding in reference_bindings:
        for identity in mapping.get((binding.get('candidate_id'), binding.get('registered_concern_id')),
                                    [binding.get('candidate_id')]):
            bindings.append({**binding, 'candidate_id': identity})
    return rewritten, bindings, trace


def _generate_candidates_single(session):
    from .patterns import machine_contracts, rule_contracts
    from .provider_schema import completion_schema, primary_concern_ids
    from .schema import business_projection, model_hash
    template = {'schema_version': 'apate.candidates.v1', 'model_hash': model_hash(session['model']),
                'actor_id': session['persona']['actor_id'],
                'role_id': (session['persona'].get('role_ids') or [None])[0],
                'context_id': session['context']['id'], 'candidates': []}
    packet = {'schema_version': 'apate.live-completion.v2', 'candidate_template': template,
              'model_hash': template['model_hash'], 'model': business_projection(session['model']),
              'persona': deepcopy(session['persona']), 'context': deepcopy(session['context']),
              'sources': _referenced_sources(session), 'concerns': deepcopy(session.get('concerns', {})),
              'patterns': machine_contracts(), 'rules': rule_contracts(),
              'decision_points': _decision_points(session),
              'quality_concern_references': _quality_concern_references(session),
              'witness_summary': {'provided': len(session.get('witnesses', [])),
                                  'comparison': 'The independent validator retains all complete sequences and derives comparable pairs.'}}
    selected = set(session.get('persona', {}).get('facets', []))
    packet['patterns'] = {key: value for key, value in packet['patterns'].items()
                          if selected.intersection(value.get('facets', []))}
    allowed_rules = {rule for pattern in packet['patterns'].values() for rule in pattern.get('rule_ids', [])}
    packet['rules'] = {key: value for key, value in packet['rules'].items() if key in allowed_rules}
    packet['required_concern_reviews'] = primary_concern_ids(session)
    if 'completion_partition' in session:
        packet['completion_partition'] = deepcopy(session['completion_partition'])
    # The manual research export contains repeated compiler and catalogue views.
    # The live provider needs the current facet context and complete executable
    # rule contracts; duplicate display branches add latency without evidence.
    for pattern in packet['patterns'].values():
        pattern.pop('branches', None)
        cps = pattern.get('CPS', {})
        pattern['CPS'] = {key: deepcopy(cps[key]) for key in ('Context', 'Problem') if key in cps}
    # The complete business projection includes ownership, decomposition,
    # dependencies, constraints and contributions. Compiler duplicates and full
    # witness transcripts are unnecessary for proposing model bindings.
    packet['candidate_schema_examples'] = {
        'choice': {'id': 'C1', 'pattern_id': 'ONE_CURRENT_PATTERN_ID', 'rule_id': 'ONE_ALLOWED_RULE_ID',
                   'kind': 'choice', 'source': 'EXISTING_PREFERRED_TASK_ID', 'target': 'EXISTING_OTHER_TASK_ID',
                   'concern_id': 'EXISTING_CONCERN_ID', 'fact_bindings': {'REQUIRED_PREDICATE': 'EXISTING_FACT_ID'}},
        'optional_participation': {'id': 'C2', 'pattern_id': 'ONE_CURRENT_PATTERN_ID', 'rule_id': 'ONE_ALLOWED_RULE_ID',
                   'kind': 'optional_participation', 'formula': 'sometime', 'x': 'EXISTING_OPTIONAL_TASK_ID',
                   'concern_id': 'EXISTING_CONCERN_ID', 'fact_bindings': {'REQUIRED_PREDICATE': 'EXISTING_FACT_ID'}},
        'temporal': {'id': 'C3', 'pattern_id': 'ONE_CURRENT_PATTERN_ID', 'rule_id': 'ONE_ALLOWED_RULE_ID',
                   'kind': 'temporal', 'formula': 'precedes', 'x': 'EXISTING_TASK_ID', 'y': 'EXISTING_TASK_ID',
                   'concern_id': 'EXISTING_CONCERN_ID', 'fact_bindings': {'REQUIRED_PREDICATE': 'EXISTING_FACT_ID'}}}
    instruction = '''Complete the preference requirements over the supplied Goal Model.
Return {candidates:[...], reviewed_rule_ids:[...],
deferred:[{rule_id,missing_predicates,reason}],
evidence_gaps:[{rule_id,scope_ids,missing_predicates,evidence_refs:[{source_id,span_id}]}],
concern_reviews:{EXISTING_CONCERN_ID:{status,candidate_ids:[...]}}}.
The imported Goal Model is fixed. Propose preference bindings only, using its
complete existing elements, AND/OR decomposition, actor/role scopes, dependencies,
hard constraints and operational contribution effects. Never add business nodes.
When completion_partition is present, you are one pattern expert assigned only
its listed concern IDs. Other experts handle other criteria over the same global
model. Review rules against your assigned criteria, preserve cross-role dependencies
and both ends of temporal criteria, and emit no preference for an unassigned
criterion. Global model content is read-only context, not additional output work.
Systematically inspect every supplied rule and each relevant existing decision
point, optional element and recorded current-work continuation; a rule can apply
at several locations. Include every supported binding, not one example per facet.
Review every criterion in required_concern_reviews separately, including multiple
criteria supported by the same rule. For each, return status proposed with the IDs
of its candidates, not_applicable when no compatible supported preference exists,
or needs_information when its required evidence is absent. Proposed candidate IDs
must exist and use that exact registered concern. This review does not authorize
inventing a preference or filling a missing condition.
Use only current context facts with value true and matching predicate IDs. Respect
their scope_ids: evidence for one task/comparison cannot license unrelated work.
Unknown, absent, contradictory or false gates never authorize a candidate. Record
the missing conditions in deferred. An existing task or facet checkbox is not
independent evidence. The selected concern's explicit AST must measure this rule's
specific operational effect; an unrelated positive outcome cannot substitute.
The criterion's declared outcome is binding. A reciprocity criterion measures
reciprocal interaction; a learning criterion must measure progress on the prior
learning question across its approved channels. Completing a communication task
does not by itself turn its reciprocity criterion into a learning criterion.
Retain distinct rule supports only when each matches that criterion's outcome.
Distinguish an existing model location with missing context evidence from a rule
that has no compatible activity or registered operational effect in this M0. For
the latter, report the inapplicability reason with missing_predicates: [], rather
than requesting new model elements or unsupported conditions to activate it.
The current user-provided source contains every original sentence, including
statements the extractor may have missed. If a required fact is absent BUT that
text explicitly states the condition for this decision, add an evidence_gaps
record with the exact supplied source/span IDs. Do not assert the fact yourself
or authorize a candidate with it. A separate bounded extraction pass will verify
those statements. Never request a gap completion merely because the desired
candidate needs a condition: unstated conditions stay deferred, with no gap entry.
Do not output witness_pairs. All complete execution sequences remain in the
independent validator, which derives comparable pairs and checks strict effects,
feasibility, hard constraints and current-role discretion before acceptance.
If none qualifies, return candidates: []. This does not assert complete coverage.
Never create fact_bindings that do not refer to the corresponding required predicate.
Never execute a descriptive case branch: only listed rule contracts are executable.
Use only the first currently assigned role for this generation pass. Preserve unknowns.
Follow candidate_schema_examples EXACTLY for field names and value types:
The response schema restricts bindings to actual OR alternatives, optional AND
scopes and current-role work. An activity must not contain its own independent
review. If a registered criterion directly attains one optional node, use that
exact node as its participation anchor, preserving the declared activity scope.
fact_bindings is an OBJECT mapping predicate IDs to fact IDs, never an array.
Every candidate has an id, canonical pattern_id and one explicit rule_id from it.
concern_id must name a registered criterion. quality_concern_references maps
existing quality nodes to their registered criterion IDs; a quality node ID itself
is not a new criterion, and a task label is never a substitute for a concern AST.
Choice uses top-level source and target; NEVER invent a relation wrapper.
Participation and temporal formulas are enum strings such as sometime, never,
precedes or require_before, NEVER function strings like sometime(task).
Use x and y for formula arguments, never task_id.
Use current_work_id for Productiveness and an existing independent review_node for
Creative Imagination. Bind the most specific existing activity named by the
evidence; use a whole optional goal when the commitment covers its whole subtree.
A generation criterion can include both the persona's generation task and
another actor's independent review. Bind the generation task as x and the
external task as review_node; the persona need not own the independent reviewer.
When the supplied situation identifies corresponding task IDs in two implementation
branches, locate the choice on those existing activity tasks, rather than replacing
them with enclosing branch goals. implementation_tasks supplies the branch-to-task
mapping; the registered concern and source evidence determine the matching tasks.
Keep distinct pattern supports separate; add no weights.
The schema example placeholder IDs are illustrative; replace them with supplied existing IDs.'''
    value, provider = request_json(instruction, packet,
        max_tokens=GENERATION_MAX_TOKENS,
        response_schema=completion_schema(session, packet))
    bundle = value.get('candidate_bundle', value)
    if not isinstance(bundle, dict) or not isinstance(bundle.get('candidates'), list):
        raise ProviderError('The provider did not return a candidate list. No candidates were applied.')
    bundle = deepcopy(bundle)
    reference_bindings = []
    for candidate in bundle['candidates']:
        if not isinstance(candidate, dict):
            continue
        reference = candidate.get('concern_id')
        if (isinstance(reference, str) and reference not in session.get('concerns', {})
                and reference in packet['quality_concern_references']):
            registered = packet['quality_concern_references'][reference]
            candidate['concern_id'] = registered
            reference_bindings.append({'candidate_id': candidate.get('id'), 'field': 'concern_id',
                                       'source_quality_id': reference, 'registered_concern_id': registered})
    raw_reviews, reference_bindings, candidate_id_bindings = _unique_candidate_ids(
        bundle['candidates'], value.get('concern_reviews', {}), reference_bindings)
    template = packet['candidate_template']
    # Bind the envelope to actual current inputs; candidate contents still face
    # independent validation and cannot create acceptance by claiming provenance.
    for key in ('schema_version', 'actor_id', 'role_id', 'context_id'):
        bundle[key] = template[key]
    bundle['model_hash'] = model_hash(session['model'])
    bundle['provider'] = provider
    reviewed = value.get('reviewed_rule_ids', [])
    reviewed = sorted({rule for rule in reviewed if isinstance(rule, str) and rule in packet['rules']}) if isinstance(reviewed, list) else []
    deferred = []
    for item in value.get('deferred', []) if isinstance(value.get('deferred', []), list) else []:
        if not isinstance(item, dict) or not isinstance(item.get('rule_id'), str) or item['rule_id'] not in packet['rules']:
            continue
        rule = item['rule_id']; missing = item.get('missing_predicates', [])
        if not isinstance(missing, list):
            continue
        deferred.append({'rule_id': rule,
                         'missing_predicates': sorted({p for p in missing if isinstance(p, str) and p in packet['rules'][rule]['required_predicates']}),
                         'reason': str(item.get('reason', ''))[:500]})
    gaps = []
    for item in value.get('evidence_gaps', []) if isinstance(value.get('evidence_gaps', []), list) else []:
        if not isinstance(item, dict) or not isinstance(item.get('rule_id'), str) or item['rule_id'] not in packet['rules']:
            continue
        rule = item['rule_id']; scope = item.get('scope_ids'); predicates = item.get('missing_predicates'); refs = item.get('evidence_refs')
        if (not isinstance(scope, list) or not scope or any(not isinstance(k, str) or k not in packet['model']['nodes'] or packet['model']['nodes'][k]['kind'] not in ('goal', 'task') for k in scope)
                or not isinstance(predicates, list) or not predicates or any(p not in packet['rules'][rule]['required_predicates'] for p in predicates)
                or not isinstance(refs, list) or not refs):
            continue
        checked_refs = []
        for ref in refs:
            if not isinstance(ref, dict) or not isinstance(ref.get('source_id'), str):
                continue
            source = packet['sources'].get(ref.get('source_id'), {})
            if source.get('kind') == 'user_provided_persona_context' and isinstance(ref.get('span_id'), str) and ref['span_id'] in source.get('spans', {}):
                checked_refs.append({'source_id': ref['source_id'], 'span_id': ref['span_id']})
        if checked_refs:
            gaps.append({'rule_id': rule, 'scope_ids': sorted(set(scope)),
                         'missing_predicates': sorted(set(predicates)), 'evidence_refs': checked_refs})
    concern_reviews = {}
    candidates_by_id = {item['id']: item for item in bundle['candidates']
                        if isinstance(item, dict) and isinstance(item.get('id'), str)}
    for concern_id in packet['required_concern_reviews']:
        item = raw_reviews.get(concern_id) if isinstance(raw_reviews, dict) else None
        if (not isinstance(item, dict)
                or item.get('status') not in ('proposed', 'not_applicable', 'needs_information')
                or not isinstance(item.get('candidate_ids'), list)
                or any(not isinstance(key, str) for key in item['candidate_ids'])):
            continue
        identifiers = sorted(set(item['candidate_ids']))
        if item['status'] == 'proposed':
            if not identifiers or any(key not in candidates_by_id or
                    candidates_by_id[key].get('concern_id') != concern_id for key in identifiers):
                continue
        elif identifiers:
            continue
        concern_reviews[concern_id] = {'status': item['status'], 'candidate_ids': identifiers}
    return {'candidate_bundle': bundle, 'provider': provider, 'review_required': True,
            'reference_bindings': reference_bindings,
            'candidate_id_bindings': candidate_id_bindings,
            'completion_review': {'reviewed_rule_ids': reviewed,
                                  'unreviewed_rule_ids': sorted(set(packet['rules']) - set(reviewed)),
                                  'concern_reviews': concern_reviews,
                                  'unreviewed_concern_ids': sorted(set(packet['required_concern_reviews']) - set(concern_reviews)),
                                  'deferred': deferred, 'evidence_gaps': gaps}}
