"""Frozen provider-free protocol, original-graph checks and deterministic merge.

The LLM alone assesses persona meaning, rule premises and preference direction.
This module checks literal provenance and original structure; it never infers,
repairs, reverses or invents semantic judgments. A qualified empty response is
distinct from a malformed response or an unfinished required mechanical check.
"""
from copy import deepcopy
import hashlib
import json

from apate.preferred_protocol import rules_for
from apate.preferred_structure import PlanSearch, authorized, literal_evidence
from apate.schema import validate_model


METHOD_ID = 'apate.preferred-to.single-facet.parallel.prompt-only.v1'
VALIDATION_ID = 'apate.facet-proposals.literal-structure-complete-plan.v1'
MERGE_ID = 'apate.facet-proposals.directed-support-merge.v1'
MECHANICAL_BUDGET = {'max_realizations': 2048, 'max_prefixes': 50000, 'max_seconds': 30}
PROPOSAL_FIELDS = ('scope', 'source', 'target', 'rule_id', 'outcome_id',
                   'persona_quote', 'model_evidence', 'reason')
CITATION_FIELDS = ('node_id', 'field', 'quote')
RESPONSE_SCHEMA = {
    'type': 'object', 'additionalProperties': False, 'required': ['proposals'],
    'properties': {'proposals': {'type': 'array', 'items': {
        'type': 'object', 'additionalProperties': False, 'required': list(PROPOSAL_FIELDS),
        'properties': {
            **{field: {'type': 'string', 'minLength': 1}
               for field in PROPOSAL_FIELDS if field != 'model_evidence'},
            'model_evidence': {'type': 'array', 'minItems': 1, 'items': {
                'type': 'object', 'additionalProperties': False,
                'required': list(CITATION_FIELDS),
                'properties': {'node_id': {'type': 'string', 'minLength': 1},
                               'field': {'type': 'string', 'enum': ['label', 'description', 'meaning']},
                               'quote': {'type': 'string', 'minLength': 1}}}}
        }}}}}
SCHEMA = RESPONSE_SCHEMA


class ValidationError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError('Repeated JSON object key: ' + key)
        result[key] = value
    return result


