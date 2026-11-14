"""Import an existing Goal Model without synthesizing business requirements.

The piStar adapter follows its public serializer, not a guessed drawing format:
https://github.com/jhcp/piStar/blob/974d729ee9cbc193c93c403490ab2de471f591f0/tool/app/istarcore/fileManager.js
Its supported execution fragment is deliberately narrower than all of iStar 2.0.
Source documents, element identities and link mappings remain in provenance.
"""
from copy import deepcopy
import hashlib
import json

from .schema import BUSINESS, ID, ModelError, business_projection, validate_model

PISTAR_SOURCE = {
    'repository': 'https://github.com/jhcp/piStar',
    'revision': '974d729ee9cbc193c93c403490ab2de471f591f0',
    'serializer': 'tool/app/istarcore/fileManager.js',
    'metamodel': 'tool/language/metamodel.js',
}
NODE_TYPES = {'Goal': 'goal', 'Task': 'task', 'Quality': 'softgoal', 'Resource': 'resource'}
ACTOR_TYPES = {'Actor': 'actor', 'Agent': 'agent', 'Role': 'role'}
DERIVED = ('id', 'revision', 'model_hash', 'result', 'compilation', 'planner_result',
           'ranking_result', 'presentation', 'pattern_usage')


def _object(value, location):
    if not isinstance(value, dict):
        raise ModelError(f'{location} must be a JSON object.')
    return value


def _list(value, location):
    if not isinstance(value, list):
        raise ModelError(f'{location} must be a JSON list.')
    return value


def _string(value, location):
    if not isinstance(value, str) or not value.strip():
        raise ModelError(f'{location} must be a nonempty string.')
    return value


def _type(value, location):
    name = _string(value, location)
    pieces = name.split('.')
    if len(pieces) != 2 or pieces[0].lower() != 'istar':
        raise ModelError(f'{location}: expected an istar.* core type; received {name!r}.')
    return pieces[1]


def _parse(document):
    if isinstance(document, str):
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ModelError(f'Imported JSON repeats the key {key!r}.')
                result[key] = value
            return result
        try:
            document = json.loads(document, object_pairs_hook=unique)
        except json.JSONDecodeError as exc:
            raise ModelError(f'Invalid Goal Model JSON at line {exc.lineno}, column {exc.colno}.') from None
    return deepcopy(_object(document, 'Imported Goal Model'))


def _session_defaults(session):
    """Prepare a new input contract, retaining only explicitly supplied evidence."""
    for key in DERIVED:
        session.pop(key, None)
    session.setdefault('persona', {'actor_id': 'Actor', 'name': 'Research Actor',
                                  'role_ids': [], 'facets': [], 'evidence': []})
    session.setdefault('context', {'id': 'Context', 'episode_id': 'Episode',
                                  'facts': {}, 'current_work': {}})
    for key in ('sources', 'concerns'):
        session.setdefault(key, {})
        _object(session[key], key)
    _object(session['persona'], 'persona')
    _object(session['context'], 'context')
    session.setdefault('witnesses', [])
    _list(session['witnesses'], 'witnesses')
    session.setdefault('candidate_bundle', None)
    if session['candidate_bundle'] is not None:
        _object(session['candidate_bundle'], 'candidate_bundle')
    session['result'] = None
    return session


def _native(document, root_id):
    if 'session' in document:
        session = deepcopy(_object(document['session'], 'session'))
    elif 'model' in document:
        session = deepcopy(document)
    else:
        model = document.get('M0', document)
        session = {'model': deepcopy(_object(model, 'Goal Model'))}
    model = _object(session.get('model'), 'model')
    if root_id is not None and root_id != model.get('root'):
        raise ModelError('The supplied root_id differs from the input Goal Model root. Import an explicitly revised model to change it.')
    checked = validate_model(model)
    session['model'] = checked
    session = _session_defaults(session)
    report = {'format': 'apate-session' if 'model' in document or 'session' in document else 'apate-goal-model',
              'warnings': [], 'id_map': {key: key for key in checked['nodes']},
              'source': {'kind': 'user_goal_model'}, 'input_nodes': len(checked['nodes']),
              'imported_nodes': len(checked['nodes']), 'root_id': checked['root'],
              'business_projection_preserved': business_projection(checked) == business_projection(model),
              'normalization': 'Required schema defaults only; supplied requirements and evidence are retained.'}
    return session, report


