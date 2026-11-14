"""Provider-free structure and finite execution checks for original OR choices.

This module records supplied structure and text. It does not classify text,
apply personality patterns, infer outcomes, or infer a preference direction.
Search completion concerns the finite execution fragment, not source-world
resource availability or the satisfaction of declarative social dependencies.
"""
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
import time

from .compiler import compile_model
from .schema import ModelError, business_projection, model_hash, validate_model
from .semantics import attained, validate_plan
from .scheduling_guards import prepare_npr_forward_checks, npr_prefix_impossible


TEXT_FIELDS = ('label', 'description', 'meaning')


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode('utf-8')).hexdigest()


class _Tree:
    def __init__(self, model, text_nodes=None):
        self.model = model
        self.nodes = model['nodes']
        self.text_nodes = self.nodes if text_nodes is None else text_nodes
        self.refs = {r['parent']: r for r in model.get('refinements', [])}
        self.parents = {c: r['parent'] for r in self.refs.values()
                        for c in r['children'] if self.nodes[c]['kind'] in ('goal', 'task')}
        self.region = lru_cache(None)(self.region)
        self.leaves = lru_cache(None)(self.leaves)

    def region(self, identity):
        return frozenset({identity}).union(*(self.region(c)
            for c in self.refs.get(identity, {}).get('children', [])))

    def leaves(self, identity):
        if self.nodes[identity]['kind'] == 'task':
            return frozenset({identity})
        return frozenset().union(*(self.leaves(c)
            for c in self.refs.get(identity, {}).get('children', [])))

    def structure(self, identity):
        node = self.nodes[identity]
        original_text = self.text_nodes.get(identity, {})
        ref = self.refs.get(identity)
        result = {'node_id': identity, 'kind': node['kind'],
                  'owner': node.get('role'), 'optional': node.get('optional', False),
                  'text': {field: deepcopy(original_text[field]) for field in TEXT_FIELDS if field in original_text}}
        if ref:
            result['operator'] = ref['kind']
            result['children'] = [self.structure(c) for c in ref['children']]
        return result


def _authority_evidence(model, role, scope, tree):
    """Return original field locations, never a grant inferred from execution."""
    if not isinstance(role, str) or not isinstance(scope, str):
        return []
    ref = tree.refs.get(scope)
    if (role not in model.get('roles', {}) or not ref or ref['kind'] != 'OR'
            or model['nodes'].get(scope, {}).get('kind') != 'goal'):
        return []
    if model['nodes'][scope].get('role') == role:
        return [{'path': ['nodes', scope, 'role'], 'value': role,
                 'basis': 'original_OR_owner'}]
    declarations = []
    raw = model.get('role_discretion', {})
    if isinstance(raw, dict) and role in raw:
        declarations.append((['role_discretion', role], raw[role]))
    meta = model.get('roles', {}).get(role)
    if isinstance(meta, dict):
        for field in ('discretion', 'discretion_scopes'):
            if field in meta:
                declarations.append((['roles', role, field], meta[field]))
    evidence = []
    covered = set()
    for path, raw in declarations:
        values = [raw] if isinstance(raw, str) else raw if isinstance(raw, list) else []
        for i, grant in enumerate(values):
            if not isinstance(grant, str) or grant not in tree.nodes:
                continue
            children = [c for c in ref['children'] if c in tree.region(grant)]
            if children:
                covered.update(children)
                evidence.append({'path': path if isinstance(raw, str) else [*path, i],
                                 'value': grant, 'covered_children': children,
                                 'basis': 'explicit_original_discretion'})
    return evidence if covered == set(ref['children']) else []


def authorized(model, role, scope):
    """Whether the supplied role owns this original OR or has an explicit grant.

    An ancestor's ownership and ownership of execution leaves do not grant a
    different owner's nested decision. Explicit grants retain original paths.
    """
    checked = validate_model(model)
    return bool(_authority_evidence(checked, role, scope, _Tree(checked)))


def literal_evidence(model, node_id, field, quote):
    """A nonempty exact substring of one supplied semantic text field."""
    model = model.get('M0', model)
    return (isinstance(node_id, str) and field in TEXT_FIELDS and isinstance(quote, str) and bool(quote.strip())
            and isinstance(model.get('nodes', {}).get(node_id, {}).get(field), str)
            and quote in model['nodes'][node_id][field])


