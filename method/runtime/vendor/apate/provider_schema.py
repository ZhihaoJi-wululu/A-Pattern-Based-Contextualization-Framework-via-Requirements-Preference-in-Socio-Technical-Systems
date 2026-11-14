"""Closed completion shapes derived only from current model inputs.

These constraints prevent invented identifiers; independent validation still
decides evidence, scope, effects, authorization and feasible preferences.
"""


def _object(properties):
    return {'type': 'object', 'properties': properties,
            'required': list(properties), 'additionalProperties': False}


def _enum(values):
    return {'type': 'string', 'enum': sorted(set(values))}


def _array(items, *, nonempty=False):
    result = {'type': 'array', 'items': items}
    if nonempty:
        result['minItems'] = 1
    return result


def _alternatives(branches):
    # Empty enums/anyOf are invalid schemas. An empty array needs no item enum.
    if not branches:
        return {'type': 'array', 'items': _object({}), 'maxItems': 0}
    return _array({'anyOf': branches})


def _shared_enums(schema):
    """Keep repeated identifier lists within the strict provider enum budget."""
    counts, definitions, names = {}, {}, {}
    def visit(value, replace=False):
        if isinstance(value, dict):
            values = tuple(value.get('enum', []))
            if values:
                if not replace:
                    counts[values] = counts.get(values, 0) + 1
                elif counts[values] > 1:
                    if values not in names:
                        name = 'identifiers_' + str(len(names) + 1)
                        names[values] = name
                        definitions[name] = _enum(values)
                    return {'$ref': '#/$defs/' + names[values]}
            return {key: visit(child, replace) for key, child in value.items()}
        if isinstance(value, list):
            return [visit(child, replace) for child in value]
        return value
    visit(schema)
    output = visit(schema, True)
    if definitions:
        output['$defs'] = definitions
    return output


def primary_concern_ids(session):
    """Require a review of each explicit criterion, or all imported criteria."""
    concerns = session.get('concerns', {})
    registered = [key for key, row in concerns.items()
                  if isinstance(key, str) and isinstance(row, dict)]
    explicit = [key for key in registered
                if concerns[key].get('origin') != 'imported_quality_contributions']
    return sorted(explicit or registered)


def _criterion_leaves(view, expression):
    """Return structural dependencies, never their desirability or truth."""
    if not isinstance(expression, dict) or len(expression) != 1:
        raise ValueError('A registered criterion needs one supported AST operator.')
    operation, value = next(iter(expression.items()))
    if operation == 'attains':
        return view.endpoint_leaves(value)
    if operation == 'before' and isinstance(value, list) and len(value) == 2:
        return frozenset().union(*(view.endpoint_leaves(item) for item in value))
    if operation == 'not':
        return _criterion_leaves(view, value)
    if operation in ('and', 'or') and isinstance(value, list) and value:
        return frozenset().union(*(_criterion_leaves(view, item) for item in value))
    raise ValueError('Unsupported registered criterion AST.')


def _true_facts(view, facts, predicates):
    output = {}
    for predicate in predicates:
        output[predicate] = {}
        for identity, fact in facts.items():
            if fact.get('predicate') != predicate or fact.get('value') is not True:
                continue
            try:
                output[predicate][identity] = view.fact_scope(fact)
            except ValueError:
                continue
    return output


def _covering_facts(facts, leaves):
    return {predicate: {identity: scope for identity, scope in values.items()
                        if scope is None or leaves <= scope}
            for predicate, values in facts.items()}


def _bindings(facts):
    if any(not values for values in facts.values()):
        return None
    return _object({predicate: _enum(values) for predicate, values in facts.items()})


def _canonical_optional_anchor(view, expression, optional, review):
    """Direct attainment names the activity scope used in the final model."""
    if not isinstance(expression, dict) or set(expression) != {'attains'}:
        return None
    try:
        identities = view.endpoint_nodes(expression['attains'])
    except ValueError:
        return None
    if len(identities) != 1 or identities[0] not in optional:
        return None
    identity = identities[0]
    if review is not None and review in view.leaves(identity):
        return None
    return identity


