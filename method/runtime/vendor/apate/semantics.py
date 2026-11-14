"""Finite monotone paper semantics, with first-attainment diagnostics kept separate."""
from functools import lru_cache
from copy import deepcopy

def _refs(model):
    return {r['parent']: r for r in model.get('refinements', [])}

def selected_attainment_model(model, sequence):
    """An adopted optional branch counts until completed after Fig.2(A).

    The original AND may ignore an optional child for mandatory satisfaction,
    but the compiled wrapper selected that child's method. Its performance is
    part of the parent's normalized attainment formula. Omitted wrappers need
    a real dummy trace if that parent's timing is being used as evidence.
    """
    effective = deepcopy(model)
    refs = _refs(effective)
    done = set(sequence)
    @lru_cache(None)
    def leaves(key):
        if effective['nodes'][key]['kind'] == 'task': return frozenset({key})
        return frozenset().union(*(leaves(c) for c in refs.get(key, {}).get('children', [])))
    for key, node in effective['nodes'].items():
        if node['kind'] in {'goal', 'task'} and node.get('optional') and leaves(key) & done:
            node['optional'] = False
    for ref in refs.values():
        if ref['kind'] == 'OR' and effective['nodes'][ref['parent']]['kind'] == 'goal':
            active = [child for child in ref['children'] if leaves(child) & done]
            # An unselected all-optional alternative must not become true by
            # an empty conjunction in the flat business interpretation.
            if active: ref['children'] = active
    return effective

def omitted_optional_timing(model, key, sequence):
    """A flat business sequence cannot date hidden skip operators exactly."""
    if not isinstance(key, str):
        values = key if isinstance(key, (list, tuple)) else key.get('tasks', [key.get('goal')]) if isinstance(key, dict) else []
        return any(omitted_optional_timing(model, k, sequence) for k in values)
    refs, done = _refs(model), set(sequence)
    @lru_cache(None)
    def leaves(n):
        if model['nodes'][n]['kind'] == 'task': return frozenset({n})
        return frozenset().union(*(leaves(c) for c in refs.get(n, {}).get('children', [])))
    def visit(n):
        ref = refs.get(n, {})
        children = ref.get('children', [])
        if ref.get('kind') == 'OR':
            # A complete witness chooses one OR branch. Hidden dummies in
            # the other methods cannot affect this goal's attainment time.
            active = [child for child in children if leaves(child) & done]
            if active: children = active
        for child in children:
            if model['nodes'][child].get('optional') and not leaves(child) & done: return True
            if visit(child): return True
        return False
    return key in model['nodes'] and model['nodes'][key]['kind'] in {'goal', 'task'} and visit(key)

def attained(model, node_id, done):
    if isinstance(node_id, (list, tuple, set)):
        return all(attained(model, n, done) for n in node_id)
    nodes = model['nodes']
    if node_id not in nodes:
        return False
    if nodes[node_id]['kind'] == 'task':
        return node_id in done
    ref = _refs(model).get(node_id)
    if not ref:
        return False
    children = [c for c in ref['children'] if not nodes[c].get('optional')] if ref['kind'] == 'AND' else ref['children']
    values = [attained(model, c, done) for c in children]
    return all(values) if ref['kind'] == 'AND' else any(values)

def attainment_formula(model, node_id):
    nodes = model['nodes']
    if nodes[node_id]['kind'] == 'task':
        return {'predicate': 'v_' + node_id}
    ref = _refs(model).get(node_id)
    if not ref:
        return {'constant': False}
    children = [c for c in ref['children'] if not nodes[c].get('optional')] if ref['kind'] == 'AND' else ref['children']
    return {ref['kind'].lower(): [attainment_formula(model, c) for c in children]}

def quality_satisfied(model, node_id, done, *, effective_model=None):
    """Three-valued final quality; hidden skip evidence remains unknown."""
    refs = _refs(model)
    effective = effective_model if effective_model is not None else selected_attainment_model(model, done)
    def conjunction(values):
        return False if False in values else None if None in values else True
    def disjunction(values):
        return True if True in values else None if None in values else False
    @lru_cache(None)
    def source_truth(source):
        if model['nodes'][source]['kind'] != 'task' and omitted_optional_timing(model, source, done):return None
        return attained(effective, source, done)
    @lru_cache(None)
    def evaluate(key):
        edges = [c for c in model.get('contributions', []) if c['target'] == key]
        positives = [source_truth(c['source']) for c in edges if c['type'] == 'makes']
        ref = refs.get(key)
        if ref:
            children = [c for c in ref['children'] if not model['nodes'][c].get('optional')] if ref['kind'] == 'AND' else ref['children']
            values = [evaluate(c) for c in children]
            positives.append(conjunction(values) if ref['kind'] == 'AND' else disjunction(values))
        breaks = disjunction([source_truth(c['source']) for c in edges if c['type'] == 'breaks'])
        no_breaks = None if breaks is None else not breaks
        return conjunction([disjunction(positives), no_breaks])
    return evaluate(node_id)

