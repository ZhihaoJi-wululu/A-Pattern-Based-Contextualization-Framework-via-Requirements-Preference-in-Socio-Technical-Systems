"""Fresh, evidence-bound modeling from persona, patterns and the goal model."""
from copy import deepcopy
import hashlib
import json

from . import workbench as wb
from .patterns import load_catalogue, rule_contracts
from .schema import ModelError, business_projection, model_hash
from .store import SessionConflict

CONTRACT_ID = 'apate.input.three.v1'


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':')).encode('utf-8')).hexdigest()


def public_three_input_workspace(value):
    """Hide legacy extra inputs and results that have not used this contract."""
    output = wb.public_workspace(value)
    output.pop('material', None)
    contract = value.get('artifacts', {}).get('input_contract', {})
    if contract.get('id') != CONTRACT_ID:
        output['result'] = None
    output['input_contract'] = {'id': CONTRACT_ID,
        'inputs': ['persona', 'pattern', 'goal_model']}
    output['input_contract'].update({key: contract[key] for key in ('method', 'prompt_version') if key in contract})
    return output


def rule_gate_audit(persona, session):
    """Expose missing premises; observed premises still need scoped validation."""
    facts = session.get('context', {}).get('facts', {}) if session else {}
    selected = set(persona.get('facets', []))
    rows = {}
    for rule_id, contract in rule_contracts().items():
        if not selected.intersection(contract['facets']):
            continue
        predicates = {}
        for predicate in contract['required_predicates']:
            records = [deepcopy(f) for f in facts.values()
                       if f.get('predicate') == predicate]
            predicates[predicate] = {'fact_ids': [f['id'] for f in records],
                'scopes': [f.get('scope_ids', []) for f in records],
                'values': [f.get('value') for f in records]}
        missing = [p for p, record in predicates.items()
                   if True not in record['values']]
        rows[rule_id] = {'pattern_ids': deepcopy(contract['pattern_ids']),
            'facets': deepcopy(contract['facets']), 'required_predicates': predicates,
            'missing_or_unestablished_predicates': missing,
            'status': 'missing_premises' if missing else 'requires_scoped_candidate_validation'}
    return rows


def contextualize_evidence_workspace(identity, payload):
    """Use no source-wrapper evidence, cached analysis, witnesses or answers."""
    if not isinstance(payload, dict):
        raise ModelError('Contextualization input must be an object.')
    unexpected = sorted(set(payload) - {'persona', 'revision', 'material'})
    if unexpected:
        raise ModelError('Three-input modeling accepts persona and revision only: ' + ', '.join(unexpected))
    if 'material' in payload and payload['material'] != '':
        raise ModelError('Three-input modeling requires material to be empty.')
    value = wb.get_workspace(identity)
    if 'revision' in payload and payload['revision'] != value['revision']:
        raise SessionConflict('This workspace input revision is stale.')
    persona = wb._persona(value, payload)
    base = value.get('base_session')
    fresh = None
    if base is not None:
        model = business_projection(base['model'])
        fresh = {'model': model, 'persona': {}, 'sources': {},
            'context': {}, 'concerns': deepcopy(model.get('concerns', {})),
            'witnesses': [], 'candidate_bundle': None}
    contract = {'id': CONTRACT_ID, 'inputs': ['persona', 'pattern', 'goal_model'],
        'persona_sha256': _hash(persona), 'pattern_sha256': _hash(load_catalogue()),
        'goal_model_sha256': model_hash(fresh['model']) if fresh else None,
        'evidence_policy': 'Explicit supplied persona statements and original model declarations; unknown premises remain unknown.',
        'extraction_policy': 'Fresh extraction for each attempt; immutable persona description.'}
    clean_payload = {'persona': persona, 'material': ''}
    if 'revision' in payload:
        clean_payload['revision'] = payload['revision']
    wb.contextualize_workspace(identity, clean_payload,
        _fresh_session=fresh, _input_contract=contract)
    # The immutable source remains retained for provenance. Analysis was built
    # exclusively from its business projection, never from wrapper fields.
    with wb.LOCK:
        saved = wb.get_workspace(identity)
        if saved['revision'] != value['revision'] + 1:
            raise SessionConflict('Workspace changed before the input audit was saved.')
        saved['artifacts']['rule_gate_audit'] = rule_gate_audit(persona, saved.get('analysis_session'))
        wb._write(saved)
    return public_three_input_workspace(saved)


def contextualize_three_input_workspace(identity, payload):
    """Compatibility entry for the reviewed original-OR agent method."""
    from .preferred_to import contextualize_workspace
    output = contextualize_workspace(identity, payload)
    return public_three_input_workspace(wb.get_workspace(output['id']))
