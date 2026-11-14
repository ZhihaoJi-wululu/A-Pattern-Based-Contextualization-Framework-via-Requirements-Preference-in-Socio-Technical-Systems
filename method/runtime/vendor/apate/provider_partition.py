"""Parallel criterion ownership over one unchanged model and context snapshot."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json

from .provider_schema import _criterion_leaves, primary_concern_ids
from .schema import model_hash

PARTITION_POLICY = {'max_concerns': 4, 'workers': 3, 'split_threshold': 4,
                    'order': 'active_role_then_model_decision_order',
                    'worker_transient_retries': 1, 'retry_condition': 'ProviderError.retryable is True',
                    'transient_causes': ['TimeoutError', 'URLError', 'OSError', 'HTTP429', 'HTTP5xx']}


def _ordered_concerns(session):
    from .contextualize import _ModelView
    view = _ModelView(session['model'])
    order = {}
    def visit(key):
        if key in order:
            return
        order[key] = len(order)
        for child in view.refs.get(key, {}).get('children', []):
            visit(child)
    root = session['model'].get('root')
    if root in view.nodes:
        visit(root)
    for key in sorted(view.nodes):
        visit(key)
    active = (session.get('persona', {}).get('role_ids') or [None])[0]
    roles = [active] + [key for key in session['model'].get('roles', {}) if key != active]
    ranks = {key: index for index, key in enumerate(roles)}
    def key(identity):
        try:
            leaves = _criterion_leaves(view, session['concerns'][identity].get('ast'))
        except ValueError:
            leaves = []
        owners = [ranks.get(view.nodes[leaf].get('role'), len(ranks)) for leaf in leaves]
        return (min(owners, default=len(ranks)),
                min((order[leaf] for leaf in leaves), default=len(order)), identity)
    # This is traversal order for assignment, not an execution-order assertion.
    return sorted(primary_concern_ids(session), key=key)


def partition_sessions(session, max_concerns=4):
    """Clone only output criterion ownership; keep all global input content."""
    if type(max_concerns) is not int or max_concerns < 1:
        raise ValueError('max_concerns must be a positive integer.')
    limit = min(PARTITION_POLICY['max_concerns'], max_concerns)
    concerns = _ordered_concerns(session)
    groups = [concerns[i:i + limit] for i in range(0, len(concerns), limit)] or [[]]
    output = []
    for index, group in enumerate(groups, 1):
        identity = 'P' + str(index).zfill(2)
        clone = deepcopy(session)
        if len(groups) > 1:
            clone['concerns'] = {key: deepcopy(session['concerns'][key]) for key in group}
            clone['completion_partition'] = {'partition_id': identity, 'concern_ids': list(group)}
        output.append({'partition_id': identity, 'concern_ids': list(group), 'session': clone})
    return output


def _unique(rows):
    seen, output = set(), []
    for row in rows:
        key = json.dumps(row, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            seen.add(key)
            output.append(row)
    return output


def _sum_usage(target, usage):
    if not isinstance(usage, dict):
        return
    for key, value in usage.items():
        if isinstance(value, dict):
            _sum_usage(target.setdefault(key, {}), value)
        elif type(value) in (int, float):
            target[key] = target.get(key, 0) + value


def complete_partitions(session, generate_single, workers=3):
    """Merge in order, allowing one explicitly transient worker retry."""
    from .provider import ProviderError
    from .patterns import rule_contracts
    if type(workers) is not int or workers < 1:
        raise ValueError('workers must be a positive integer.')
    partitions = partition_sessions(session)
    if len(partitions) == 1:
        return generate_single(partitions[0]['session'])
    def run(partition):
        snapshot = deepcopy(partition['session'])
        attempts = []
        for attempt in range(1, PARTITION_POLICY['worker_transient_retries'] + 2):
            working = deepcopy(snapshot)
            working['completion_partition']['worker_attempt'] = attempt
            unchanged = deepcopy(working)
            try:
                result = generate_single(working)
                if working != unchanged:
                    raise ProviderError('A completion worker changed its immutable input snapshot.')
                bundle = result.get('candidate_bundle', {})
                expected = {'schema_version': 'apate.candidates.v1', 'model_hash': model_hash(snapshot['model']),
                            'actor_id': snapshot.get('persona', {}).get('actor_id'),
                            'role_id': (snapshot.get('persona', {}).get('role_ids') or [None])[0],
                            'context_id': snapshot.get('context', {}).get('id')}
                if not isinstance(bundle, dict) or any(key not in bundle or bundle[key] != value
                                                       for key, value in expected.items()):
                    raise ProviderError('A completion worker returned a bundle for a different model, actor, role or context.')
                candidates = bundle.get('candidates', [])
                identities = [row.get('id') for row in candidates if isinstance(row, dict)]
                if (len(identities) != len(candidates) or any(not isinstance(key, str) for key in identities)
                        or len(identities) != len(set(identities))):
                    raise ProviderError('A completion worker returned malformed or duplicate candidate IDs.')
                if any(row.get('concern_id') not in partition['concern_ids'] for row in candidates):
                    raise ProviderError('A completion worker proposed a criterion outside its assignment.')
                attempts.append({'worker_attempt': attempt, 'status': 'completed',
                                 'provider': deepcopy(result.get('provider', bundle.get('provider', {})))})
                return {'partition_id': partition['partition_id'], 'concern_ids': partition['concern_ids'],
                        'status': 'completed', 'attempts': attempts, 'result': deepcopy(result)}
            except ProviderError as error:
                retryable = getattr(error, 'retryable', False) is True and working == unchanged
                attempts.append({'worker_attempt': attempt, 'status': 'failed', 'error': str(error),
                                 'retryable': retryable, 'snapshot_preserved': working == unchanged,
                                 'provider': deepcopy(getattr(error, 'metadata', {}))})
                if not retryable or attempt > PARTITION_POLICY['worker_transient_retries']:
                    return {'partition_id': partition['partition_id'], 'concern_ids': partition['concern_ids'],
                            'status': 'failed', 'error': str(error), 'attempts': attempts}
    with ThreadPoolExecutor(max_workers=min(workers, len(partitions))) as pool:
        # map yields input order regardless of actual worker completion order.
        results = list(pool.map(run, partitions))
    candidates, references, gaps, deferred, reviews, metadata = [], [], [], [], {}, []
    reviewed_sets, rule_ids = [], set()
    selected = set(session.get('persona', {}).get('facets', []))
    rule_ids.update(key for key, rule in rule_contracts().items() if selected.intersection(rule['facets']))
    for partition in results:
        if partition['status'] == 'failed':
            reviewed_sets.append(set())
            continue
        result = partition['result']
        prefix = partition['partition_id'] + ':'
        local = result['candidate_bundle'].get('candidates', [])
        by_id = {row['id']: row for row in local}
        for row in local:
            candidates.append({**deepcopy(row), 'id': prefix + row['id']})
        for row in result.get('reference_bindings', []):
            if row.get('candidate_id') in by_id:
                references.append({**deepcopy(row), 'candidate_id': prefix + row['candidate_id']})
        review = result.get('completion_review', {})
        reviewed = set(review.get('reviewed_rule_ids', []))
        reviewed_sets.append(reviewed)
        rule_ids.update(reviewed | set(review.get('unreviewed_rule_ids', [])))
        deferred.extend(deepcopy(review.get('deferred', [])))
        gaps.extend(deepcopy(review.get('evidence_gaps', [])))
        for key in partition['concern_ids']:
            row = review.get('concern_reviews', {}).get(key)
            if not isinstance(row, dict) or not isinstance(row.get('candidate_ids'), list):
                continue
            ids = row['candidate_ids']
            status = row.get('status')
            if status == 'proposed':
                if not ids or any(identity not in by_id or by_id[identity].get('concern_id') != key for identity in ids):
                    continue
            elif status not in ('not_applicable', 'needs_information') or ids:
                continue
            reviews[key] = {'status': status, 'candidate_ids': [prefix + identity for identity in ids]}
    proposed_rules = {row.get('rule_id') for row in candidates}
    grouped = {}
    for row in deferred:
        identity = row.get('rule_id')
        if identity in proposed_rules:
            continue
        group = grouped.setdefault(identity, {'rule_id': identity, 'missing_predicates': set(), 'reasons': []})
        group['missing_predicates'].update(row.get('missing_predicates', []))
        if row.get('reason') and row['reason'] not in group['reasons']:
            group['reasons'].append(row['reason'])
    deferred = [{'rule_id': key, 'missing_predicates': sorted(row['missing_predicates']),
                 'reason': ' '.join(row['reasons'])} for key, row in sorted(grouped.items())]
    # Each worker reviews its owned criteria. Missing/failed ownership remains
    # explicit in unreviewed_concern_ids; other workers need not repeat that work.
    reviewed = set.union(*reviewed_sets) if reviewed_sets else set()
    usage = {}
    for partition in results:
        metadata.extend(row['provider'] for row in partition['attempts']
                        if isinstance(row.get('provider'), dict) and row['provider'])
    for row in metadata:
        _sum_usage(usage, row.get('usage', {}))
    successful = [row['result'].get('provider', row['result']['candidate_bundle'].get('provider', {}))
                  for row in results if row['status'] == 'completed']
    provider = deepcopy(successful[0]) if successful else {'kind': 'partitioned-completion'}
    provider.setdefault('kind', 'partitioned-completion')
    provider.update(partitioned=True, partition_count=len(results), workers=min(workers, len(partitions)),
                    failed_partitions=sum(row['status'] == 'failed' for row in results), usage=usage,
                    worker_attempts=sum(len(row['attempts']) for row in results),
                    worker_retries=sum(len(row['attempts']) - 1 for row in results),
                    failed_attempts=sum(attempt['status'] == 'failed' for row in results for attempt in row['attempts']),
                    request_id=None, request_ids=[row['request_id'] for row in metadata if row.get('request_id')],
                    elapsed_seconds=round(sum(row.get('elapsed_seconds', 0) for row in metadata), 3),
                    elapsed_basis='sum_of_worker_request_seconds')
    bundle = {'schema_version': 'apate.candidates.v1', 'model_hash': model_hash(session['model']),
              'actor_id': session.get('persona', {}).get('actor_id'),
              'role_id': (session.get('persona', {}).get('role_ids') or [None])[0],
              'context_id': session.get('context', {}).get('id'), 'candidates': candidates, 'provider': provider}
    return {'candidate_bundle': bundle, 'provider': provider, 'review_required': True,
            'reference_bindings': references, 'partition_results': results, 'partition_policy': deepcopy(PARTITION_POLICY),
            'completion_review': {'reviewed_rule_ids': sorted(reviewed),
                'unreviewed_rule_ids': sorted(rule_ids - reviewed), 'concern_reviews': reviews,
                'unreviewed_concern_ids': sorted(set(primary_concern_ids(session)) - set(reviews)),
                'deferred': deferred, 'evidence_gaps': _unique(gaps)}}