def quality_formula(model, node_id):
    edges = [c for c in model.get('contributions', []) if c['target'] == node_id]
    ref = _refs(model).get(node_id)
    child = {'constant': False}
    if ref:
        children = [c for c in ref['children'] if not model['nodes'][c].get('optional')] if ref['kind'] == 'AND' else ref['children']
        child = {ref['kind'].lower(): [quality_formula(model, c) for c in children]}
    makes = [attainment_formula(model, c['source']) for c in edges if c['type'] == 'makes']
    breaks = [{'not': attainment_formula(model, c['source'])} for c in edges if c['type'] == 'breaks']
    return {'and': [{'or': makes + [child]}] + breaks}

def temporal_ast(formula, x, y=None):
    if formula == 'sometime': return {'sometime': x}
    if formula == 'never': return {'always': {'not': x}}
    if formula == 'precedes': return {'sometime-before': [{'and': [x, y]}, {'and': [x, {'not': y}]}]}
    if formula == 'require_before': return {'sometime-before': [y, x]}
    if formula == 'require_after': return {'sometime-after': [y, x]}
    if formula == 'never_before': return temporal_ast('precedes', y, x)
    if formula == 'never_after': return temporal_ast('precedes', x, y)
    raise ValueError('Unknown temporal template: ' + str(formula))

def sexpr(ast):
    if isinstance(ast, str): return ast
    if 'predicate' in ast: return '(' + ast['predicate'] + ')'
    if 'constant' in ast: return '(and)' if ast['constant'] else '(or)'
    key, value = next(iter(ast.items()))
    items = value if isinstance(value, list) else [value]
    return '(' + key + ((' ' + ' '.join(sexpr(v) for v in items)) if items else '') + ')'

def temporal_pddl(model, pref):
    x = attainment_formula(model, pref['x'])
    y = attainment_formula(model, pref['y']) if pref.get('y') else None
    return sexpr(temporal_ast(pref['formula'], x, y))

def finite_temporal(values_x, values_y, formula):
    """Table4 under Gerevini & Long (2005), including initial/final states."""
    if formula == 'sometime': return any(values_x)
    if formula == 'never': return not any(values_x)
    if formula == 'never_before': return finite_temporal(values_y, values_x, 'precedes')
    if formula == 'never_after': return finite_temporal(values_x, values_y, 'precedes')
    if formula == 'precedes':
        trigger = [a and b for a, b in zip(values_x, values_y)]
        response = [a and not b for a, b in zip(values_x, values_y)]
        return all(not value or any(response[:i]) for i, value in enumerate(trigger))
    if formula == 'require_before':
        return all(not value or any(values_x[:i]) for i, value in enumerate(values_y))
    if formula == 'require_after':
        return all(not value or any(values_x[i:]) for i, value in enumerate(values_y))
    raise ValueError('Unknown temporal template: ' + str(formula))

def temporal_report(model, sequence, pref):
    if omitted_optional_timing(model, pref['x'], sequence) or (pref.get('y') and omitted_optional_timing(model, pref['y'], sequence)):
        return {'paper_literal': None, 'first_attainment': None, 'divergent': False, 'first_x': None, 'first_y': None,
                'formula': pref['formula'], 'note': 'A referenced goal contains omitted optional branches; supply the normalized SHOP2 trace including dummy operators.'}
    model = selected_attainment_model(model, sequence)
    states, done = [set()], set()
    for task in sequence:
        done = done | {task}
        states.append(done)
    vx = [attained(model, pref['x'], state) for state in states]
    vy = [attained(model, pref['y'], state) for state in states] if pref.get('y') else []
    tx = next((i for i, v in enumerate(vx) if v), None)
    ty = next((i for i, v in enumerate(vy) if v), None)
    f = pref['formula']
    literal = finite_temporal(vx, vy, f)
    if f == 'sometime': intended = tx is not None
    elif f == 'never': intended = tx is None
    elif f == 'precedes': intended = tx is None or ty is None or tx < ty
    elif f == 'require_before': intended = ty is None or (tx is not None and tx < ty)
    elif f == 'require_after': intended = ty is None or (tx is not None and tx > ty)
    elif f == 'never_before': intended = tx is None or ty is None or ty < tx
    else: intended = tx is None or ty is None or tx < ty
    return {'paper_literal': literal, 'first_attainment': intended, 'divergent': literal != intended,
            'first_x': tx, 'first_y': ty, 'formula': f,
            'note': 'Table4 sometime-after permits j>=i; first-attainment order is a separate diagnostic.' if f == 'require_after' else ''}