def _canonical_current_work_pair(view, expression, work, business):
    """Use a direct before criterion's exact legal recorded operands."""
    if not isinstance(expression, dict) or set(expression) != {'before'}:
        return None
    pair = expression['before']
    if not isinstance(pair, list) or len(pair) != 2 or any(not isinstance(key, str) for key in pair):
        return None
    x, y = pair
    if x not in business or y not in business:
        return None
    for record in work.values():
        if record.get('remaining') != x or y not in record.get('diversion', []):
            continue
        try:
            unit = view.endpoint_leaves(record['work_unit'])
            checkpoint = view.endpoint_leaves(record['checkpoint'])
        except (KeyError, ValueError):
            continue
        if checkpoint and checkpoint <= unit and view.leaves(x) <= unit:
            return (x, y)
    return None


def completion_schema(session, packet):
    """Prune necessary structural impossibilities, retaining validator authority.

    This does not read candidates, gold/reference outputs, labels or witness
    effects. Criterion dependency is necessary for local non-temporal effects;
    temporal criteria are deliberately exempt from this site dependency test.
    Direct single-node attainment criteria use that exact legal optional node
    as a canonical representation of the registered activity scope.
    """
    from apate.contextualize import _ModelView
    view = _ModelView(session['model'])
    nodes = view.nodes
    role = (session.get('persona', {}).get('role_ids') or [None])[0]
    business = sorted(key for key, node in nodes.items()
                      if node.get('kind') in ('goal', 'task') and view.leaves(key)
                      and view.authorized(role, key))
    all_business = sorted(key for key, node in nodes.items()
                          if node.get('kind') in ('goal', 'task'))
    concerns = sorted(set(session.get('concerns', {})) & set(packet.get('concerns', {})))
    non_temporal = [key for key in concerns
                    if not (isinstance(session['concerns'][key].get('ast'), dict)
                            and set(session['concerns'][key]['ast']) == {'before'})]
    dependencies = {}
    for key in concerns:
        try:
            dependencies[key] = _criterion_leaves(view, session['concerns'][key].get('ast'))
        except ValueError:
            continue
    optional = {key: view.optional_scope(key) for key in business}
    optional = {key: scope for key, scope in optional.items() if scope is not None}
    choices = []
    for parent, refinement in view.refs.items():
        if refinement['kind'] != 'OR' or nodes[parent]['kind'] != 'goal':
            continue
        for left in refinement['children']:
            for right in refinement['children']:
                if left == right:
                    continue
                a, b = view.leaves(left), view.leaves(right)
                source = [key for key in business if view.leaves(key) <= a]
                target = [key for key in business if view.leaves(key) <= b]
                if source and target:
                    choices.append((parent, a, b, source, target))
    rules = packet.get('rules', {})
    patterns = set(packet.get('patterns', {}))
    roles = session['model'].get('roles', {})
    reviews = sorted(key for key, node in nodes.items()
                     if node.get('kind') == 'task' and node.get('role') in roles
                     and node.get('role') != role)
    facts = session.get('context', {}).get('facts', {})
    work = session.get('context', {}).get('current_work', {})
    current_pairs = {key: _canonical_current_work_pair(view, session['concerns'][key].get('ast'), work, business)
                     for key in concerns}
    branches = []
    for rule_id, rule in rules.items():
        parents = sorted(set(rule.get('pattern_ids', [])) & patterns)
        fact_domains = _true_facts(view, facts, rule.get('required_predicates', []))
        if not parents or not concerns or _bindings(fact_domains) is None:
            continue
        base = {'id': {'type': 'string'}, 'pattern_id': _enum(parents), 'rule_id': _enum([rule_id])}
        for kind in rule.get('allowed_kinds', []):
            common = {**base, 'kind': _enum([kind])}
            review_ids = reviews if rule.get('requires_review_node') else [None]
            for review in review_ids:
                properties = dict(common)
                if review is not None:
                    properties['review_node'] = _enum([review])
                if kind == 'choice':
                    for parent, a, b, source, target in choices:
                        criteria = [key for key in non_temporal if dependencies.get(key, set()) & view.leaves(parent)]
                        # A covering fact must touch both implementations, but
                        # need not cover every task in the enclosing OR region.
                        scoped = {predicate: {identity: scope for identity, scope in values.items()
                                              if scope is None or scope & a and scope & b}
                                  for predicate, values in fact_domains.items()}
                        source_ids = [key for key in source if _bindings(_covering_facts(scoped, view.leaves(key))) is not None]
                        target_ids = [key for key in target if _bindings(_covering_facts(scoped, view.leaves(key))) is not None]
                        if review is not None:
                            source_ids = [key for key in source_ids if review not in view.leaves(key)]
                        bindings = _bindings(scoped)
                        if not criteria or not source_ids or not target_ids or bindings is None:
                            continue
                        def endpoint(ids):
                            return {'anyOf': [_enum(ids), _array(_enum(ids), nonempty=True)]}
                        branches.append(_object({**properties, 'concern_id': _enum(criteria),
                            'fact_bindings': bindings, 'source': endpoint(source_ids), 'target': endpoint(target_ids)}))
                elif kind == 'optional_participation':
                    formulas = rule.get('allowed_formulas', [])
                    if not formulas:
                        continue
                    canonical = {key: _canonical_optional_anchor(view, session['concerns'][key].get('ast'), optional, review)
                                 for key in concerns}
                    for anchor, scope in optional.items():
                        # An activity cannot finish before its own review leaf.
                        if review is not None and review in view.leaves(anchor):
                            continue
                        criteria = [key for key in non_temporal if dependencies.get(key, set()) & view.leaves(scope)
                                    and canonical[key] in (None, anchor)]
                        bindings = _bindings(_covering_facts(fact_domains, view.leaves(anchor)))
                        if criteria and bindings is not None:
                            branches.append(_object({**properties, 'concern_id': _enum(criteria),
                                'fact_bindings': bindings, 'x': _enum([anchor]), 'formula': _enum(formulas)}))
                elif kind == 'temporal':
                    formulas = rule.get('allowed_formulas', [])
                    if not business or not formulas:
                        continue
                    temporal = {**properties, 'formula': _enum(formulas), 'concern_id': _enum(concerns)}
                    if rule.get('requires_current_work'):
                        for work_id, record in work.items():
                            remaining = record.get('remaining')
                            if remaining not in business:
                                continue
                            for diversion in record.get('diversion', []):
                                if diversion not in business:
                                    continue
                                leaves = view.leaves(remaining) | view.leaves(diversion)
                                bindings = _bindings(_covering_facts(fact_domains, leaves))
                                criteria = [key for key in concerns if current_pairs[key] in (None, (remaining, diversion))]
                                if bindings is not None and criteria:
                                    branches.append(_object({**temporal, 'concern_id': _enum(criteria), 'fact_bindings': bindings,
                                        'current_work_id': _enum([work_id]), 'x': _enum([remaining]), 'y': _enum([diversion])}))
                    else:
                        branches.append(_object({**temporal, 'fact_bindings': _bindings(fact_domains),
                            'x': _enum(business), 'y': _enum(business)}))

    deferred = [_object({'rule_id': _enum([key]),
                         'missing_predicates': _array(_enum(rule['required_predicates'])),
                         'reason': {'type': 'string'}})
                for key, rule in rules.items() if rule.get('required_predicates')]
    source_refs = []
    for key, source in packet.get('sources', {}).items():
        spans = source.get('spans', {})
        if source.get('kind') == 'user_provided_persona_context' and spans:
            source_refs.append(_object({'source_id': _enum([key]), 'span_id': _enum(spans)}))
    gaps = [_object({'rule_id': _enum([key]), 'scope_ids': _array(_enum(all_business), nonempty=True),
                     'missing_predicates': _array(_enum(rule['required_predicates']), nonempty=True),
                     'evidence_refs': _array({'anyOf': source_refs}, nonempty=True)})
            for key, rule in rules.items()
            if all_business and source_refs and rule.get('required_predicates')]
    concern_review = _object({'status': _enum(['proposed', 'not_applicable', 'needs_information']),
                              'candidate_ids': _array({'type': 'string'})})
    reviewed_rules = (_array(_enum(rules)) if rules else
                      {'type': 'array', 'items': {'type': 'string'}, 'maxItems': 0})
    return _shared_enums(_object({'candidates': _alternatives(branches), 'reviewed_rule_ids': reviewed_rules,
                    'deferred': _alternatives(deferred), 'evidence_gaps': _alternatives(gaps),
                    'concern_reviews': _object({key: concern_review for key in primary_concern_ids(session)})}))
