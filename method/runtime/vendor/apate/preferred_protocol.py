"""Closed three-input projection and exhaustive semantic review protocol.

This module checks syntax, citations and original decision structure. It does
not classify ordinary language or infer a persona's preference direction.
Response conditions are a required closed object keyed by original condition
ID. Opportunity inputs retain their original ordered condition records. Earlier
array responses are rejected, never rewritten or silently repaired.
Status is the sole comparison disposition: supported denotes strict difference,
effect_equal equal effect, and the other source-review statuses retain their
specified absence/unknown/counterevidence meanings. There is no second private
comparison flag whose value could contradict that disposition.
Wire support uses supported_left or supported_right against the fixed neutral
unit pair. Private cells carry no source/target IDs; only final formal relations
use the deterministically decoded original endpoint IDs.
Every v6 cell binds the complete original unit context, cites both fixed
endpoint regions and accounts for the exact union of their original tasks.
Effects stay in left/right coordinates, independently of preferred direction.
"""
from copy import deepcopy
from itertools import combinations
import hashlib
import json
import math
import re

from .provider import ProviderError


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


PLAIN = 'plain'
AST = 'ast'
REF = 'reference'
OMIT = object()


def _map(spec):
    return ('map', spec)


def _union(*specs):
    return ('union', *specs)


def _fields(names, spec=PLAIN):
    return {name: spec for name in names.split()}


NODE = {**_fields('id label description meaning kind role', str), 'optional': bool}
ROLE = {**_fields('label name type description meaning', str),
        'discretion': REF, 'discretion_scopes': REF}
DEPENDUM = _fields('id kind label description meaning', str)
MODEL = {
    **_fields('id version root'), 'nodes': _map(NODE), 'roles': _map(_union(str, ROLE)),
    'refinements': [{**_fields('parent kind', str), 'children': [str]}],
    'hard_constraints': [_fields('type source target', str)],
    'contributions': [{'source': REF, 'target': str, 'type': str}],
    'dependencies': [{**_fields('id depender dependee depender_node dependee_node', str), 'dependum': DEPENDUM}],
    'role_discretion': _map(REF), 'initial_state': [str],
    'temporal_preferences': [{**_fields('id formula x y', _union(str, type(None)))}],
    'concerns': _map({**_fields('id label name description meaning kind', str), 'ast': AST}),
}
PERSONA = {**_fields('actor_id name description', str), 'role_ids': [str], 'facets': [str]}
SOLUTION = {**_fields('IF THEN OTHERWISE'),
    'branches': [{**_fields('rule_id facet Context Problem IF THEN OTHERWISE')}],
    'model_semantic_branches': [_fields('rule_id facet inference_profile status')]}
CPS = {**_fields('Context Problem'), 'Solution': SOLUTION}
INSTANTIATION = {
    **_fields('IF_THEN trigger guard context_effects_required timing_boundary'),
    'concern': _union(str, _fields('name criterion')),
    'comparison': _union(str, _fields('A B comparison_unit preferred other')),
    'output': _fields('type from to support formula status task_edge_condition relation scope kind plan_preference graph_rule'),
    'complete_plans': _fields('pi_a pi_b'),
    'counterexamples_unknown': [_union(str, _fields('context result'))],
}
LEGACY = {**_fields('id rule_id name facets pattern_ids pattern_id status construct_boundary inference_boundary rule_ids model_semantic_rule_ids'),
          'CPS': CPS, 'instantiation': INSTANTIATION}
QUALITY_REQUIREMENTS = _fields('original_quality_and_contributions_only same_original_or_decision fixed_same_rule_outcome strict_feasible_local_contrast composite_source_scope original_global_truth independent_acceptance')
REQUIRED_EVIDENCE = {**_fields('grammar outcome_id evidence_combination task_action_heads task_participation_heads interaction_nouns reciprocal_phrases consult_requires_interpersonal_object task_object_mentions_only_are_insufficient task_path_role allow_canonical_from_task_head_only allow_canonical_from_explicit_quality_contribution allowed_canonical_kinds quality_guard_namespace quality_modifiers quality_nouns reject_negated_or_conditional_quality_labels insufficient_terms insufficient_quality_semantics noncontact_examples provenance_fields description task_hosting_heads solitary_document_action_heads allow_canonical_from_certified_task_contrast certified_task_contrast solitary_written_use_heads written_use_evidence'),
                     'quality_evidence_requirements': QUALITY_REQUIREMENTS}