def parse_response(value):
    """Parse one strict JSON object, without fences, coercion or repair."""
    if isinstance(value, str):
        def constant(token):
            raise ValidationError('Non-finite JSON constant: ' + token)
        try:
            value = json.loads(value, object_pairs_hook=_unique, parse_constant=constant)
        except json.JSONDecodeError as exc:
            raise ValidationError('Invalid JSON: ' + str(exc)) from exc
    if not isinstance(value, dict) or set(value) != {'proposals'} or not isinstance(value['proposals'], list):
        raise ValidationError('Response must be exactly an object with a proposals array.')
    try:
        json.dumps(value, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ValidationError('Response is not finite JSON data.') from exc
    return deepcopy(value)


def _inputs(case):
    if not isinstance(case, dict) or not isinstance(case.get('persona'), dict):
        raise ValidationError('Case requires an original persona object.')
    model = case.get('source_document', {}).get('model', case.get('goal_model', case.get('model')))
    if not isinstance(model, dict):
        raise ValidationError('Case requires the complete original business model.')
    validate_model(model)
    persona = case['persona']
    for field in ('actor_id', 'description'):
        if not isinstance(persona.get(field), str) or not persona[field].strip():
            raise ValidationError('Persona requires nonempty ' + field + '.')
    for field in ('role_ids', 'facets'):
        value = persona.get(field)
        if (not isinstance(value, list) or any(not isinstance(v, str) or not v for v in value)
                or len(value) != len(set(value))):
            raise ValidationError('Persona requires distinct string ' + field + '.')
    if not persona['role_ids'] or any(role not in model.get('roles', {}) for role in persona['role_ids']):
        raise ValidationError('Persona role binding must reference original roles.')
    return model, persona


def validate_response(value, case, facet, pattern, mechanical=None):
    """Return qualified/failed, process proposals, errors and mechanical proofs.

    ``mechanical`` may be a PlanSearch-like object with ``pair`` or a callable
    ``(scope, source, target) -> proof``. The default is the fixed bounded
    complete-plan checker. Its invocation is provider-free. Every nonempty
    proposal must pass; failures retain process candidates and never publish a
    partial final model. No trait-subject or effect classifier runs locally.
    """
    result = {'status': 'failed', 'validation_policy': VALIDATION_ID,
              'facet': facet, 'proposals': [], 'errors': [], 'mechanical': {}}
    try:
        model, persona = _inputs(case)
        if not isinstance(facet, str) or facet not in persona['facets']:
            raise ValidationError('active_facet must be exactly one selected persona facet.')
        rules = rules_for(pattern, [facet])
        rule_map = {}
        for rule in rules:
            if rule['id'] in rule_map:
                raise ValidationError('Active pattern has an ambiguous choice rule ID.')
            rule_map[rule['id']] = rule
        parsed = parse_response(value)
        result['raw_proposals'] = deepcopy(parsed['proposals'])
        refs = {ref['parent']: ref for ref in model.get('refinements', [])}
        checker = mechanical
        for ordinal, row in enumerate(parsed['proposals']):
            try:
                if not isinstance(row, dict) or set(row) != set(PROPOSAL_FIELDS):
                    raise ValidationError('Candidate must contain exactly the fixed proposal fields.')
                for field in PROPOSAL_FIELDS:
                    if field != 'model_evidence' and (not isinstance(row[field], str) or not row[field].strip()):
                        raise ValidationError(field + ' must be a nonempty scalar string.')
                scope, source, target = (row[field] for field in ('scope', 'source', 'target'))
                ref = refs.get(scope)
                if (not ref or ref.get('kind') != 'OR'
                        or model['nodes'].get(scope, {}).get('kind') != 'goal'
                        or source == target or source not in ref['children'] or target not in ref['children']):
                    raise ValidationError('Endpoints must be different original direct children of the same original OR goal.')
                roles = [role for role in persona['role_ids'] if authorized(model, role, scope)]
                if len(roles) != 1:
                    raise ValidationError('Exactly one persona-bound original role must have this decision authority.')
                rule = rule_map.get(row['rule_id'])
                if rule is None:
                    raise ValidationError('rule_id is not an allowed choice rule for active_facet.')
                if row['outcome_id'] not in {outcome['id'] for outcome in rule['outcomes']}:
                    raise ValidationError('outcome_id does not belong to the selected rule.')
                if row['persona_quote'] not in persona['description']:
                    raise ValidationError('persona_quote is not a literal substring of the complete original persona description.')
                evidence = row['model_evidence']
                if not isinstance(evidence, list) or not evidence:
                    raise ValidationError('model_evidence must be a nonempty citation array.')
                for citation in evidence:
                    if not isinstance(citation, dict) or set(citation) != set(CITATION_FIELDS):
                        raise ValidationError('Each model citation requires exactly node_id, field and quote.')
                    if not literal_evidence(model, citation['node_id'], citation['field'], citation['quote']):
                        raise ValidationError('Model citation is not literal text in one original semantic field.')
                def region(identity):
                    found, stack = set(), [identity]
                    while stack:
                        current = stack.pop()
                        if current not in found:
                            found.add(current)
                            stack.extend(refs.get(current, {}).get('children', []))
                    return found
                cited = {citation['node_id'] for citation in evidence}
                if not cited.intersection(region(source)) or not cited.intersection(region(target)):
                    raise ValidationError('Model evidence must cite at least one original node in each complete endpoint region.')
                key = digest([scope, source, target])
                if key not in result['mechanical']:
                    if checker is None:
                        checker = PlanSearch(model, **MECHANICAL_BUDGET)
                    check = checker.pair if callable(getattr(checker, 'pair', None)) else checker
                    if not callable(check):
                        raise ValidationError('Mechanical checker is not callable.')
                    proof = check(scope, source, target)
                    result['mechanical'][key] = deepcopy(proof)
                proof = result['mechanical'][key]
                if not isinstance(proof, dict) or proof.get('status') != 'complete_feasible':
                    status = proof.get('status') if isinstance(proof, dict) else 'invalid'
                    raise ValidationError('Required complete-plan check did not pass: ' + str(status))
                result['proposals'].append({**deepcopy(row), 'actor_id': persona['actor_id'],
                    'role_id': roles[0], 'facet': facet, 'pattern_id': rule['pattern_id'],
                    'kind': 'choice', 'type': 'preferred_to', 'proposal_ordinal': ordinal,
                    'mechanical_key': key})
            except (ValueError, TypeError, KeyError) as exc:
                result['errors'].append({'proposal_ordinal': ordinal, 'error': str(exc)})
        if not result['errors']:
            result['status'] = 'qualified'
    except (ValueError, TypeError, KeyError) as exc:
        result['errors'].append({'proposal_ordinal': None, 'error': str(exc)})
    return result


def merge(case_id, case, facet_proposals):
    """Merge qualified process candidates, preserving separate semantic support.

    Each supplied value must be a qualified validate_response result. A subset
    is allowed solely to preserve process candidates after failure. This helper
    never finalizes a public model: the entry alone checks all facet technical
    states before calling the existing final-model formatter. Opposing relations
    remain with an explicit conflict; no vote or weight resolves them.
    """
    model, persona = _inputs(case)
    if not isinstance(case_id, str) or not case_id:
        raise ValidationError('case_id must be a nonempty string.')
    if not isinstance(facet_proposals, dict) or not set(facet_proposals) <= set(persona['facets']):
        raise ValidationError('Process merge accepts only original selected facets.')
    for facet in facet_proposals:
        value = facet_proposals[facet]
        if (not isinstance(value, dict) or value.get('status') != 'qualified'
                or value.get('facet') != facet or value.get('validation_policy') != VALIDATION_ID
                or value.get('errors') or not isinstance(value.get('proposals'), list)):
            raise ValidationError('Process merge requires a qualified checked result for facet ' + facet)
    relations, supports, duplicates, provenance = {}, {}, [], []
    for facet in persona['facets']:
        if facet not in facet_proposals:
            continue
        checked = facet_proposals[facet]
        for row in checked['proposals']:
            core = {key: row[key] for key in ('actor_id', 'role_id', 'kind', 'type', 'source', 'target')}
            identity = {'case_id': case_id, **core, 'original_or_scope': row['scope']}
            rid = 'P_' + digest(identity)[:20]
            sid = 'S_' + digest({'relation': identity, 'facet': facet,
                'rule_id': row['rule_id'], 'outcome_id': row['outcome_id']})[:20]
            if rid not in relations:
                relations[rid] = {**core, 'id': rid, 'scope': row['scope'], 'original_or_scope': row['scope'],
                    'support_ids': [], 'pattern_ids': [], 'rule_ids': [], 'facets': [],
                    'explanation': row['reason']}
            relation = relations[rid]
            for field, item in (('support_ids', sid), ('pattern_ids', row['pattern_id']),
                                ('rule_ids', row['rule_id']), ('facets', facet)):
                if item not in relation[field]:
                    relation[field].append(item)
            reference = {'facet': facet, 'proposal_ordinal': row['proposal_ordinal'],
                         'relation_id': rid, 'support_id': sid}
            provenance.append(reference)
            if sid in supports:
                duplicates.append(reference)
                supports[sid]['proposal_ordinals'].append(row['proposal_ordinal'])
                continue
            supports[sid] = {'id': sid, 'preference_id': rid, 'pattern_id': row['pattern_id'],
                'rule_id': row['rule_id'], 'facet': facet, 'outcome_id': row['outcome_id'],
                'original_or_scope': row['scope'], 'persona_evidence': {'quote': row['persona_quote']},
                'model_evidence': deepcopy(row['model_evidence']), 'reason': row['reason'],
                'proposal_ordinals': [row['proposal_ordinal']],
                'witness': deepcopy(checked['mechanical'][row['mechanical_key']])}
    conflicts = []
    ordered = list(relations.values())
    for i, left in enumerate(ordered):
        for right in ordered[i + 1:]:
            if (left['actor_id'] == right['actor_id'] and left['role_id'] == right['role_id']
                    and left['original_or_scope'] == right['original_or_scope']
                    and left['source'] == right['target'] and left['target'] == right['source']):
                conflicts.append({'preference_ids': [left['id'], right['id']],
                                  'kind': 'source_supported_opposing_concerns',
                                  'resolution': 'retained_without_vote_or_weight'})
    checked = {'relations': ordered, 'supports': list(supports.values()), 'conflicts': conflicts,
               'duplicates': duplicates, 'proposal_provenance': provenance,
               'method': METHOD_ID, 'merge_policy': MERGE_ID, 'base_preserved': True,
               'status': 'process_candidates', 'is_final': False,
               'qualified_facets': [facet for facet in persona['facets'] if facet in facet_proposals],
               'missing_facets': [facet for facet in persona['facets'] if facet not in facet_proposals]}
    return {**checked, 'preferences': deepcopy(ordered), 'support_count': len(supports)}