def build_index(model):
    """Index every original decision and every nested implementation structure.

    AND/OR trees are represented compositionally rather than expanding an
    exponential Cartesian product. No original alternative is truncated.
    Realization products and their execution feasibility belong to PlanSearch.
    """
    checked = validate_model(model)
    raw_nodes = model.get('M0', model)['nodes']
    tree = _Tree(checked, raw_nodes)
    decisions = {}
    for scope, ref in tree.refs.items():
        if ref['kind'] != 'OR' or tree.nodes[scope]['kind'] != 'goal':
            continue
        alternatives = []
        for child in ref['children']:
            region = tree.region(child)
            alternatives.append({'node_id': child, 'owner': tree.nodes[child].get('role'),
                'descendants': sorted(region - {child}), 'selected_endpoint_means': 'complete_original_implementation',
                'execution_roles': {t: tree.nodes[t].get('role') for t in sorted(tree.leaves(child))},
                'nested_ORs': {g: list(tree.refs[g]['children']) for g in sorted(region)
                              if g in tree.refs and tree.refs[g]['kind'] == 'OR'
                              and tree.nodes[g]['kind'] == 'goal'},
                'implementation_structure': tree.structure(child)})
        decisions[scope] = {'node_id': scope, 'owner': tree.nodes[scope].get('role'),
            'children': list(ref['children']), 'alternatives': alternatives,
            'authority': {role: _authority_evidence(checked, role, scope, tree)
                          for role in checked.get('roles', {})}}
    return {'schema': 'apate.preferred-structure.v1', 'input_hash': model_hash(checked),
            'raw_input_sha256': _digest(model), 'root': checked['root'],
            'nodes': {k: {'kind': n['kind'], 'owner': n.get('role'),
                         'optional': n.get('optional', False),
                         'descendants': sorted(tree.region(k) - {k}),
                         'text': {f: deepcopy(raw_nodes[k][f]) for f in TEXT_FIELDS if f in raw_nodes[k]},
                         'original': deepcopy(raw_nodes[k])} for k, n in checked['nodes'].items()},
            'ORs': decisions, 'roles': deepcopy(checked.get('roles', {})),
            'role_discretion': deepcopy(checked.get('role_discretion', {})),
            'dependencies': deepcopy(checked.get('dependencies', [])),
            'hard_constraints': deepcopy(checked.get('hard_constraints', [])),
            'contributions': deepcopy(checked.get('contributions', [])),
            'refinements': deepcopy(checked.get('refinements', [])),
            'source_business_projection': business_projection(checked),
            'boundaries': ['All original OR children and nested structures are retained.',
                           'Dependencies retain declarative meaning and add no temporal guards.',
                           'Structure and execution ownership establish no personality preference.']}


class _Halt(Exception):
    def __init__(self, reason, stopped=False):
        self.reason, self.stopped = reason, stopped