ANCHOR = {**_fields('id grammar description outcome_id allowed_kinds preferred_action_heads contrasted_action_heads requires_same_or_parent requires_same_material_object allow_implicit_object_from_or_parent allow_goal_labels_as_action task_action_head_only ambiguous_match_policy preferred_filing_forms contrasted_linear_forms reject_negated_or_unresolved_conditional_labels requires_guaranteed_task_across_nested_choices reject_counterpart_with_equivalent_index_structure'),
    'object_binding': _fields('policy implicit_object_source normalization preserve_distinguishing_modifiers reject_token_overlap_only different_objects'),
    'criterion': _fields('kind effect quality_binding evidence source_evidence'),
    'grammar_spec': _fields('preferred contrasted nonmatches no_goal_name_shortcut')}
MS = {**_fields('id facet pattern_id status allowed_kinds allowed_formulas preferred_semantics contrasted_semantics boundaries inference_boundary endpoint_contract'),
      'semantic_outcomes': [_fields('id description', str)],
      'required_semantic_evidence': REQUIRED_EVIDENCE,
      'canonical_semantic_anchors': [ANCHOR]}
PATTERN = {**_fields('version rule_schema branch_semantics inference_profile common_contract legacy_common_contract'),
    'facets': _map(_fields('label_zh domain patterns rule_ids construct_boundary evidence_status')),
    'patterns': [LEGACY], 'rules': [LEGACY], 'model_semantic_rules': [MS],
    'model_semantic_endpoint_contract': _fields('choice decision_authority optional_participation source_structure temporal'),
    'derived_criterion_contract': {
        **_fields('direction_preservation export_separation'),
        'canonical_task_semantics': _fields('basis quality_binding scope'),
        'decision_local_contribution': _fields('definition truth global_quality break_precedence composite_scope no_model_mutation provenance_fields')},
}


def _project(value, spec, path, dropped):
    if spec == PLAIN:
        if value is None or type(value) in (str, bool, int) or type(value) is float and math.isfinite(value):
            return deepcopy(value)
        if isinstance(value, list):
            return _project(value, [PLAIN], path, dropped)
    elif spec == REF:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return _project(value, [str], path, dropped)
        if isinstance(value, dict):
            return _project(value, AST, path, dropped)
    elif spec == AST:
        if isinstance(value, dict):
            out = {}
            for key, child in value.items():
                child_spec = ([AST] if key in ('and', 'or') else AST if key == 'not'
                              else REF if key in ('attains', 'before') else None)
                if child_spec is None:
                    dropped.append(path + '.' + str(key)); continue
                result = _project(child, child_spec, path + '.' + key, dropped)
                if result is not OMIT:
                    out[key] = result
            return out
    elif isinstance(spec, type):
        if type(value) is spec:
            return deepcopy(value)
    elif isinstance(spec, tuple) and spec[0] == 'union':
        for candidate in spec[1:]:
            trial = []
            result = _project(value, candidate, path, trial)
            if result is not OMIT:
                dropped.extend(trial); return result
    elif isinstance(spec, tuple) and spec[0] == 'map':
        if isinstance(value, dict):
            out = {}
            for key, child in value.items():
                if not isinstance(key, str):
                    dropped.append(path + '.' + str(key)); continue
                result = _project(child, spec[1], path + '.' + key, dropped)
                if result is not OMIT:
                    out[key] = result
            return out
    elif isinstance(spec, dict):
        if isinstance(value, dict):
            out = {}
            for key, child in value.items():
                if key not in spec:
                    dropped.append(path + '.' + str(key)); continue
                result = _project(child, spec[key], path + '.' + str(key), dropped)
                if result is not OMIT:
                    out[key] = result
            return out
    elif isinstance(spec, list) and isinstance(value, list):
        out = []
        for i, child in enumerate(value):
            result = _project(child, spec[0], path + '[' + str(i) + ']', dropped)
            if result is not OMIT:
                out.append(result)
        return out
    dropped.append(path)
    return OMIT


