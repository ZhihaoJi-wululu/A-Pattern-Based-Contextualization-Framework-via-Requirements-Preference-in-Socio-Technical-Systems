"""Read-only, case-specific trace from a CPS card to an active preference.

A matching facet is not an application. Stored supports are shown as applied
only while the current candidate validator can reproduce them and they remain
linked to an active stored relation. Revalidation never restores withdrawals.
"""
from copy import deepcopy
import math

from .compiler import compile_model
from .contextualize import contextualize_session
from .patterns import (CandidateBindingError, catalogue_overview, load_catalogue,
                       machine_contracts, resolve_candidate_binding, rule_contracts)
from .schema import model_hash, validate_model


def _evidence(reference, sources):
    if isinstance(reference, list):
        return [span for item in reference for span in _evidence(item, sources)]
    if not isinstance(reference, dict): return []
    source_id, span_id = reference.get('source_id'), reference.get('span_id')
    source = sources.get(source_id, {})
    if not isinstance(source, dict): return []
    span = source.get('spans', {}).get(span_id)
    text = span.get('text') if isinstance(span, dict) else span
    if not isinstance(text, str) or not text.strip(): return []
    return [{'source_id': source_id, 'span_id': span_id, 'text': text,
             'source_label': source.get('label', source_id), 'kind': source.get('kind'),
             **({'quote': reference['quote']} if reference.get('quote') else {})}]


def _endpoint_ids(value):
    if isinstance(value, str): return [value]
    if isinstance(value, list): return [key for item in value for key in _endpoint_ids(item)]
    if isinstance(value, dict): return _endpoint_ids(value.get('tasks', value.get('goal', value.get('id'))))
    return []


def _node(model, key):
    n = model['nodes'].get(key, {})
    return {'id': key, 'label': n.get('label', key), 'kind': n.get('kind'), 'role': n.get('role')}


def _named(model, value):
    return ' + '.join(key + ' (' + str(model['nodes'].get(key, {}).get('label', key)).replace('\n', ' ') + ')'
                      for key in _endpoint_ids(value))


def _relation(model, relation):
    result = deepcopy(relation)
    if relation['kind'] == 'choice':
        values = [relation.get('source'), relation.get('target')]
        label = _named(model, values[0]) + ' preferred_to ' + _named(model, values[1])
    else:
        values = [relation.get('x'), relation.get('y')]
        label = relation.get('formula', relation['kind']) + ' [' + _named(model, values[0]) + ']'
        if values[1] is not None: label += ' / [' + _named(model, values[1]) + ']'
    ids = list(dict.fromkeys(key for value in values for key in _endpoint_ids(value)))
    result.update(label=label, endpoints=[_node(model, key) for key in ids])
    return result


def _manual_weight(session, key):
    value = session.get('preference_profile', {}).get('weights', {}).get(key)
    if value is None or isinstance(value, str) and not value.strip(): return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        return None
    return value


