"""Local proof module; deliberately has no runner, provider or ledger adapter.

The only positive result is a fixed-validator-qualified exact empty response
under a well-formed focused pattern whose original rules_for result is [] .
This is a syntactic eligibility theorem, not a semantic persona judgment.
"""
from copy import deepcopy
import hashlib
import json

from apate.preferred_protocol import rules_for
import facet_validation as fixed


POLICY_ID = 'apate.local-zero-choice.eligibility-certificate.v1'
CHECKER_ID = 'apate.local-zero-choice.recompute-checker.v1'
EMPTY_RESPONSE = {'proposals': []}
_COMMON_FIELDS = ('version', 'rule_schema', 'branch_semantics', 'inference_profile',
                  'common_contract', 'legacy_common_contract',
                  'model_semantic_endpoint_contract', 'derived_criterion_contract')


def _json_domain(value):
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        import math
        if math.isfinite(value):
            return
    elif type(value) is list:
        for child in value:
            _json_domain(child)
        return
    elif type(value) is dict and all(type(k) is str for k in value):
        for child in value.values():
            _json_domain(child)
        return
    raise ValueError('Original inputs/certificates must contain only finite JSON types.')


def digest(value):
    _json_domain(value)
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


class Unresolved(ValueError):
    """An unrecognized/incomplete input is never an empty-rule proof."""


def _text(value):
    return type(value) is str and bool(value.strip())


def _strings(value, *, nonempty=False):
    return (type(value) is list and (not nonempty or bool(value))
            and all(_text(v) for v in value))


def _require(condition, code):
    if not condition:
        raise Unresolved(code)


def _well_formed_focused_pattern(pattern, facet):
    """Check selector-bearing shape before the permissive original projector.

    Extra documentation is allowed and bound by the full pattern hash. It
    cannot create resolver membership: the frozen resolver's allowlist decides
    that. Missing or malformed selector-bearing data is unresolved, not [].
    Completeness/authenticity of the caller's frozen focused input is a later
    framework provenance obligation; this module does not invent a catalogue.
    """
    _require(type(pattern) is dict, 'pattern_not_object')
    _require(all(k in pattern for k in _COMMON_FIELDS), 'missing_common_contract')
    _require(all(_text(pattern[k]) for k in ('version', 'rule_schema',
        'branch_semantics', 'inference_profile')), 'malformed_common_identity')
    _require(type(pattern['common_contract']) is list
        and type(pattern['legacy_common_contract']) is list
        and type(pattern['model_semantic_endpoint_contract']) is dict
        and type(pattern['derived_criterion_contract']) is dict,
        'malformed_common_contract')
    _require(type(pattern.get('facets')) is dict and set(pattern['facets']) == {facet},
        'not_exact_active_facet_focus')
    info = pattern['facets'][facet]
    _require(type(info) is dict and _strings(info.get('patterns'))
        and _strings(info.get('rule_ids')), 'malformed_facet_index')
    for collection in ('patterns', 'rules', 'model_semantic_rules'):
        rows = pattern.get(collection)
        _require(type(rows) is list, 'missing_or_malformed_' + collection)
        _require(all(type(row) is dict and _text(row.get('id')) for row in rows),
            'malformed_' + collection + '_row')
        _require(len({row['id'] for row in rows}) == len(rows),
            'duplicate_' + collection + '_identity')
        for row in rows:
            if collection == 'model_semantic_rules':
                _require(_text(row.get('facet')) and _text(row.get('pattern_id'))
                    and _strings(row.get('allowed_kinds')),
                    'malformed_model_semantic_selector')
                outcomes = row.get('semantic_outcomes')
                _require(type(outcomes) is list and all(type(o) is dict
                    and _text(o.get('id')) and _text(o.get('description'))
                    for o in outcomes), 'malformed_model_semantic_outcomes')
            else:
                _require(_strings(row.get('facets')), 'malformed_legacy_facets')
                for field in ('rule_id', 'pattern_id'):
                    _require(field not in row or _text(row[field]),
                        'malformed_legacy_' + field)
                _require('pattern_ids' not in row or _strings(row['pattern_ids']),
                    'malformed_legacy_pattern_ids')
                if 'instantiation' not in row:
                    _require(collection == 'patterns', 'missing_rule_instantiation')
                    continue
                inst = row['instantiation']
                _require(type(inst) is dict and type(inst.get('output')) is dict
                    and _text(inst['output'].get('type')), 'malformed_legacy_output')
                if inst['output']['type'] == 'preferred_to':
                    concern = inst.get('concern')
                    _require(_text(concern) or (type(concern) is dict
                        and _text(concern.get('name'))), 'malformed_choice_concern')
    # Also rejects NaN, Python-only containers and non-serializable unknown data.
    digest(pattern)