def validate_plan(model, sequence):
    """Check a flat witness using SHOP2's first-primitive method-start boundary.

    Goal guards are checked when the first selected descendant starts, not on
    every descendant action. This follows the actual vendored SHOP2 search,
    whose method expansion commits together with its first primitive action.
    Empty optional-only goals have no visible first action. Compiled plans
    can also be checked on the
    normalized model with dummy actions retained.
    """
    errors = []
    nodes, refs = model['nodes'], _refs(model)
    if not isinstance(sequence, list) or any(not isinstance(t, str) for t in sequence):
        return {'valid': False, 'errors': ['The task sequence must be a list of strings.'], 'qualities': {}, 'temporal': {}, 'goal_starts': {}}
    if len(set(sequence)) != len(sequence): errors.append('Duplicate tasks are not allowed in the current single-run task fragment.')
    for t in sequence:
        if nodes.get(t, {}).get('kind') != 'task': errors.append(f'Unknown or non-leaf task:{t}')
    @lru_cache(None)
    def leaves(key):
        if nodes[key]['kind'] == 'task': return frozenset({key})
        return frozenset().union(*(leaves(c) for c in refs.get(key, {}).get('children', [])))
    selected = set(sequence)
    if not selected <= leaves(model['root']): errors.append('Tasks exist outside the root business process.')
    def structural(key):
        if nodes[key]['kind'] == 'task': return key in selected
        ref = refs.get(key)
        if not ref: return False
        active = [c for c in ref['children'] if leaves(c) & selected]
        if ref['kind'] == 'OR': return len(active) == 1 and structural(active[0])
        required = [c for c in ref['children'] if not nodes[c].get('optional')]
        return all(structural(c) for c in required) and all(structural(c) for c in active if c not in required)
    if not structural(model['root']): errors.append('The root business does not satisfy mandatory/AND/OR/optional integrity constraints.')
    if errors:
        return {'valid': False, 'errors': errors, 'qualities': {}, 'temporal': {}, 'goal_starts': {}}
    references = {e['source'] for e in model.get('hard_constraints', [])}
    references.update(p[k] for p in model.get('temporal_preferences', []) for k in ('x', 'y') if p.get(k))
    ambiguous = sorted(k for k in references if omitted_optional_timing(model, k, sequence))
    if ambiguous:
        return {'valid': False, 'errors': ['Requires a normalized SHOP2 trace that includes internal dummies. The goal completion time for omitted optional tasks cannot be inferred from a flat business witness:' + ', '.join(ambiguous)],
                'qualities': {}, 'temporal': {}, 'goal_starts': {}, 'status': 'requires_normalized_trace'}
    effective = selected_attainment_model(model, sequence)
    positions = {t: i for i, t in enumerate(sequence)}
    states, done = [set()], set()
    for task in sequence:
        done = done | {task}
        states.append(done)
    incoming = {}
    for e in model.get('hard_constraints', []): incoming.setdefault(e['target'], []).append(e)
    def guards(key, index):
        return all(attained(effective, e['source'], states[index]) == (e['type'] == 'pre') for e in incoming.get(key, []))
    for task in sequence:
        if not guards(task, positions[task]): errors.append(f'{task}: operator pre/npr not satisfied.')
    goal_starts = {}
    def start_goal(key, parent_start):
        if nodes[key]['kind'] == 'task': return
        active_leaves = leaves(key) & selected
        end = min((positions[t] for t in active_leaves), default=len(sequence))
        possible = (end if guards(key, end) else None) if active_leaves else next((i for i in range(parent_start, end + 1) if guards(key, i)), None)
        if possible is None:
            errors.append(f'{key}: no valid method-start (goal pre/npr) exists before the first descendant executes.')
            return
        goal_starts[key] = possible
        ref = refs[key]
        for child in ref['children']:
            if nodes[child]['kind'] != 'task' and (leaves(child) & selected or not nodes[child].get('optional')):
                # Unchosen OR branches are not methods that were initiated.
                if ref['kind'] != 'OR' or leaves(child) & selected:
                    start_goal(child, possible)
    start_goal(model['root'], 0)
    qualities = {k: quality_satisfied(model, k, selected, effective_model=effective) for k, n in nodes.items() if n['kind'] in {'softgoal', 'hard_preference'}}
    temporal = {p['id']: temporal_report(model, sequence, p) for p in model.get('temporal_preferences', [])}
    return {'valid': not errors, 'errors': errors, 'qualities': qualities, 'temporal': temporal,
            'goal_starts': goal_starts, 'semantics': 'paper-method-guards / finite monotone / literal Table4',
            'sequence': sequence}