def build_pattern_usage(session):
    """Build the current usage view without mutating or persisting the session."""
    base = validate_model(session['model'])
    current_hash = model_hash(base)
    catalogue, contracts = load_catalogue(), machine_contracts()
    overview = catalogue_overview(catalogue)
    cards = {card['id']: card for card in catalogue['patterns']}
    rules = {rule['id']: rule for rule in catalogue['rules']}
    atomic_contracts = rule_contracts()
    source_catalogue = catalogue.get('sources', {})
    if isinstance(source_catalogue, list): source_catalogue = {s['id']: s for s in source_catalogue}
    original = compile_model(base)
    base_pddl = {p['id']: p['pddl'] for p in original['transformation_steps'][2]['items']}
    base_preferences = [{**deepcopy(p), 'origin': 'base', 'pattern_ids': [],
                         'pddl': base_pddl[p['id']], 'weight': _manual_weight(session, p['id'])}
                        for p in original['ir']['preferences']]
    raw_candidates = (session.get('candidate_bundle') or {}).get('candidates', [])
    candidates = raw_candidates if isinstance(raw_candidates, list) else []
    stored = deepcopy(session.get('result'))
    if stored:
        for support in stored.get('supports', []):
            try:
                binding = resolve_candidate_binding(support, parents=cards, rules=atomic_contracts)
            except CandidateBindingError:
                continue
            support.update(pattern_id=binding['pattern_id'], rule_id=binding['rule_id'])
    warnings, excluded, fresh = [], [], None
    metadata_fresh = bool(stored and stored.get('model_hash') == current_hash and stored.get('base_preserved')
                          and model_hash(stored.get('base', {})) == current_hash)
    if stored and metadata_fresh:
        try:
            fresh = contextualize_session(session)
        except (ValueError, TypeError, KeyError) as error:
            warnings.append('当前候选无法重新核验，未将旧支持计为已使用：' + str(error))
    elif stored:
        warnings.append('补全结果与当前M0不一致，旧支持不计为当前应用。')
    elif candidates:
        warnings.append('当前有预置或导入候选，尚未校验；候选不计为已使用的pattern。')
    else:
        warnings.append('当前示例没有pattern候选；原有quality/时序偏好来自结构化模型，可单独用于手动权重演示。')

    stored_relations = {r['id']: r for r in (stored or {}).get('relations', [])}
    fresh_supports = {s['id']: s for s in (fresh or {}).get('supports', [])}
    fresh_relations = {r['id']: r for r in (fresh or {}).get('relations', [])}
    active = []
    for support in (stored or {}).get('supports', []):
        sid = support.get('id'); relation = stored_relations.get(support.get('relation_id'))
        checked = fresh_supports.get(sid)
        reason = None
        if not metadata_fresh or fresh is None: reason = 'result_not_current'
        elif support.get('status') not in {'active', 'active_transfer_candidate'}: reason = 'support_not_active'
        elif not relation or sid not in relation.get('support_ids', []): reason = 'support_not_linked_to_relation'
        elif checked is None: reason = 'support_not_reproduced_from_current_inputs'
        elif checked.get('relation_id') not in fresh_relations: reason = 'relation_not_current'
        elif any(support.get(k) != checked.get(k) for k in ('guards', 'persona_evidence', 'provider', 'pattern_id', 'rule_id')):
            reason = 'support_evidence_or_provenance_changed'
        elif support.get('pattern_version') != checked.get('pattern_version') and not (
                support.get('pattern_version') == 'APATE_v4.1' and checked.get('pattern_version') == 'APATE_v4.2'):
            reason = 'support_catalogue_version_changed'
        elif any(relation.get(k) != fresh_relations[checked['relation_id']].get(k)
                 for k in ('kind', 'source', 'target', 'formula', 'x', 'y', 'actor_id', 'role_id', 'context_id', 'current_work_id')):
            reason = 'relation_binding_changed'
        if reason:
            excluded.append({'support_id': sid, 'pattern_id': support.get('pattern_id'),
                             'rule_id': support.get('rule_id'), 'reason': reason})
        else:
            active.append(deepcopy(checked))
    if excluded: warnings.append(str(len(excluded)) + '项旧支持未通过当前输入复核，已从应用统计排除。')

    active_ids = {s['id'] for s in active}
    active_by_id = {s['id']: s for s in active}
    current_relations = []
    for rid, relation in stored_relations.items():
        ids = [sid for sid in relation.get('support_ids', []) if sid in active_ids]
        if ids:
            copy = deepcopy(relation); copy['support_ids'] = ids
            for field, source in (('pattern_ids','pattern_id'),('rule_ids','rule_id'),
                                  ('facets','facet'),('concern_ids','concern_id')):
                copy[field] = list(dict.fromkeys(active_by_id[sid][source] for sid in ids))
            current_relations.append(copy)
    compiled = compile_model(base, contextualized_relations=current_relations)
    current_relation_map = {r['id']: r for r in current_relations}
    pref_map = {p['id']: p for p in compiled['ir']['preferences']}
    pddl_map = {p['id']: p['pddl'] for p in compiled['transformation_steps'][2]['items']}
    witness_map = {w.get('id', str(i)): w for i, w in enumerate(session.get('witnesses', [])) if isinstance(w, dict)}
    sources = session.get('sources', {})
    persona, context = session.get('persona', {}), session.get('context', {})
    applications = {key: [] for key in cards}
    active_candidates = set()
    for support in active:
        pid = support['pattern_id']; card = cards[pid]
        rule_id = support['rule_id']; rule = rules[rule_id]; contract = atomic_contracts[rule_id]
        relation = current_relation_map[support['relation_id']]
        formal_id = 'apate:' + relation['id']; pref = pref_map[formal_id]
        facts = []
        for guard in support.get('guards', []):
            fact = context.get('facts', {}).get(guard['fact_id'], {})
            facts.append({'predicate': guard['predicate'], 'description': contract['predicate_descriptions'].get(guard['predicate'], guard['predicate']),
                          'fact_id': guard['fact_id'], 'value': fact.get('value'), 'status': guard['status'],
                          'evidence': _evidence(fact.get('evidence'), sources)})
        concern_id = support['concern_id']; concern = deepcopy(session.get('concerns', {}).get(concern_id, {}))
        concern.update(id=concern_id)
        card_concern = rule.get('instantiation', {}).get('concern', {})
        concern.setdefault('criterion', card_concern.get('criterion') if isinstance(card_concern, dict) else card_concern)
        pairs = []
        for pair in support.get('witness_pairs', []):
            rows = {}
            for name in ('preferred', 'other'):
                wid = pair[name]; witness = witness_map[wid]
                rows[name] = {'id': wid, 'sequence': [_node(base, key) for key in witness['sequence']],
                              'effect': pair[name + '_effect']}
                if witness.get('normalized_sequence') is not None:
                    rows[name]['normalized_sequence'] = deepcopy(witness['normalized_sequence'])
            pairs.append(rows)
        role = support['role_id']; role_label = base.get('roles', {}).get(role, role)
        if isinstance(role_label, dict): role_label = role_label.get('label', role_label.get('name', role))
        app = {'support_id': support['id'], 'candidate_id': support.get('candidate_id'), 'pattern_id': pid,
               'rule_id': rule_id, 'rule_name': rule['name'],
               'facet': support['facet'], 'actor': {'id': support['actor_id'], 'name': persona.get('name', support['actor_id']),
               'role_id': role, 'role_label': role_label, 'context_id': support['context_id']},
               'persona_evidence': _evidence(persona.get('evidence'), sources), 'facts': facts, 'concern': concern,
               'relation': _relation(base, relation), 'witness_pairs': pairs, 'witness_count': len(pairs),
               'formal_mapping': {'preference_id': formal_id, 'formula': deepcopy(pref['formula']), 'pddl': pddl_map[formal_id],
                                  'weight': _manual_weight(session, formal_id), 'translation': pref.get('translation'),
                                  'origin': 'contextualization'},
               'sources': [deepcopy(source_catalogue[key]) for key in rule.get('sources', []) if key in source_catalogue],
               'inference_boundary': rule.get('inference_boundary', ''), 'provider': deepcopy(support.get('provider', {}))}
        if relation.get('current_work_id'):
            app['current_work'] = {'id': relation['current_work_id'], **deepcopy(context.get('current_work', {}).get(relation['current_work_id'], {}))}
        candidate = next((c for c in candidates if c.get('id') == support.get('candidate_id')), {})
        if candidate.get('review_node'): app['independent_review'] = _node(base, candidate['review_node'])
        applications[pid].append(app); active_candidates.add(support.get('candidate_id'))

    stored_decisions = {d.get('candidate_id'): d for d in (stored or {}).get('decisions', [])}
    fresh_decisions = {d.get('candidate_id'): d for d in (fresh or {}).get('decisions', [])}
    candidate_rows = {key: [] for key in cards}
    pending = []
    for candidate in candidates:
        if not isinstance(candidate, dict): continue
        cid, pid, rule_id = candidate.get('id'), candidate.get('pattern_id'), candidate.get('rule_id')
        try:
            binding = resolve_candidate_binding(candidate, parents=cards, rules=atomic_contracts)
            pid, rule_id = binding['pattern_id'], binding['rule_id']
        except CandidateBindingError:
            pass
        previous, current = stored_decisions.get(cid, {}), fresh_decisions.get(cid, {})
        if cid in active_candidates:
            decision = current; status = 'applied'
        elif previous.get('status') == 'withdrawn':
            decision = previous; status = 'withdrawn'
        elif not stored:
            decision = {}; status = 'pending'
        elif not metadata_fresh or not fresh:
            decision = {'reason_code': 'result_not_current', 'reason': '当前结果需要重新校验。'}; status = 'unknown'
        else:
            decision = current; status = current.get('status', 'unknown')
            if status == 'accepted':
                status = 'unknown'; decision = {'reason_code': 'support_not_current', 'reason': '旧支持未保留或其证据已改变。'}
        row = {'id': cid, 'pattern_id': pid, 'rule_id': rule_id, 'status': status, 'reason_code': decision.get('reason_code'),
               'reason': decision.get('reason', '')}
        if pid in candidate_rows: candidate_rows[pid].append(row)
        if status == 'pending': pending.append(row)
    entries = []
    for pid, card in cards.items():
        apps, rows = applications[pid], candidate_rows[pid]
        statuses = {row['status'] for row in rows}
        status = 'applied' if apps else 'pending' if 'pending' in statuses else 'unknown' if 'unknown' in statuses else 'withdrawn' if 'withdrawn' in statuses else 'rejected' if rows else 'unused'
        entries.append({'id': pid, 'name': card['name'], 'facets': deepcopy(card['facets']),
                        'rule_ids': list(card['rule_ids']), 'status': status,
                        'card': deepcopy(card), 'contract': deepcopy(contracts[pid]), 'applications': apps, 'candidates': rows})
    summary = {'catalogue_patterns': overview['pattern_count'], 'catalogue_facets': overview['facet_count'],
               'catalogue_associations': overview['association_count'], 'catalogue_rules': overview['rule_count'],
               'catalogue_branches': overview['branch_count'],
               'applied_patterns': sum(bool(v) for v in applications.values()),
               'applied_rules': len({s['rule_id'] for s in active}),
               'applied_branches': len({(s['pattern_id'],s['rule_id']) for s in active}),
               'active_supports': len(active), 'applied_relations': len(current_relations), 'candidate_count': len(candidates),
               'pending_candidates': len(pending), 'base_preferences': len(base_preferences), 'excluded_supports': len(excluded)}
    return {'schema_version': 'apate.pattern-usage.v1', 'model_hash': current_hash, 'result_fresh': metadata_fresh and fresh is not None and not excluded,
            'summary': summary, 'catalogue_overview': overview, 'patterns': entries,
            'base_preferences': base_preferences, 'pending_candidates': pending,
            'excluded_supports': excluded, 'warnings': warnings}