def _inspect(case, active_facet, focused_pattern):
    _require(_text(active_facet), 'invalid_active_facet')
    _well_formed_focused_pattern(focused_pattern, active_facet)
    rows = rules_for(focused_pattern, [active_facet])
    _require(type(rows) is list, 'resolver_did_not_return_list')
    if rows:
        return {'status': 'not_eligible', 'reason': 'nonempty_original_choice_rules',
                'certificate': None}
    # No response coercion, semantic classifier or mechanical-plan bypass.
    verdict = fixed.validate_response(deepcopy(EMPTY_RESPONSE), case,
        active_facet, focused_pattern)
    _require(verdict.get('status') == 'qualified' and verdict.get('proposals') == []
        and verdict.get('raw_proposals') == [] and verdict.get('errors') == []
        and verdict.get('mechanical') == {}, 'fixed_empty_gate_not_qualified')
    model, persona = fixed._inputs(case)  # The unchanged gate's exact extraction.
    body = {
        'schema': POLICY_ID,
        'active_facet': active_facet,
        'input_sha256': {'persona': digest(persona), 'original_model': digest(model),
            'focused_pattern': digest(focused_pattern), 'public_schema': digest(fixed.SCHEMA)},
        'resolver': {'identity': 'apate.preferred_protocol.rules_for',
            'selected_facets': [active_facet], 'exact_result': []},
        'fixed_validation': {'identity': fixed.VALIDATION_ID, 'status': 'qualified',
            'response_sha256': digest(EMPTY_RESPONSE), 'errors': [], 'mechanical': {}},
        'necessity': 'Every qualified proposal requires rule_id membership in the original active-facet rule_map; that map is empty.',
    }
    return {'status': 'eligible', 'reason': 'strict_empty_original_choice_rules',
            'certificate': {**body, 'certificate_sha256': digest(body)}}


def build_eligibility_certificate(case, active_facet, focused_pattern):
    """Return eligible/not_eligible/unresolved; no input or candidate is changed."""
    try:
        return _inspect(case, active_facet, focused_pattern)
    except Exception as exc:
        # No unknown/error is a proof of absence, and no input prose is emitted.
        return {'status': 'unresolved',
                'reason': str(exc) if isinstance(exc, Unresolved) else 'inspection_exception',
                'certificate': None}


def verify_eligibility_certificate(certificate, candidate, case, active_facet, focused_pattern):
    """Recompute, exact-compare and rerun the fixed gate; never repair the object.

    A matching digest alone is insufficient. The response must already be the
    exact public empty JSON object, and the independent invocation must again
    prove the original resolver is [] and the fixed empty gate is qualified.
    """
    result = {'schema': CHECKER_ID, 'status': 'rejected', 'reason': 'invalid_certificate'}
    try:
        if type(candidate) is not dict or set(candidate) != {'proposals'} \
                or type(candidate['proposals']) is not list or candidate['proposals']:
            return {**result, 'reason': 'candidate_not_exact_empty_response'}
        observed = _inspect(case, active_facet, focused_pattern)
        if observed['status'] != 'eligible':
            return {**result, 'reason': 'eligibility_not_reproduced'}
        if type(certificate) is not dict or digest(certificate) != digest(observed['certificate']):
            return {**result, 'reason': 'certificate_or_input_binding_mismatch'}
        gate = fixed.validate_response(deepcopy(candidate), case, active_facet, focused_pattern)
        if gate['status'] != 'qualified' or gate['errors']:
            return {**result, 'reason': 'fixed_gate_rejected'}
        return {**result, 'status': 'verified', 'reason': 'recomputed_strict_empty_rules_and_fixed_gate',
                'certificate_sha256': certificate['certificate_sha256'],
                'response_sha256': digest(candidate)}
    except Exception:
        return {**result, 'reason': 'verification_exception'}



def source_catalogue_is_known(catalogue, active_facet):
    """Prevent focus_pattern's defaults/filtering from converting unknown to [].

    Validate source containers and all membership selectors before the frozen
    focus function's output is allowed to obtain a certificate. Full selected
    rule bodies still face the existing conservative focused-pattern guard.
    """
    try:
        _json_domain(catalogue)
        _require(type(catalogue) is dict and all(k in catalogue for k in _COMMON_FIELDS), 'unknown_source_contract')
        _require(type(catalogue.get('facets')) is dict and active_facet in catalogue['facets'], 'unknown_source_facet')
        for collection in ('patterns', 'rules', 'model_semantic_rules'):
            rows = catalogue.get(collection)
            _require(type(rows) is list, 'unknown_source_container')
            for row in rows:
                _require(type(row) is dict and _text(row.get('id')), 'unknown_source_row')
                if collection == 'model_semantic_rules':
                    _require(_text(row.get('facet')) and _text(row.get('pattern_id')), 'unknown_source_ms_selector')
                else:
                    _require(_strings(row.get('facets')), 'unknown_source_legacy_selector')
                    _require('pattern_id' not in row or _text(row['pattern_id']), 'unknown_source_parent_selector')
        return True
    except Exception:
        return False