def project_inputs(persona, model, catalogue):
    """Separate unchanged source documents from the deep runtime allowlist."""
    dropped = []
    projected = {}
    for name, value, spec in (('persona', persona, PERSONA), ('goal_model', model, MODEL), ('pattern', catalogue, PATTERN)):
        result = _project(value, spec, name, dropped)
        if result is OMIT:
            raise ProviderError('The required ' + name + ' input must be an object.')
        projected[name] = result
    projected['hashes'] = {name: digest(projected[name]) for name in ('persona', 'goal_model', 'pattern')}
    projected['projection'] = {'policy': 'apate.preferred-runtime-allowlist.v1',
                               'dropped_paths': sorted(set(dropped))}
    return projected


def _texts(value):
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [text for item in value for text in _texts(item)]
    return []


def rules_for(catalogue, facets):
    selected = set(facets)
    safe = _project(catalogue, PATTERN, 'pattern', [])
    if safe is OMIT:
        raise ProviderError('The pattern catalogue must be an object.')
    rows = []
    for rule in safe.get('model_semantic_rules', []):
        if rule.get('facet') not in selected or 'choice' not in rule.get('allowed_kinds', []):
            continue
        conditions = _texts(rule.get('boundaries'))
        # Preferred/contrasted descriptions can enumerate alternative outcomes.
        # They remain intact in original, rather than becoming a conjunction
        # of necessary gates for every outcome-specific comparison below.
        if rule.get('required_semantic_evidence'):
            conditions.append('Required semantic evidence: ' + json.dumps(rule['required_semantic_evidence'], ensure_ascii=False, sort_keys=True))
        rows.append({'id': rule['id'], 'pattern_id': rule['pattern_id'], 'facet': rule['facet'],
                     'outcomes': deepcopy(rule.get('semantic_outcomes', [])),
                     'conditions': [{'id': 'c' + str(i), 'text': text} for i, text in enumerate(conditions)],
                     'original': deepcopy(rule)})
    legacy = list(safe.get('rules', []))
    known = {rule.get('id') for rule in legacy}
    legacy += [rule for rule in safe.get('patterns', []) if rule.get('id') not in known and 'instantiation' in rule]
    for rule in legacy:
        instantiation = rule.get('instantiation', {})
        if instantiation.get('output', {}).get('type') != 'preferred_to':
            continue
        concern = instantiation.get('concern', {})
        if isinstance(concern, str):
            concern = {'name': concern, 'criterion': concern}
        name = concern.get('name')
        if not isinstance(name, str) or not name:
            continue
        conditions = _texts(rule.get('CPS', {}).get('Solution', {}).get('IF'))
        for facet in rule.get('facets', []):
            if facet not in selected:
                continue
            parents = rule.get('pattern_ids', [])
            rows.append({'id': rule.get('rule_id', rule['id']),
                         'pattern_id': rule.get('pattern_id') or (parents[0] if parents else rule['id']),
                         'facet': facet, 'outcomes': [{'id': name, 'description': concern.get('criterion', name)}],
                         'conditions': [{'id': 'c' + str(i), 'text': text} for i, text in enumerate(conditions)],
                         'original': deepcopy(rule)})
    return rows


def units_for(persona, model, catalogue, index):
    rules = rules_for(catalogue, persona.get('facets', []))
    roles = persona.get('role_ids', [])
    role = roles[0] if roles else ''
    units = []
    original_ors = {ref['parent']: ref for ref in model.get('refinements', [])
                    if ref.get('kind') == 'OR' and model['nodes'][ref['parent']]['kind'] == 'goal'}
    for scope, refinement in sorted(original_ors.items()):
        decision = index.get('ORs', {}).get(scope, {})
        children = sorted(refinement['children'])
        indexed = sorted(decision.get('children', [])) == children
        for left, right in combinations(children, 2):
            for rule in rules:
                for outcome in rule['outcomes']:
                    identity = {'scope': scope, 'left': left, 'right': right,
                        'actor_id': persona.get('actor_id', ''), 'role_id': role,
                        'rule_id': rule['id'], 'pattern_id': rule['pattern_id'],
                        'facet': rule['facet'], 'outcome_id': outcome['id']}
                    conditions = deepcopy(rule['conditions'])
                    conditions.append({'id': 'c' + str(len(conditions)),
                        'text': 'Compare only fixed outcome ' + outcome['id'] + ': ' + outcome['description']
                                + '. Determine each complete alternative\'s effect on this same dimension.'})
                    units.append({'id': 'U_' + digest(identity)[:24], **identity,
                        'outcome_description': outcome['description'],
                        'conditions': conditions,
                        'authorized': indexed and bool(decision.get('authority', {}).get(role))})
    return units


