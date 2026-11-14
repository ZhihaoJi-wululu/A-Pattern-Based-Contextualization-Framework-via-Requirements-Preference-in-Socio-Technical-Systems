"""Pure local string-enum projection of existing choice-protocol ID invariants.

No semantics, preferred direction, output count, oracle, retry or transport code
enters this module. The fixed validator remains the final authority for every
proposal. A derived enum is a necessary ID domain, not a validity certificate.
"""
from copy import deepcopy
import hashlib
import json

from apate.preferred_protocol import rules_for
from apate.preferred_structure import authorized
from apate.schema import validate_model

MODULE_ID = 'apate.original-structural-id-string-enums.v1'
DEFAULT_MAX_ENUM_VALUES = 256
DEFAULT_MAX_ENUM_UTF8_BYTES = 16384
_FIELDS = ('scope', 'source', 'target', 'rule_id', 'outcome_id', 'model_evidence.node_id')


def canonical_sha256(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _string_ids(values):
    """No bool/numeric coercion, text normalization or prefix-based selection."""
    return sorted({value for value in values if type(value) is str and value.strip()})


def _field_schema(schema, field):
    try:
        properties = schema['properties']['proposals']['items']['properties']
        if field == 'model_evidence.node_id':
            return properties['model_evidence']['items']['properties']['node_id']
        return properties[field]
    except (KeyError, TypeError):
        return None


def _original_model(case):
    if not isinstance(case, dict):
        return None
    source = case.get('source_document')
    if isinstance(source, dict) and 'model' in source:
        return source['model']
    return case.get('goal_model', case.get('model'))


def _domains(case, facet, pattern):
    """Use the same structural authority and choice-rule resolvers as acceptance.

    None means context could not be safely derived. Empty means no IDs exist in
    that domain. Both preserve the corresponding original field schema.
    """
    domains = dict.fromkeys(_FIELDS)
    diagnostics = {}
    try:
        raw_model = _original_model(case)
        model = validate_model(raw_model)
        nodes = model['nodes']
        domains['model_evidence.node_id'] = _string_ids(nodes)
        persona = case.get('persona') if isinstance(case, dict) else None
        roles = persona.get('role_ids') if isinstance(persona, dict) else None
        if (not isinstance(roles, list) or not roles
                or any(type(role) is not str or not role for role in roles)
                or len(roles) != len(set(roles))
                or any(role not in model.get('roles', {}) for role in roles)):
            diagnostics['decision_domains'] = 'invalid_original_role_binding'
        else:
            scopes, endpoints = [], []
            for refinement in model.get('refinements', []):
                scope = refinement['parent']
                if refinement['kind'] != 'OR' or nodes[scope].get('kind') != 'goal':
                    continue
                # Match the fixed acceptance condition exactly; execution-role
                # ownership alone and ancestor ownership provide no extra grant.
                if sum(bool(authorized(model, role, scope)) for role in roles) != 1:
                    continue
                scopes.append(scope)
                endpoints.extend(refinement['children'])
            domains['scope'] = _string_ids(scopes)
            domains['source'] = _string_ids(endpoints)
            domains['target'] = _string_ids(endpoints)
    except (ValueError, TypeError, KeyError, AttributeError):
        diagnostics['model_domains'] = 'invalid_original_model_context'
    try:
        if type(facet) is not str or not facet:
            raise ValueError('active facet must be an original string ID')
        rules = rules_for(pattern, [facet])
        # All choice rules/outcomes are included without a semantic applicability
        # test. A rule/outcome pairing is still checked by the fixed validator.
        domains['rule_id'] = _string_ids(rule['id'] for rule in rules)
        domains['outcome_id'] = _string_ids(
            outcome['id'] for rule in rules for outcome in rule['outcomes'])
    except (ValueError, TypeError, KeyError, AttributeError):
        diagnostics['rule_domains'] = 'invalid_original_rule_context'
    return domains, diagnostics


def derive_response_schema(base_schema, case, active_facet, pattern, *,
        max_enum_values=DEFAULT_MAX_ENUM_VALUES,
        max_enum_utf8_bytes=DEFAULT_MAX_ENUM_UTF8_BYTES):
    """Return ``{'schema': deep_copy, 'metadata': provenance}`` without mutation.

    At most one existing ``enum`` keyword is added to each of six existing
    string fields. The evidence ``field`` enum, all eight proposal fields,
    required keys, field types and quote/reason contracts remain unchanged.
    Source and target use the same union of direct children of eligible ORs;
    no direction is chosen and no pairwise/semantic acceptance is attempted.

    Internal per-field size caps are implementation limits, not asserted
    provider limits. Empty/oversized/invalid domains leave that entire original
    field schema intact. Values are never truncated and no placeholder IDs or
    empty enums are created. A zero cap intentionally preserves all fields.
    """
    if type(base_schema) is not dict:
        raise TypeError('base_schema must be a schema object, not a bool or scalar')
    for name, limit in (('max_enum_values', max_enum_values),
                        ('max_enum_utf8_bytes', max_enum_utf8_bytes)):
        if type(limit) is not int or limit < 0:
            raise ValueError(name + ' must be a nonnegative integer, not bool')
    derived = deepcopy(base_schema)
    domains, context_diagnostics = _domains(case, active_facet, pattern)
    records = []
    for field in _FIELDS:
        values = domains[field]
        target = _field_schema(derived, field)
        record = {'field': field, 'domain_size': len(values) if values is not None else None}
        if values is None:
            record['status'] = 'invalid_context_preserved'
        elif not values:
            record['status'] = 'empty_domain_preserved'
        elif not isinstance(target, dict) or target.get('type') != 'string':
            record['status'] = 'base_field_not_string_preserved'
        else:
            # Preserve an already narrower original enum, if present. Standard
            # SCHEMA has no enums at these six locations; its field enum is not
            # visited or modified here.
            narrowed = values
            if 'enum' in target:
                existing = target['enum']
                if (not isinstance(existing, list)
                        or any(type(item) is not str for item in existing)):
                    record['status'] = 'unsupported_existing_enum_preserved'
                    records.append(record)
                    continue
                narrowed = [value for value in values if value in existing]
            encoded_bytes = len(json.dumps(narrowed, ensure_ascii=False,
                separators=(',', ':'), allow_nan=False).encode('utf-8'))
            record.update(enum_values=len(narrowed), enum_utf8_bytes=encoded_bytes,
                domain_sha256=canonical_sha256(values))
            if not narrowed:
                record['status'] = 'empty_intersection_preserved'
            elif len(narrowed) > max_enum_values or encoded_bytes > max_enum_utf8_bytes:
                record['status'] = 'oversize_domain_preserved'
            else:
                target['enum'] = deepcopy(narrowed)
                record['status'] = 'applied_original_id_enum'
        records.append(record)
    metadata = {'module_id': MODULE_ID,
        'base_schema_sha256': canonical_sha256(base_schema),
        'derived_schema_sha256': canonical_sha256(derived),
        'limits': {'max_enum_values_per_field': max_enum_values,
                   'max_enum_utf8_bytes_per_field': max_enum_utf8_bytes},
        'fields': records, 'context_diagnostics': context_diagnostics,
        'scope': 'Necessary original ID domains only; no semantic applicability, direction, count, evidence truth, rule/outcome pairing or same-OR pair certificate.',
        'fallback': 'Preserve original field schema without truncating a domain or inventing IDs.',
        'final_acceptance': 'Unchanged fixed validator and mechanical checks.'}
    return {'schema': derived, 'metadata': metadata}
