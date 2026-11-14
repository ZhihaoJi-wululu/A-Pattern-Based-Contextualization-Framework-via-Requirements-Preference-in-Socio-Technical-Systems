"""Validate the explicit, finite goal-model fragment accepted by the prototype."""
from copy import deepcopy
import hashlib
import json
import re

ID = re.compile(r'^[A-Za-z][A-Za-z0-9_:-]{0,95}$')
KINDS = {'goal', 'task', 'softgoal', 'hard_preference', 'resource'}
ACTOR_TYPES = {'actor', 'agent', 'role'}
DEPENDUM_KINDS = {'goal', 'task', 'resource', 'quality'}
BUSINESS = {'goal', 'task'}
QUALITY = {'softgoal', 'hard_preference'}
TEMPORAL = {'sometime', 'never', 'precedes', 'require_before', 'require_after', 'never_before', 'never_after'}
FACETS = ['Sociability', 'Assertiveness', 'Energy Level', 'Compassion', 'Respectfulness', 'Trust',
          'Organization', 'Productiveness', 'Responsibility', 'Anxiety', 'Depression',
          'Emotional Volatility', 'Intellectual Curiosity', 'Aesthetic Sensitivity', 'Creative Imagination']
PROJECTION_KEYS = ('id', 'version', 'nodes', 'refinements', 'hard_constraints', 'contributions',
                   'roles', 'role_discretion', 'root', 'temporal_preferences', 'initial_state', 'concerns',
                   'dependencies')

class ModelError(ValueError):
    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details or []

def business_projection(model):
    """Actor, current facts and personal relations are outside this fixed projection."""
    return deepcopy({k: model[k] for k in PROJECTION_KEYS if k in model})