STATUSES = ['supported', 'counterevidence', 'no_opportunity', 'effect_equal',
            'missing_basis', 'genuine_dispute', 'check_incomplete']
WIRE_STATUSES = ['supported_left', 'supported_right', *[s for s in STATUSES if s != 'supported']]
UNIT_CONTEXT_FIELDS = ('scope', 'left', 'right', 'actor_id', 'role_id', 'rule_id', 'facet', 'outcome_id')


def disposition(cell):
    """Read the explicit wire disposition without repairing an old response."""
    status = cell.get('status') if isinstance(cell, dict) else None
    if status not in WIRE_STATUSES or 'source' in cell or 'target' in cell:
        raise ProviderError('The cell must use an explicit supported direction or a known negative disposition.')
    return 'supported' if status in ('supported_left', 'supported_right') else status


def comparison_endpoints(cell, unit):
    """Decode only the model's explicit direction against neutral source IDs.

    No text, trait, outcome, proposed endpoint, reference or prior answer is used
    to infer, reverse, or correct the direction. Wire and sealed cells stay as
    received. Negative dispositions have no proposed endpoint pair.
    """
    status = disposition(cell)
    if status != 'supported':
        return '', ''
    if not isinstance(unit, dict):
        raise ProviderError('A comparison requires an original opportunity object.')
    left, right = unit.get('left'), unit.get('right')
    if not isinstance(left, str) or not isinstance(right, str) or not left or not right or left == right:
        raise ProviderError('A comparison requires two distinct original scalar alternatives.')
    return (left, right) if cell['status'] == 'supported_left' else (right, left)


def comparison_effects(cell, unit):
    """Decode fixed-coordinate effects by explicit status, without correction."""
    if disposition(cell) != 'supported':
        return '', ''
    comparison_endpoints(cell, unit)  # Validate the same original scalar pair.
    left, right = cell.get('left_effect'), cell.get('right_effect')
    if not isinstance(left, str) or not isinstance(right, str):
        raise ProviderError('Comparison effects require explicit fixed left/right strings.')
    return (left, right) if cell['status'] == 'supported_left' else (right, left)


def evidence_for(cell):
    """Return both neutral endpoint citations followed by additional evidence."""
    return deepcopy([cell['endpoint_evidence']['left'], cell['endpoint_evidence']['right'],
                     *cell['model_evidence']])


def coverage_for(cell):
    """Expose the exact fixed task map as a stable structural audit array."""
    return [{'node_id': node, 'reason': cell['implementation_coverage'][node]}
            for node in sorted(cell['implementation_coverage'])]