def _pistar(document, root_id):
    if str(document.get('istar', '')).strip() != '2.0':
        raise ModelError('This adapter accepts piStar iStar 2.0 exports.')
    actors = _list(document.get('actors'), 'piStar actors')
    orphans = _list(document.get('orphans', []), 'piStar orphans')
    dependencies = _list(document.get('dependencies', []), 'piStar dependencies')
    links = _list(document.get('links', []), 'piStar links')
    if not actors and not orphans:
        raise ModelError('The piStar document contains no actors or intentional elements.')
    elements, owner = {}, {}

    def register(item, where, owner_id=None):
        _object(item, where)
        sid = _string(item.get('id'), where + '.id')
        if sid in elements:
            raise ModelError(f'piStar element ID {sid!r} is repeated.')
        _string(item.get('text'), where + '.text')
        elements[sid] = item
        owner[sid] = owner_id
        return sid

    actor_ids = []
    node_ids = []
    for index, actor in enumerate(actors):
        sid = register(actor, f'actors[{index}]')
        if _type(actor.get('type'), sid + '.type') not in ACTOR_TYPES:
            raise ModelError(f'{sid}: unsupported piStar actor type {actor.get("type")!r}.')
        actor_ids.append(sid)
        for j, node in enumerate(_list(actor.get('nodes', []), sid + '.nodes')):
            node_ids.append(register(node, f'{sid}.nodes[{j}]', sid))
    for index, node in enumerate(orphans):
        node_ids.append(register(node, f'orphans[{index}]'))
    dep_ids = [register(dep, f'dependencies[{i}]') for i, dep in enumerate(dependencies)]
    for sid in node_ids + dep_ids:
        if _type(elements[sid].get('type'), sid + '.type') not in NODE_TYPES:
            raise ModelError(f'{sid}: unsupported piStar intentional element type.')
    source_link_ids = []
    for i, link in enumerate(links):
        _object(link, f'links[{i}]')
        lid = _string(link.get('id'), f'links[{i}].id')
        if lid in elements or lid in source_link_ids:
            raise ModelError(f'piStar link ID {lid!r} is repeated or overlaps an element ID.')
        source_link_ids.append(lid)
        for field in ('source', 'target'):
            endpoint = _string(link.get(field), lid + '.' + field)
            if endpoint not in elements:
                raise ModelError(f'{lid}: {field} references unknown element {endpoint!r}.')

    # Keep legal upstream identifiers; make every other identity explicit.
    all_ids = list(elements) + source_link_ids
    reserved = {sid for sid in all_ids if ID.fullmatch(sid)}
    ids = {sid: sid for sid in reserved}
    for sid in all_ids:
        if sid in ids:
            continue
        mapped = 'I_' + hashlib.sha256(sid.encode('utf-8')).hexdigest()[:20]
        while mapped in reserved:
            mapped += '_x'
        ids[sid] = mapped
        reserved.add(mapped)

    model = {'id': 'Imported_piStar_Model', 'version': 'pistar_import_v1',
             'label': document.get('diagram', {}).get('name', 'Imported Goal Model')
                      if isinstance(document.get('diagram', {}), dict) else 'Imported Goal Model',
             'roles': {}, 'nodes': {}, 'refinements': [], 'hard_constraints': [],
             'contributions': [], 'temporal_preferences': [], 'dependencies': [], 'initial_state': []}
    for sid in actor_ids:
        actor = elements[sid]
        model['roles'][ids[sid]] = {'label': actor['text'], 'type': ACTOR_TYPES[_type(actor['type'], sid)],
                                   'source_id': sid}
    custom = False
    for sid in node_ids:
        raw = elements[sid]
        custom = custom or bool(raw.get('customProperties'))
        node = {'id': ids[sid], 'label': raw['text'], 'kind': NODE_TYPES[_type(raw['type'], sid)],
                'role': ids[owner[sid]] if owner[sid] else None, 'optional': False,
                'source_id': sid, 'source_type': raw['type']}
        if raw.get('customProperties'):
            node['source_properties'] = deepcopy(raw['customProperties'])
        model['nodes'][ids[sid]] = node

    groups = {}
    consumed = set()
    link_map = {}
    for dep in dependencies:
        sid = dep['id']
        for field in ('source', 'target'):
            endpoint = dep.get(field)
            if not isinstance(endpoint, str) or endpoint not in elements or endpoint in dep_ids:
                raise ModelError(f'{sid}: dependency {field} must identify an actor or an owned intentional element.')
        incoming = [l for l in links if _type(l.get('type'), l['id']) == 'DependencyLink'
                    and l['source'] == dep['source'] and l['target'] == sid]
        outgoing = [l for l in links if _type(l.get('type'), l['id']) == 'DependencyLink'
                    and l['source'] == sid and l['target'] == dep['target']]
        if len(incoming) != 1 or len(outgoing) != 1:
            raise ModelError(f'{sid}: expected one matching incoming and one matching outgoing piStar DependencyLink.')

        def endpoint(reference):
            if reference in actor_ids:
                return ids[reference], None
            role = owner[reference]
            if role is None:
                raise ModelError(f'{sid}: a dependency local endpoint must belong to an actor.')
            return ids[role], ids[reference]
        depender, depender_node = endpoint(dep['source'])
        dependee, dependee_node = endpoint(dep['target'])
        kind = NODE_TYPES[_type(dep['type'], sid)]
        relation = {'id': ids[incoming[0]['id']], 'depender': depender, 'dependee': dependee,
                    'dependum': {'id': ids[sid], 'kind': 'quality' if kind == 'softgoal' else kind,
                                 'label': dep['text']},
                    'source_id': sid, 'source_link_ids': [incoming[0]['id'], outgoing[0]['id']]}
        if depender_node:
            relation['depender_node'] = depender_node
        if dependee_node:
            relation['dependee_node'] = dependee_node
        model['dependencies'].append(relation)
        for link in incoming + outgoing:
            consumed.add(link['id'])
            link_map[link['id']] = {'kind': 'dependency_connector', 'dependency_id': relation['id']}

    unsupported = []
    for link in links:
        lid = link['id']
        if lid in consumed:
            continue
        kind = _type(link.get('type'), lid + '.type')
        source, target = link['source'], link['target']
        if kind in ('AndRefinementLink', 'OrRefinementLink'):
            if source not in node_ids or target not in node_ids:
                raise ModelError(f'{lid}: refinement endpoints must be existing intentional elements.')
            if owner[source] is not None and owner[target] is not None and owner[source] != owner[target]:
                raise ModelError(f'{lid}: piStar intentional refinement crosses actor owners.')
            mode = 'AND' if kind == 'AndRefinementLink' else 'OR'
            parent = ids[target]
            if parent in groups and groups[parent]['kind'] != mode:
                raise ModelError(f'{target}: mixed AND and OR links require an explicit supported input refinement.')
            group = groups.setdefault(parent, {'parent': parent, 'kind': mode, 'children': [], 'source_link_ids': []})
            group['children'].append(ids[source])
            group['source_link_ids'].append(lid)
            link_map[lid] = {'kind': 'refinement', 'parent': parent, 'child': ids[source], 'operator': mode}
        elif kind == 'ContributionLink':
            if source not in node_ids or target not in node_ids:
                raise ModelError(f'{lid}: contribution endpoints must be owned intentional elements.')
            label = link.get('label')
            if label not in ('make', 'break'):
                unsupported.append(f'{lid}: contribution {label!r}; only explicit make/break has an exact executable mapping.')
                continue
            model['contributions'].append({'source': ids[source], 'target': ids[target],
                                           'type': 'makes' if label == 'make' else 'breaks',
                                           'source_link_id': lid})
            link_map[lid] = {'kind': 'contribution', 'source': ids[source], 'target': ids[target]}
        else:
            unsupported.append(f'{lid}: {link["type"]}')
    if unsupported:
        raise ModelError('The piStar model contains relations outside the supported executable fragment. No relations were discarded.', unsupported)
    model['refinements'] = list(groups.values())
    executable = {key for key, node in model['nodes'].items() if node['kind'] in BUSINESS}
    children = {child for ref in model['refinements'] for child in ref['children'] if child in executable}
    roots = sorted(executable - children)
    if len(roots) != 1:
        reverse = {target: source for source, target in ids.items()}
        raise ModelError('The imported diagram requires an explicit supported execution projection with one connected business root. No root or business relation was invented.',
                         ['Existing root candidates: ' + ', '.join(reverse.get(k, k) for k in roots)])
    requested = None
    if root_id is not None:
        _string(root_id, 'root_id')
        requested = ids.get(root_id, root_id)
        if requested != roots[0]:
            raise ModelError('root_id must identify the existing business root and cannot discard other input branches.')
    model['root'] = requested or roots[0]
    checked = validate_model(model)
    warnings = ['The executable profile selects one OR implementation and requires leaf tasks.']
    if custom or document.get('display') or document.get('diagram'):
        warnings.append('Source custom properties and drawing coordinates are archived as metadata; they do not create execution constraints or personal preferences.')
    if orphans:
        warnings.append('Unowned source elements retain their unowned status in the imported model.')
    report = {'format': 'pistar-2.0', 'warnings': warnings, 'id_map': ids, 'link_map': link_map,
              'source': {**PISTAR_SOURCE, 'tool': document.get('tool'), 'language': document.get('istar')},
              'input_nodes': len(node_ids), 'imported_nodes': len(checked['nodes']),
              'input_actors': len(actor_ids), 'imported_actors': len(checked['roles']),
              'input_dependencies': len(dep_ids), 'imported_dependencies': len(checked['dependencies']),
              'root_id': checked['root'], 'invented_business_nodes': 0,
              'discarded_semantic_links': 0, 'mapped_source_links': len(link_map)}
    assert len(link_map) == len(links)
    return _session_defaults({'model': checked, 'name': checked['label']}), report


def import_goal_model(document, root_id=None):
    """Return {session, report} for a validated, explicitly supplied Goal Model.

    This function has no persistence or model-provider side effects. Imported
    accepted results are cleared; only actual supplied evidence is retained.
    """
    original = _parse(document)
    if 'actors' in original and 'links' in original:
        session, report = _pistar(original, root_id)
    else:
        session, report = _native(original, root_id)
    session['import_provenance'] = {'format': report['format'], 'source_document': original,
                                    'id_map': deepcopy(report['id_map']), 'source': deepcopy(report['source'])}
    return {'session': session, 'report': report}