def model_hash(model):
    raw = json.dumps(business_projection(model), sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()

def _node_kind(nodes, key):
    """Return a kind only for a scalar, known node ID."""
    return nodes.get(key, {}).get('kind') if isinstance(key, str) else None


def _validate_actors_and_dependencies(model, nodes, roles, errors):
    """Check the declarative social layer without compiling it into tasks."""
    for actor_id, actor in roles.items():
        if not isinstance(actor_id, str) or not ID.fullmatch(actor_id):
            errors.append(f'Invalid actor or role ID: {actor_id!r}.')
        if isinstance(actor, str):
            if not actor.strip():
                errors.append(f'{actor_id}: Actor label must not be empty.')
        elif isinstance(actor, dict):
            label = actor.get('label', actor_id)
            if not isinstance(label, str) or not label.strip():
                errors.append(f'{actor_id}: Actor label must be a nonempty string.')
            kind = actor.get('type', 'role')
            if not isinstance(kind, str) or kind not in ACTOR_TYPES:
                errors.append(f'{actor_id}: Actor type must be actor, agent or role.')
            if actor.get('id', actor_id) != actor_id:
                errors.append(f'{actor_id}: Actor id must match its object key.')
        else:
            errors.append(f'{actor_id}: Actor must be a label string or an object.')
    dependencies = model.get('dependencies', [])
    if not isinstance(dependencies, list):
        errors.append('dependencies must be a list.')
        return
    if len(dependencies) > 500:
        errors.append('The prototype accepts at most 500 dependencies.')
    ids = set()
    dependency_ids = {item['id'] for item in dependencies if isinstance(item, dict)
                      and isinstance(item.get('id'), str)}
    dependum_ids = set()
    raw_refs = model.get('refinements', [])
    refined = {ref['parent'] for ref in raw_refs if isinstance(ref, dict)
               and isinstance(ref.get('parent'), str)} if isinstance(raw_refs, list) else set()
    raw_effects = model.get('contributions', [])
    contribution_targets = {edge['target'] for edge in raw_effects if isinstance(edge, dict)
                            and isinstance(edge.get('target'), str)} if isinstance(raw_effects, list) else set()
    for index, dependency in enumerate(dependencies):
        if not isinstance(dependency, dict):
            errors.append(f'Dependency {index + 1} must be an object.')
            continue
        did = dependency.get('id')
        where = did if isinstance(did, str) else f'Dependency {index + 1}'
        if not isinstance(did, str) or not ID.fullmatch(did):
            errors.append(f'{where}: Dependency requires a valid ID.')
        elif did in ids or did in nodes or did in roles:
            errors.append(f'{did}: Dependency ID must be unique across model elements.')
        else:
            ids.add(did)
        depender, dependee = dependency.get('depender'), dependency.get('dependee')
        for field, endpoint in [('depender', depender), ('dependee', dependee)]:
            if not isinstance(endpoint, str) or endpoint not in roles:
                errors.append(f'{where}: {field} must reference an existing actor or role.')
        if isinstance(depender, str) and depender == dependee:
            errors.append(f'{where}: Depender and dependee must be distinct actors.')
        dependum = dependency.get('dependum')
        if not isinstance(dependum, dict):
            errors.append(f'{where}: dependum must be an object with kind and label.')
        else:
            kind = dependum.get('kind')
            if not isinstance(kind, str) or kind not in DEPENDUM_KINDS:
                errors.append(f'{where}: Dependum kind must be goal, task, resource or quality.')
            if not isinstance(dependum.get('label'), str) or not dependum['label'].strip():
                errors.append(f'{where}: Dependum label must be a nonempty string.')
            if 'id' in dependum:
                dependum_id = dependum['id']
                if not isinstance(dependum_id, str) or not ID.fullmatch(dependum_id):
                    errors.append(f'{where}: Dependum id must be a valid identifier when supplied.')
                elif dependum_id in dependum_ids or dependum_id in nodes or dependum_id in roles or dependum_id in dependency_ids:
                    errors.append(f'{where}: Each dependency must own a distinct external dependum ID.')
                else:
                    dependum_ids.add(dependum_id)
        for field, owner in [('depender_node', depender), ('dependee_node', dependee)]:
            endpoint = dependency.get(field)
            if endpoint is None:
                continue
            if not isinstance(endpoint, str) or endpoint not in nodes:
                errors.append(f'{where}: {field} must reference an existing node.')
            elif nodes[endpoint].get('role') != owner:
                errors.append(f'{where}: {field} must belong to its endpoint actor.')
            elif field == 'depender_node' and (endpoint in refined or endpoint in contribution_targets):
                errors.append(f'{where}: The local depender element cannot be refined or receive contributions.')


def validate_model(model):
    if not isinstance(model, dict):
        raise ModelError('Model must be a JSON object.')
    if 'M0' in model:
        model = model['M0']
        if not isinstance(model, dict):
            raise ModelError('M0 must be a JSON object.')
    result = deepcopy(model)
    errors = []
    nodes = result.get('nodes')
    if not isinstance(nodes, dict) or not nodes:
        raise ModelError('nodes must be a nonempty object.')
    if len(nodes) > 500:
        raise ModelError('The prototype accepts at most 500 nodes.')
    roles = result.get('roles', {})
    if not isinstance(roles, dict):
        raise ModelError('roles must be an object.')
    for key, node in nodes.items():
        if not isinstance(key, str) or not ID.fullmatch(key):
            errors.append(f'Invalid node ID or reserved internal prefix: {key!r}')
        if not isinstance(node, dict):
            errors.append(f'{key}: Node must be an object.')
            continue
        if not isinstance(node.get('kind'), str) or node['kind'] not in KINDS:
            errors.append(f'{key}: Unsupported node kind.')
        if node.get('id', key) != key:
            errors.append(f'{key}: Node id must match its object key.')
        if not isinstance(node.get('label', key), str) or not node.get('label', key).strip():
            errors.append(f'{key}: label must be a nonempty string.')
        if node.get('role') is not None and (not isinstance(node['role'], str) or node['role'] not in roles):
            errors.append(f'{key}: role must reference an existing actor or role.')
        if not isinstance(node.get('optional', False), bool):
            errors.append(f'{key}: optional must be boolean.')
        if node.get('kind') == 'resource' and node.get('optional', False):
            errors.append(f'{key}: A descriptive resource cannot be an optional executable item.')
        node.setdefault('id', key)
        node.setdefault('label', key)
        node.setdefault('optional', False)
    if errors:
        raise ModelError('Node validation failed.', errors)
    _validate_actors_and_dependencies(result, nodes, roles, errors)
    root = result.get('root')
    if _node_kind(nodes, root) not in BUSINESS:
        errors.append('root must reference an executable goal or task.')
    refs = result.setdefault('refinements', [])
    if not isinstance(refs, list):
        raise ModelError('refinements must be a list.')
    by_parent = {}
    business_parents = {}
    for ref in refs:
        if not isinstance(ref, dict):
            errors.append('Refinement must be an object.')
            continue
        parent, children = ref.get('parent'), ref.get('children')
        if not isinstance(parent, str) or parent not in nodes or not isinstance(children, list) or not children:
            errors.append(f'{parent}: Refinement requires an existing parent and nonempty children.')
            continue
        if parent in by_parent:
            errors.append(f'{parent}: A parent may have only one refinement.')
        by_parent[parent] = ref
        if nodes[parent]['kind'] == 'task':
            errors.append(f'{parent}: Executable leaf tasks cannot be refined in this profile.')
        if nodes[parent]['kind'] == 'resource':
            errors.append(f'{parent}: Resources cannot be refinement parents in this execution profile.')
        if not isinstance(ref.get('kind'), str) or ref['kind'] not in {'AND', 'OR'}:
            errors.append(f'{parent}: Refinement kind must be AND or OR.')
        if any(not isinstance(c, str) for c in children):
            errors.append(f'{parent}: children must contain node ID strings.')
            continue
        if len(set(children)) != len(children):
            errors.append(f'{parent}: children must not repeat a node.')
        for child in children:
            if child not in nodes:
                errors.append(f'{parent}: Unknown child {child}.')
                continue
            if (nodes[parent]['kind'] in BUSINESS) != (nodes[child]['kind'] in BUSINESS):
                errors.append(f'{parent}: Executable and quality refinements cannot be mixed.')
            if nodes[child]['kind'] == 'resource':
                errors.append(f'{child}: Resources are descriptive and cannot be refinement children.')
            if nodes[child].get('optional') and ref.get('kind') != 'AND':
                errors.append(f'{child}: optional is supported only on AND children.')
            if nodes[child]['kind'] in BUSINESS:
                if child in business_parents:
                    errors.append(f'{child}: The finite execution profile does not support shared business subtrees.')
                business_parents[child] = parent
    if errors:
        raise ModelError('Model structure validation failed.', errors)
    seen, visiting = set(), set()
    def visit(key):
        if key in visiting:
            errors.append(f'{key}: Refinement graph contains a cycle.')
            return
        if key in seen:
            return
        visiting.add(key)
        for child in by_parent.get(key, {}).get('children', []):
            if child in nodes:
                visit(child)
        visiting.remove(key)
        seen.add(key)
    for key in nodes:
        visit(key)
    if root in nodes:
        reachable = set()
        def walk(key):
            if key in reachable:
                return
            reachable.add(key)
            for child in by_parent.get(key, {}).get('children', []):
                if child in nodes:
                    walk(child)
        walk(root)
        for key, node in nodes.items():
            if node.get('kind') == 'goal' and key not in by_parent:
                errors.append(f'{key}: Executable goal requires a refinement.')
            if node.get('kind') in BUSINESS and key not in reachable:
                errors.append(f'{key}: Executable node is outside the root tree.')
    for list_key in ('hard_constraints', 'contributions', 'temporal_preferences'):
        if not isinstance(result.setdefault(list_key, []), list):
            raise ModelError(list_key + ' must be a list.')
    for edge in result['hard_constraints']:
        if not isinstance(edge, dict):
            errors.append('Hard constraint must be an object.')
            continue
        if not isinstance(edge.get('type'), str) or edge['type'] not in {'pre', 'npr'}:
            errors.append('Hard constraint type must be pre or npr.')
        if any(_node_kind(nodes, edge.get(k)) not in BUSINESS for k in ('source', 'target')):
            errors.append('Hard constraint endpoints must be existing executable elements.')
    for edge in result.setdefault('contributions', []):
        if not isinstance(edge, dict):
            errors.append('Contribution must be an object.')
            continue
        if not isinstance(edge.get('type'), str) or edge['type'] not in {'makes', 'breaks'}:
            errors.append('Contribution type must be makes or breaks.')
        if _node_kind(nodes, edge.get('source')) not in BUSINESS or _node_kind(nodes, edge.get('target')) not in QUALITY:
            errors.append('Contribution must connect an executable element to a quality or preference.')
    pref_ids = set()
    quality_ids={k for k,n in nodes.items() if n['kind'] in QUALITY}
    for pref in result.setdefault('temporal_preferences', []):
        if not isinstance(pref, dict):
            errors.append('Temporal preference must be an object.')
            continue
        pid=pref.get('id')
        if not isinstance(pid,str) or not pid.strip() or len(pid)>160:
            errors.append('Temporal preference ID must be a nonempty string of at most 160 characters.')
            continue
        if pid in pref_ids or pid in quality_ids:
            errors.append('Temporal preference ID must be unique.')
        pref_ids.add(pid)
        if not isinstance(pref.get('formula'), str) or pref['formula'] not in TEMPORAL:
            errors.append('Unsupported soft temporal template.')
        endpoints = [pref.get('x')] + ([] if pref.get('formula') in ('sometime', 'never') else [pref.get('y')])
        if any(_node_kind(nodes, k) not in BUSINESS for k in endpoints):
            errors.append('Temporal endpoints must be existing executable elements.')
    if result.get('initial_state', []) != []:
        errors.append('This finite execution profile requires an empty initial state.')
    if errors:
        raise ModelError('Model validation failed.', errors)
    return result