def _object(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


def _string(enum=None):
    return {'type': 'string', **({'enum': list(enum)} if enum is not None else {})}


def quotation_domain(text, *, allow_empty=False):
    """All neutral original sentence/line spans plus the unchanged full text.

    No facet, direction, proposal, count, outcome, lexical classifier or size
    budget selects these quotes. Splitting never joins separate source fields,
    rewrites wording, or makes a claim about what a quote semantically supports.
    """
    if not isinstance(text, str):
        raise ProviderError('Quotation context must contain original text strings.')
    quotes = [''] if allow_empty else []
    if text:
        quotes.append(text)
    for segment in re.split(r'(?<=[.!?。！？])\s+|[\r\n]+', text):
        quote = segment.strip()
        if quote and quote not in quotes:
            quotes.append(quote)
    return quotes


def schema_for(units, persona=None, model=None):
    """Closed v6 schema over original units, endpoint regions and task maps.

    Nonempty units require the original model. Quote values share an unchanged
    source domain; node/field/quote binding is checked mechanically below.
    A region with no original semantic text cannot produce a safe response and
    fails explicitly before transport instead of inventing a quotation.
    """
    if units and model is None:
        raise ProviderError('Original model context is required for endpoint evidence and task coverage.')
    evidence = _object({'node_id': _string(), 'field': _string(['label', 'description', 'meaning']), 'quote': _string()})
    definitions = {}
    persona_quote = _string()
    empty_model_quotes = False
    if persona is not None:
        if not isinstance(persona, dict):
            raise ProviderError('Persona quotation context must be an object.')
        definitions['persona_quote'] = _string(quotation_domain(persona.get('description', ''), allow_empty=True))
        persona_quote = {'$ref': '#/$defs/persona_quote'}
    if model is not None:
        if not isinstance(model, dict) or not isinstance(model.get('nodes', {}), dict):
            raise ProviderError('Model quotation context must contain an original node map.')
        nodes = model.get('nodes', {})
        if any(not isinstance(key, str) or not isinstance(node, dict) for key, node in nodes.items()):
            raise ProviderError('Original model quotation nodes require string IDs and node objects.')
        quotes = []
        for identity in sorted(nodes):
            for field in ('label', 'description', 'meaning'):
                if field not in nodes[identity]:
                    continue
                for quote in quotation_domain(nodes[identity][field]):
                    if quote.strip() and quote not in quotes:
                        quotes.append(quote)
        empty_model_quotes = not quotes
        definitions['model_quote'] = _string(quotes or [''])
        definitions['source_evidence'] = _object({'node_id': _string(sorted(nodes) or ['']),
            'field': _string(['label', 'description', 'meaning']), 'quote': {'$ref': '#/$defs/model_quote'}})
        evidence = {'$ref': '#/$defs/source_evidence'}
    cells = {}
    for unit in units:
        if unit['id'] in cells:
            raise ProviderError('Original opportunity unit IDs must be unique.')
        if any(not isinstance(unit.get(key), str) for key in UNIT_CONTEXT_FIELDS):
            raise ProviderError('Every original opportunity requires its complete scalar unit context.')
        regions = {side: _region(model, unit[side]) for side in ('left', 'right')}
        if any(node not in nodes for region in regions.values() for node in region):
            raise ProviderError('Every endpoint region must contain only original model nodes.')
        endpoint_evidence = {}
        for side, region in regions.items():
            identities = [node for node in sorted(region) if any(
                isinstance(nodes[node].get(field), str) and nodes[node][field].strip()
                for field in ('label', 'description', 'meaning'))]
            if not identities:
                raise ProviderError('No original semantic text is available in the ' + side + ' endpoint region.')
            endpoint_evidence[side] = _object({'node_id': _string(identities),
                'field': _string(['label', 'description', 'meaning']), 'quote': {'$ref': '#/$defs/model_quote'}})
        tasks = sorted(node for node in regions['left'] | regions['right'] if nodes[node].get('kind') == 'task')
        condition_ids = [row['id'] for row in unit['conditions']]
        if len(set(condition_ids)) != len(condition_ids):
            raise ProviderError('Original opportunity condition IDs must be unique.')
        condition = _object({'status': _string(['true', 'false', 'unknown']),
                             'reason': _string()})
        cells[unit['id']] = _object({
            'status': _string(WIRE_STATUSES), 'persona_quote': deepcopy(persona_quote),
            'unit_context': _object({key: _string([unit[key]]) for key in UNIT_CONTEXT_FIELDS}),
            'endpoint_evidence': _object(endpoint_evidence),
            'model_evidence': {'type': 'array', 'items': evidence, **({'maxItems': 0} if empty_model_quotes else {})},
            'conditions': _object({identity: deepcopy(condition) for identity in condition_ids}),
            'left_effect': _string(), 'right_effect': _string(),
            'implementation_coverage': _object({node: _string() for node in tasks}),
            'counterevidence': {'type': 'array', 'items': evidence, **({'maxItems': 0} if empty_model_quotes else {})}, 'reason': _string()})
    result = _object({'cells': _object(cells)})
    if definitions:
        result['$defs'] = definitions
    return result


def _validate_schema(value, schema, path='$', *, _root=None, _references=()):
    """Validate only this closed protocol and safe finite local definitions."""
    _root = schema if _root is None else _root
    if not isinstance(schema, dict):
        raise ProviderError(path + ' has an invalid private protocol schema.')
    if '$ref' in schema:
        reference = schema['$ref']
        if (set(schema) != {'$ref'} or not isinstance(reference, str)
                or not re.fullmatch(r'#/\$defs/[A-Za-z0-9_-]+', reference)):
            raise ProviderError(path + ' has an unsupported private schema reference.')
        if reference in _references or len(_references) >= 8:
            raise ProviderError(path + ' has a cyclic or excessive private schema reference chain.')
        definitions = _root.get('$defs', {})
        target = definitions.get(reference.rsplit('/', 1)[1]) if isinstance(definitions, dict) else None
        if not isinstance(target, dict):
            raise ProviderError(path + ' has an unresolved private schema reference.')
        return _validate_schema(value, target, path, _root=_root, _references=(*_references, reference))
    if schema.get('type') not in ('object', 'array', 'string'):
        raise ProviderError(path + ' has an unsupported private protocol schema type.')
    kind = schema['type']
    valid = {'object': lambda: type(value) is dict, 'array': lambda: type(value) is list,
             'string': lambda: type(value) is str}[kind]()
    if not valid:
        raise ProviderError(path + ' has the wrong JSON type.')
    if 'enum' in schema and value not in schema['enum']:
        raise ProviderError(path + ' is outside the closed value domain.')
    if kind == 'object':
        if set(value) != set(schema['properties']):
            raise ProviderError(path + ' must contain exactly the required fields.')
        for key, child in value.items():
            _validate_schema(child, schema['properties'][key], path + '.' + key,
                             _root=_root, _references=_references)
    elif kind == 'array':
        if len(value) < schema.get('minItems', 0) or len(value) > schema.get('maxItems', float('inf')):
            raise ProviderError(path + ' has the wrong number of records.')
        for i, child in enumerate(value):
            _validate_schema(child, schema['items'], path + '[' + str(i) + ']',
                             _root=_root, _references=_references)


def _region(model, node):
    refs = {row['parent']: row['children'] for row in model.get('refinements', [])}
    result = set()
    def visit(identity):
        if identity in result:
            return
        result.add(identity)
        for child in refs.get(identity, []):
            visit(child)
    visit(node)
    return result


def validate_response(response, units, persona, model):
    _validate_schema(response, schema_for(units, persona=persona, model=model))
    description = persona.get('description', '')
    for unit in units:
        cell = response['cells'][unit['id']]
        quote = cell['persona_quote']
        if quote and (not quote.strip() or quote not in description):
            raise ProviderError('Persona evidence must be a literal original description quotation.')
        for evidence in evidence_for(cell) + cell['counterevidence']:
            value = model.get('nodes', {}).get(evidence['node_id'], {}).get(evidence['field'])
            if (not isinstance(value, str) or not evidence['quote'].strip() or evidence['quote'] not in value):
                raise ProviderError('Model evidence must quote one original semantic field literally.')
        if set(cell['conditions']) != {row['id'] for row in unit['conditions']}:
            raise ProviderError('Every necessary condition must be reviewed exactly once.')
        if not cell['reason'].strip():
            raise ProviderError('Every semantic disposition requires an explicit reason.')
        if disposition(cell) != 'supported':
            continue
        source, target = comparison_endpoints(cell, unit)
        if not unit['authorized']:
            raise ProviderError('A supported relation requires original decision authority.')
        refs = [r for r in model.get('refinements', []) if r['parent'] == unit['scope'] and r['kind'] == 'OR']
        if not refs or not {unit['left'], unit['right']} <= set(refs[0]['children']):
            raise ProviderError('Supported endpoints must be different direct children of one original OR.')
        if ({source, target} != {unit['left'], unit['right']}
                or not quote.strip()
                or not cell['left_effect'].strip() or not cell['right_effect'].strip()
                or cell['left_effect'] == cell['right_effect']
                or any(row['status'] != 'true' for row in cell['conditions'].values())):
            raise ProviderError('A supported cell lacks a strict, evidenced comparison with all necessary premises true.')
        left = _region(model, unit['left']); right = _region(model, unit['right'])
        cited = {row['node_id'] for row in evidence_for(cell)}
        if not cited.intersection(left) or not cited.intersection(right):
            raise ProviderError('Evidence must cover each complete compared subtree; parent-only citations are insufficient.')
        coverage = coverage_for(cell)
        identities = [row['node_id'] for row in coverage]
        tasks = {node for node in left | right if model['nodes'][node]['kind'] == 'task'}
        if (set(identities) != tasks or any(not row['reason'].strip() for row in coverage)):
            raise ProviderError('Implementation coverage must explain every original task in both endpoint subtrees.')