class PlanSearch:
    """Auditable bounded feasibility search over complete normalized realizations.

    Every realization includes fixed OR and optional choices over the complete
    root tree. Each feasible realization retains a complete witness. Matching
    witnesses have identical external business tasks and relative order. The
    search checks all realization feasibility before reporting complete_feasible.
    A budget-limited result is search_incomplete even if witnesses were found.
    """
    def __init__(self, model, max_realizations=2048, max_prefixes=50000,
                 max_seconds=30, stop=None):
        for name, value in (('max_realizations', max_realizations), ('max_prefixes', max_prefixes)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(name + ' must be a nonnegative integer.')
        if (isinstance(max_seconds, bool) or not isinstance(max_seconds, (int, float))
                or not 0 <= max_seconds < float('inf')):
            raise ValueError('max_seconds must be finite and nonnegative.')
        if stop is not None and not callable(stop) and not callable(getattr(stop, 'is_set', None)):
            raise ValueError('stop must be a callable or an event with is_set().')
        self.original = validate_model(model)
        compilation = compile_model(self.original)
        self.model = compilation['normalized_model']
        self.tree = _Tree(self.model)
        self.original_tree = _Tree(self.original, model.get('M0', model)['nodes'])
        self.dummies = set(compilation['dummy_tasks'])
        self.limits = {'max_realizations': max_realizations, 'max_prefixes': max_prefixes,
                       'max_seconds': max_seconds}
        self.stop = stop
        self.input_hash = model_hash(self.original)
        self.raw_input_sha256 = _digest(model)
        self.incoming = {}
        for edge in self.model.get('hard_constraints', []):
            self.incoming.setdefault(edge['target'], []).append(edge)

    def _guard(self):
        if self.stop is not None:
            requested = self.stop() if callable(self.stop) else self.stop.is_set()
            if requested:
                raise _Halt('stop_requested', True)
        if time.monotonic() - self.started >= self.limits['max_seconds']:
            raise _Halt('max_seconds')

    def _prefix(self):
        self._guard()
        if self.used['prefixes'] >= self.limits['max_prefixes']:
            raise _Halt('max_prefixes')
        self.used['prefixes'] += 1

    def _fixed(self, scope, child):
        choices = {scope: child}
        while scope in self.tree.parents:
            parent = self.tree.parents[scope]
            if self.tree.refs[parent]['kind'] == 'OR':
                choices[parent] = scope
            scope = parent
        return choices

    def _realizations(self, identity, fixed):
        self._guard()
        if self.model['nodes'][identity]['kind'] == 'task':
            yield (frozenset({identity}), frozenset({identity}), {})
            return
        ref = self.tree.refs[identity]
        children = [fixed[identity]] if identity in fixed else ref['children']
        if ref['kind'] == 'OR':
            for child in children:
                for tasks, nodes, choices in self._realizations(child, fixed):
                    yield tasks, nodes | {identity}, {**choices, identity: child}
            return

        def combine(i, tasks, nodes, choices):
            self._guard()
            if i == len(children):
                yield tasks, nodes | {identity}, choices
                return
            for ts, ns, cs in self._realizations(children[i], fixed):
                yield from combine(i + 1, tasks | ts, nodes | ns, {**choices, **cs})
        yield from combine(0, frozenset(), frozenset(), {})

    def _schedules(self, realization, external_order=None):
        selected = realization[0]
        order = {key: i for i, key in enumerate(self.model['nodes'])}
        npr = prepare_npr_forward_checks(self.model, selected, self.tree.leaves)
        ancestors = {}
        for task in selected:
            chain = []; node = task
            while node in self.tree.parents:
                node = self.tree.parents[node]; chain.append(node)
            ancestors[task] = chain
        external_positions = {t: i for i, t in enumerate(external_order or ())}
        failed = set()

        def visit(done, sequence):
            self._prefix()
            if done in failed:
                return
            if done == selected:
                checked = validate_plan(self.model, list(sequence))
                if checked['valid']:
                    yield list(sequence), checked
                return
            produced = False
            for task in sorted(selected - done, key=order.__getitem__):
                self._guard()
                if task in external_positions and not set(external_order[:external_positions[task]]) <= done:
                    continue
                starts = [task] + [g for g in ancestors[task] if not self.tree.leaves(g).intersection(done)]
                if any(attained(self.model, edge['source'], done) != (edge['type'] == 'pre')
                       for node in starts for edge in self.incoming.get(node, [])):
                    continue
                after = done | {task}
                if npr_prefix_impossible(self.model, after, npr):
                    continue
                for result in visit(after, (*sequence, task)):
                    produced = True
                    yield result
            if not produced:
                failed.add(done)
        yield from visit(frozenset(), ())

    def _plan(self, realization, sequence, checked):
        tasks, nodes, choices = realization
        original_nodes = self.original['nodes']
        business = [task for task in sequence if task not in self.dummies]
        return {'sequence': business, 'task_order': business,
                'normalized_sequence': list(sequence),
                'selected_tasks': sorted(tasks - self.dummies),
                'selected_nodes': sorted(nodes.intersection(original_nodes)),
                'or_choices': {g: c for g, c in choices.items() if g in original_nodes},
                'normalized_or_choices': deepcopy(choices),
                'optional_choices': {g: choices['__opt_' + g] == g for g, n in original_nodes.items()
                                     if n.get('optional') and '__opt_' + g in choices},
                'execution_roles': {t: original_nodes[t].get('role') for t in business},
                'global_quality_truth': deepcopy(checked['qualities']),
                'normalized_validation': deepcopy(checked)}

    def pair(self, scope, source, target):
        ref = self.original_tree.refs.get(scope) if isinstance(scope, str) else None
        if (not ref or ref['kind'] != 'OR' or self.original['nodes'][scope]['kind'] != 'goal'
                or not isinstance(source, str) or not isinstance(target, str)
                or source == target or source not in ref['children'] or target not in ref['children']):
            raise ModelError('A comparison requires distinct scalar direct children of one original OR goal.')
        self.started = time.monotonic()
        self.used = {'realizations': 0, 'prefixes': 0}
        records = {'source': [], 'target': []}
        internal = {'source': [], 'target': []}
        plans = []
        witness_pair = None
        enumeration = {'source': False, 'target': False}
        stage = 'realizations'
        status, reason = 'infeasible', 'exhausted_no_compatible_complete_pair'
        region = self.original_tree.leaves(scope)
        scope_nodes = self.original_tree.region(scope)

        def outside(plan):
            return tuple(t for t in plan['sequence'] if t not in region)

        def external_identity(plan):
            # Empty/all-optional external branches can have identical physical
            # task sets while representing different original business choices.
            return (tuple(sorted(set(plan['selected_nodes']) - scope_nodes)),
                    tuple(sorted((g, c) for g, c in plan['or_choices'].items() if g not in scope_nodes)))

        try:
            self._guard()
            for side, child in (('source', source), ('target', target)):
                for realization in self._realizations(self.model['root'], self._fixed(scope, child)):
                    self._guard()
                    if self.used['realizations'] >= self.limits['max_realizations']:
                        raise _Halt('max_realizations')
                    self.used['realizations'] += 1
                    tasks, nodes, choices = realization
                    record = {'realization_id': _digest([sorted(tasks), choices]),
                              'selected_tasks': sorted(tasks - self.dummies),
                              'normalized_tasks': sorted(tasks),
                              'selected_nodes': sorted(nodes.intersection(self.original['nodes'])),
                              'or_choices': {g: c for g, c in choices.items() if g in self.original['nodes']},
                              'normalized_or_choices': deepcopy(choices), 'status': 'search_incomplete'}
                    records[side].append(record)
                    found = next(self._schedules(realization), None)
                    if found is None:
                        record['status'] = 'infeasible'
                    else:
                        plan = self._plan(realization, *found)
                        record.update(status='feasible', plan=plan)
                        plans.append(plan)
                        internal[side].append((realization, plan))
                enumeration[side] = True
            stage = 'matching_external_order'
            self._guard()
            for left, a in internal['source']:
                self._guard()
                eligible = [(right, b) for right, b in internal['target']
                            if set(outside(a)) == set(outside(b))
                            and external_identity(a) == external_identity(b)]
                if not eligible:
                    continue
                for right, b in eligible:
                    if outside(a) == outside(b):
                        signature = outside(a)
                        witness_pair = {'preferred': a, 'other': b,
                                        'external_tasks': sorted(signature),
                                        'external_task_order': list(signature)}
                        break
                if witness_pair:
                    break
                signatures = set()
                for sequence, checked in self._schedules(left):
                    a = self._plan(left, sequence, checked)
                    signature = outside(a)
                    if signature in signatures:
                        continue
                    signatures.add(signature)
                    for right, b in eligible:
                        if outside(b) != signature:
                            found = next(self._schedules(right, signature), None)
                            if found is None:
                                continue
                            b = self._plan(right, *found)
                        witness_pair = {'preferred': a, 'other': b,
                                        'external_tasks': sorted(signature),
                                        'external_task_order': list(signature)}
                        break
                    if witness_pair:
                        break
                if witness_pair:
                    break
            if witness_pair:
                status, reason = 'complete_feasible', 'all_realizations_checked_and_compatible_pair_found'
        except _Halt as halt:
            status = 'stopped' if halt.stopped else 'search_incomplete'
            reason = halt.reason
        return {'schema': 'apate.complete-plan-pair.v1', 'status': status,
                'termination_reason': reason, 'termination_stage': stage,
                'input_hash': self.input_hash, 'raw_input_sha256': self.raw_input_sha256,
                'scope': scope, 'source': source, 'target': target,
                'endpoint_structures': {side: self.original_tree.structure(child)
                                        for side, child in (('source', source), ('target', target))},
                'realizations': records, 'enumeration_complete': enumeration,
                'plans': plans, 'witness_pair': witness_pair, 'pair': witness_pair,
                'budget': {**self.limits, **self.used,
                           'elapsed_seconds': time.monotonic() - self.started},
                'roles': deepcopy(self.original.get('roles', {})),
                'dependencies': deepcopy(self.original.get('dependencies', [])),
                'hard_constraints': deepcopy(self.original.get('hard_constraints', [])),
                'contributions': deepcopy(self.original.get('contributions', [])),
                'boundary': 'Finite monotone execution only; declarative dependencies add no order or resource guarantee.'}
