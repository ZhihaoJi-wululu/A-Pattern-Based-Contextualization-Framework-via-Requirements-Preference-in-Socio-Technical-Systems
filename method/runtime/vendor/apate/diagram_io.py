"""Lossless display input for existing i* diagrams, with optional exact reasoning.

piStar JSON follows jhcp/piStar's public serializer. XML accepts the published
iStarML 1.0 interchange dialect, rather than treating arbitrary XML as iStar.
Display admission is intentionally independent of PATPREF's executable fragment.
"""
from copy import deepcopy
import json
import math
import re
import xml.etree.ElementTree as ET

from .model_import import import_goal_model
from .schema import ModelError


XML_SOURCE = {
    'format': 'iStarML 1.0',
    'specification': 'https://www.upc.edu/gessi/tools/istar/tools/istarml/index.html',
    'examples': 'https://github.com/UPC-gessi-oscar-franco/iStarJson/blob/master/Test2.istarml',
}
NODE_KINDS = {'goal': 'goal', 'task': 'task', 'quality': 'quality',
              'softgoal': 'quality', 'resource': 'resource', 'hard_preference': 'hard_preference'}
PISTAR_NODES = {'Goal': 'goal', 'Task': 'task', 'Quality': 'quality', 'Resource': 'resource'}
PISTAR_ACTORS = {'Actor': 'actor', 'Role': 'role', 'Agent': 'agent'}
PISTAR_LINKS = {'AndRefinementLink': 'and', 'OrRefinementLink': 'or',
                'DependencyLink': 'dependency', 'NeededByLink': 'neededBy',
                'QualificationLink': 'qualification', 'IsALink': 'isA',
                'ParticipatesInLink': 'participatesIn'}
CONTRIBUTIONS = {'make': 'make', 'makes': 'make', '++': 'make',
                 'break': 'break', 'breaks': 'break', '--': 'break',
                 'help': 'help', '+': 'help', 'hurt': 'hurt', '-': 'hurt'}
MAX_ELEMENTS = 5000
MAX_LINKS = 20000


def _object(value, where):
    if not isinstance(value, dict):
        raise ModelError(f'{where} must be an object.')
    return value


def _array(value, where):
    if not isinstance(value, list):
        raise ModelError(f'{where} must be a list.')
    return value


def _text(value, where, limit=10000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ModelError(f'{where} must be a nonempty string of at most {limit} characters.')
    return value


def _id(value, where):
    return _text(value, where, 256)


def _boolean(value, where):
    if not isinstance(value, bool):
        raise ModelError(f'{where} must be true or false.')
    return value


def _bounds(item, raw, where, xml=False):
    fields = {'xpos': 'x', 'ypos': 'y', 'width': 'width', 'height': 'height'} if xml else {
        'x': 'x', 'y': 'y', 'width': 'width', 'height': 'height'}
    for source, target in fields.items():
        if source not in raw:
            continue
        value = raw[source]
        if isinstance(value, bool):
            raise ModelError(f'{where}.{source} must be a finite number.')
        if xml:
            try:
                value = float(value)
            except (ValueError, TypeError):
                raise ModelError(f'{where}.{source} must be a finite number.') from None
        if not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > 1000000:
            raise ModelError(f'{where}.{source} must be a finite number within drawing bounds.')
        if target in ('width', 'height') and value <= 0:
            raise ModelError(f'{where}.{source} must be positive.')
        item[target] = value


def _parse(document):
    if isinstance(document, str):
        if len(document.encode('utf-8')) > 10 * 1024 * 1024:
            raise ModelError('The model file exceeds the 10 MiB import limit.')
        text = document.lstrip('\ufeff \t\r\n')
        if text.startswith('<'):
            return document, True
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ModelError(f'Imported JSON repeats the key {key!r}.')
                result[key] = value
            return result
        try:
            def constant(value):
                raise ModelError(f'JSON numeric constant {value!r} is not finite.')
            document = json.loads(text, object_pairs_hook=unique, parse_constant=constant)
        except json.JSONDecodeError as exc:
            raise ModelError(f'Invalid model JSON at line {exc.lineno}, column {exc.colno}.') from None
    _object(document, 'Model document')
    try:
        json.dumps(document, allow_nan=False)
    except (ValueError, TypeError):
        raise ModelError('The model must contain finite, JSON-compatible data.') from None
    return deepcopy(document), False


def _kind(raw, where):
    value = _text(raw, where)
    return value.split('.', 1)[1] if value.startswith('istar.') else value


def _new_graph():
    return {'actors': [], 'nodes': [], 'links': [], 'task_refs': {}, 'temporal_preferences': []}


def _add_link(graph, source, target, kind, used, prefix, **metadata):
    candidate = prefix
    index = 1
    while candidate in used:
        index += 1
        candidate = f'{prefix}_{index}'
    used.add(candidate)
    graph['links'].append({'id': candidate, 'source': source, 'target': target,
                           'kind': kind, **metadata})
    return candidate


def _validate_graph(graph):
    all_items = graph['actors'] + graph['nodes']
    if len(all_items) > MAX_ELEMENTS or len(graph['links']) > MAX_LINKS:
        raise ModelError('The imported diagram exceeds the prototype element/link limit.')
    ids = set()
    for item in all_items + graph['links']:
        key = _id(item.get('id'), 'Element ID')
        if key in ids:
            raise ModelError(f'Diagram ID {key!r} is repeated across elements or links.')
        ids.add(key)
    actors = {a['id'] for a in graph['actors']}
    nodes = {n['id'] for n in graph['nodes']}
    for node in graph['nodes']:
        if node.get('owner') is not None:
            owner = _id(node['owner'], node['id'] + '.owner')
            if owner not in actors:
                raise ModelError(f'{node["id"]}: unknown actor owner {owner!r}.')
        if node.get('dependum') and node.get('owner') is not None:
            raise ModelError(f'{node["id"]}: a dependum must be outside actor boundaries.')
    for link in graph['links']:
        for field in ('source', 'target'):
            reference = _id(link.get(field), link['id'] + '.' + field)
            if reference not in actors | nodes:
                raise ModelError(f'{link["id"]}: unknown {field} endpoint {link.get(field)!r}.')
        if link['source'] == link['target']:
            raise ModelError(f'{link["id"]}: self links are not supported by this diagram input contract.')
    tasks = [n['id'] for n in graph['nodes'] if n['kind'] == 'task' and not n.get('dependum')]
    matches = [re.fullmatch(r't([1-9][0-9]*)', key) for key in tasks]
    natural = all(matches) and {int(m.group(1)) for m in matches} == set(range(1, len(tasks) + 1))
    graph['task_refs'] = {key: key if natural else f't{i}' for i, key in enumerate(tasks, 1)}


def _native(document):
    wrapper = document.get('session', document)
    _object(wrapper, 'Session wrapper')
    model = wrapper.get('model', wrapper.get('M0', wrapper))
    _object(model, 'Goal Model')
    nodes = _object(model.get('nodes'), 'Goal Model nodes')
    roles = _object(model.get('roles', {}), 'Goal Model roles')
    graph = _new_graph()
    for aid, raw in roles.items():
        _id(aid, 'Actor ID')
        if isinstance(raw, str):
            actor = {'id': aid, 'label': _text(raw, aid + '.label'), 'kind': 'role'}
        else:
            _object(raw, aid)
            kind = raw.get('type', 'role')
            if kind not in ('actor', 'role', 'agent'):
                raise ModelError(f'{aid}: unsupported actor type {kind!r}.')
            actor = {'id': aid, 'label': _text(raw.get('label', aid), aid + '.label'), 'kind': kind}
            _bounds(actor, raw, aid)
        graph['actors'].append(actor)
    for nid, raw in nodes.items():
        _id(nid, 'Node ID'); _object(raw, nid)
        if raw.get('id', nid) != nid:
            raise ModelError(f'{nid}: node id differs from its dictionary key.')
        kind = NODE_KINDS.get(raw.get('kind'))
        if kind is None:
            raise ModelError(f'{nid}: unsupported intentional element kind {raw.get("kind")!r}.')
        item = {'id': nid, 'label': _text(raw.get('label', nid), nid + '.label'),
                'kind': kind, 'owner': raw.get('role'),
                'optional': _boolean(raw.get('optional', False), nid + '.optional')}
        _bounds(item, raw, nid)
        graph['nodes'].append(item)
    native_dependencies = _array(model.get('dependencies', []), 'dependencies')
    used = set(nodes) | set(roles)
    dependum_ids = []
    dependency_ids = set()
    for i, dep in enumerate(native_dependencies):
        _object(dep, f'dependencies[{i}]')
        dependency_id = _id(dep.get('id'), f'dependencies[{i}].id')
        if dependency_id in used or dependency_id in dependency_ids:
            raise ModelError(f'Dependency ID {dependency_id!r} is repeated across source elements.')
        dependency_ids.add(dependency_id)
    used.update(dependency_ids)
    for i, dep in enumerate(native_dependencies):
        dependum = _object(dep.get('dependum'), f'dependencies[{i}].dependum')
        did = dependum.get('id')
        if did is None:
            did = dep['id'] + '_dependum'
            while did in used:
                did += '_external'
        else:
            _id(did, 'Dependum ID')
            if did in used:
                raise ModelError(f'Dependum ID {did!r} is repeated across source elements.')
        used.add(did)
        dependum_ids.append(did)
    for i, raw in enumerate(_array(model.get('refinements', []), 'refinements')):
        _object(raw, f'refinements[{i}]')
        children = _array(raw.get('children'), f'refinements[{i}].children')
        parent = _id(raw.get('parent'), f'refinements[{i}].parent')
        for j, child in enumerate(children):
            _id(child, f'refinements[{i}].children[{j}]')
        group_cross_owner = parent in nodes and any(child in nodes and nodes[child].get('role') != nodes[parent].get('role') for child in children)
        for j, child in enumerate(children):
            kind = str(raw.get('kind', '')).lower()
            if kind not in ('and', 'or'):
                raise ModelError(f'refinements[{i}]: unsupported refinement operator.')
            _add_link(graph, child, parent, kind, used, f'refinement_{i + 1}_{j + 1}', coordination=group_cross_owner,
                      source_refinement=deepcopy(raw))
    for collection, convert in (('hard_constraints', {'pre': 'pre', 'npr': 'npr'}),
                                ('contributions', CONTRIBUTIONS)):
        for i, raw in enumerate(_array(model.get(collection, []), collection)):
            _object(raw, f'{collection}[{i}]')
            meaning = _text(raw.get('type'), f'{collection}[{i}].type')
            kind = convert.get(meaning, f'source:{collection}:{meaning}')
            _add_link(graph, raw.get('source'), raw.get('target'), kind, used,
                      f'{collection}_{i + 1}', source_type=meaning, source_record=deepcopy(raw))
    for i, raw in enumerate(native_dependencies):
        _object(raw, f'dependencies[{i}]')
        dependum = _object(raw.get('dependum'), f'dependencies[{i}].dependum')
        did = dependum_ids[i]
        kind = NODE_KINDS.get(dependum.get('kind'))
        if kind is None:
            raise ModelError(f'{did}: unsupported dependum type.')
        graph['nodes'].append({'id': did, 'kind': kind, 'owner': None, 'dependum': True,
                               'label': _text(dependum.get('label', did), did + '.label'),
                               'source_dependency_id': raw['id']})
        used.add(did)
        for owner_field, node_field in (('depender', 'depender_node'), ('dependee', 'dependee_node')):
            owner = _id(raw.get(owner_field), f'{did}.{owner_field}')
            if owner not in roles:
                raise ModelError(f'{did}: unknown {owner_field} actor.')
            local = raw.get(node_field)
            if local is not None:
                _id(local, f'{did}.{node_field}')
            if local is not None and (local not in nodes or nodes[local].get('role') != raw[owner_field]):
                raise ModelError(f'{did}: local {owner_field} endpoint has a different owner.')
        source = raw.get('depender_node') or raw['depender']
        target = raw.get('dependee_node') or raw['dependee']
        _add_link(graph, source, did, 'dependency', used, f'dependency_{i + 1}_in',
                  dependency_id=raw.get('id'), source_record=deepcopy(raw))
        _add_link(graph, did, target, 'dependency', used, f'dependency_{i + 1}_out',
                  dependency_id=raw.get('id'), source_record=deepcopy(raw))
    for i, raw in enumerate(_array(model.get('temporal_preferences', []), 'temporal_preferences')):
        _object(raw, f'temporal_preferences[{i}]')
        _text(raw.get('formula'), f'temporal_preferences[{i}].formula')
        for field in ('x', 'y'):
            if field == 'y' and field not in raw:
                continue
            endpoint = raw.get(field)
            if isinstance(endpoint, str):
                keys = [endpoint]
            elif isinstance(endpoint, list):
                keys = endpoint
            elif isinstance(endpoint, dict):
                keys = endpoint.get('tasks', [endpoint.get('goal')])
            else:
                keys = []
            if not isinstance(keys, list) or not keys:
                raise ModelError(f'temporal_preferences[{i}].{field} requires existing business references.')
            for key in keys:
                _id(key, f'temporal_preferences[{i}].{field}')
                if key not in nodes or nodes[key].get('kind') not in ('goal', 'task'):
                    raise ModelError(f'temporal_preferences[{i}].{field} references an unknown business element.')
        graph['temporal_preferences'].append(deepcopy(raw))
    name = wrapper.get('name', model.get('label', model.get('id', 'Imported i* model')))
    return graph, _text(name, 'Model name'), [], document


def _pistar(document):
    if str(document.get('istar', '')).strip() != '2.0':
        raise ModelError('piStar JSON must declare istar: "2.0".')
    graph = _new_graph()
    for i, raw in enumerate(_array(document.get('actors'), 'piStar actors')):
        _object(raw, f'actors[{i}]')
        aid = _id(raw.get('id'), 'Actor ID')
        kind = PISTAR_ACTORS.get(_kind(raw.get('type'), aid + '.type'))
        if kind is None:
            raise ModelError(f'{aid}: unsupported piStar actor type.')
        item = {'id': aid, 'label': _text(raw.get('text'), aid + '.text'), 'kind': kind}
        _bounds(item, raw, aid); graph['actors'].append(item)
        for j, node in enumerate(_array(raw.get('nodes', []), aid + '.nodes')):
            _pistar_node(graph, node, aid, f'{aid}.nodes[{j}]')
    for i, raw in enumerate(_array(document.get('orphans', []), 'piStar orphans')):
        _pistar_node(graph, raw, None, f'orphans[{i}]')
    dependencies = _array(document.get('dependencies', []), 'piStar dependencies')
    for i, raw in enumerate(dependencies):
        _pistar_node(graph, raw, None, f'dependencies[{i}]', dependum=True)
    for i, raw in enumerate(_array(document.get('links'), 'piStar links')):
        _object(raw, f'links[{i}]')
        lid = _id(raw.get('id'), 'Link ID')
        source_type = _kind(raw.get('type'), lid + '.type')
        kind = PISTAR_LINKS.get(source_type)
        if source_type == 'ContributionLink':
            label = _text(raw.get('label'), lid + '.label')
            kind = CONTRIBUTIONS.get(label, f'source:contribution:{label}')
        if kind is None:
            kind = f'source:{raw["type"]}'
        link = {'id': lid, 'source': _id(raw.get('source'), lid + '.source'),
                'target': _id(raw.get('target'), lid + '.target'), 'kind': kind,
                'source_type': raw['type'], 'source_record': deepcopy(raw)}
        if raw.get('label') is not None:
            if not isinstance(raw['label'], str):
                raise ModelError(f'{lid}.label must be a string.')
            link['label'] = raw['label']
        graph['links'].append(link)
    display = _object(document.get('display', {}), 'piStar display')
    for item in graph['actors'] + graph['nodes'] + graph['links']:
        details = display.get(item['id'], {})
        _object(details, item['id'] + '.display')
        _bounds(item, details, item['id'] + '.display')
        if 'vertices' in details:
            points = _array(details['vertices'], item['id'] + '.vertices')
            if len(points) > 1000:
                raise ModelError(f'{item["id"]}: too many routing vertices.')
            item['vertices'] = []
            for point in points:
                _object(point, item['id'] + '.vertex')
                if 'x' not in point or 'y' not in point:
                    raise ModelError(f'{item["id"]}: routing vertices require x and y.')
                checked = {}; _bounds(checked, point, item['id'] + '.vertex')
                item['vertices'].append(checked)
        if 'collapsed' in details:
            item['collapsed'] = _boolean(details['collapsed'], item['id'] + '.collapsed')
    actors = {a['id'] for a in graph['actors']}
    nodes = {n['id']: n for n in graph['nodes']}
    for raw in dependencies:
        did = raw['id']
        for field in ('source', 'target'):
            reference = raw.get(field)
            _id(reference, f'{did}.{field}')
            if reference not in actors and (reference not in nodes or nodes[reference].get('dependum') or nodes[reference]['owner'] is None):
                raise ModelError(f'{did}: dependency {field} must identify an actor or its owned intentional element.')
        incoming = [l for l in graph['links'] if l['kind'] == 'dependency' and l['source'] == raw['source'] and l['target'] == did]
        outgoing = [l for l in graph['links'] if l['kind'] == 'dependency' and l['source'] == did and l['target'] == raw['target']]
        if len(incoming) != 1 or len(outgoing) != 1:
            raise ModelError(f'{did}: expected both explicit piStar dependency connectors.')
    diagram = document.get('diagram', {})
    name = diagram.get('name', 'Imported piStar model') if isinstance(diagram, dict) else 'Imported piStar model'
    warnings = [f'{l["id"]}: source relation {l["source_type"]} is preserved for visualization.'
                for l in graph['links'] if l['kind'].startswith('source:')]
    return graph, _text(name, 'Model name'), warnings, document


def _pistar_node(graph, raw, owner, where, dependum=False):
    _object(raw, where)
    nid = _id(raw.get('id'), where + '.id')
    kind = PISTAR_NODES.get(_kind(raw.get('type'), nid + '.type'))
    if kind is None:
        raise ModelError(f'{nid}: unsupported piStar intentional element type.')
    item = {'id': nid, 'label': _text(raw.get('text'), nid + '.text'), 'kind': kind, 'owner': owner,
            'source_type': raw['type'], 'source_properties': deepcopy(raw.get('customProperties', {}))}
    if dependum:
        item['dependum'] = True
    _bounds(item, raw, nid)
    graph['nodes'].append(item)


def _local(tag):
    return tag.rsplit('}', 1)[-1]


def _xml(document):
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)\b', document, re.IGNORECASE):
        raise ModelError('iStarML import does not accept DTD or entity declarations.')
    try:
        root = ET.fromstring(document.lstrip('\ufeff'))
    except ET.ParseError as exc:
        raise ModelError(f'Invalid iStarML XML: {exc}.') from None
    if _local(root.tag) != 'istarml' or root.get('version') != '1.0':
        raise ModelError('XML import supports the published iStarML 1.0 dialect (<istarml version="1.0">).')
    allowed = {'istarml', 'diagram', 'actor', 'boundary', 'ielement', 'actorLink', 'ielementLink',
               'dependency', 'depender', 'dependee', 'graphic'}
    stack = [root]; count = 0
    while stack:
        element = stack.pop(); tag = _local(element.tag); count += 1
        if count > MAX_LINKS + MAX_ELEMENTS * 4:
            raise ModelError('The imported XML exceeds the prototype semantic-element limit.')
        if tag not in allowed:
            raise ModelError(f'Unsupported iStarML semantic element <{tag}>. No elements were discarded.')
        if tag != 'graphic':
            stack.extend(element)
    diagrams = [d for d in root if _local(d.tag) == 'diagram']
    if not diagrams:
        raise ModelError('The iStarML document contains no diagram.')
    if any(_local(d.tag) not in ('diagram', 'graphic') for d in root):
        raise ModelError('The iStarML root may contain diagrams and graphic metadata only.')
    graph = _new_graph(); warnings = []; used = set(); elements = {}; owners = {}; source_actors = {}
    xml_links = []; dependencies = []; legacy = []
    def graphic(item, element, where):
        for child in element:
            if _local(child.tag) == 'graphic' and child.get('content', 'basic') == 'basic':
                _bounds(item, child.attrib, where, xml=True)
                break
    def collect(element, owner=None, diagram_id=None, inside_graphic=False):
        tag = _local(element.tag)
        if tag == 'graphic' or inside_graphic:
            return
        if tag == 'actor':
            if element.get('aref') is not None:
                raise ModelError('Referenced actor instances require an explicit single-instance iStarML projection.')
            aid = _id(element.get('id'), 'Actor ID')
            source_type = element.get('type', 'actor')
            if source_type not in ('actor', 'role', 'agent', 'position'):
                raise ModelError(f'{aid}: unsupported iStarML actor type {source_type!r}.')
            if owner is not None:
                raise ModelError('Nested iStarML actors require an explicit flat visualization projection.')
            if aid in used:
                raise ModelError(f'Diagram ID {aid!r} is repeated.')
            used.add(aid)
            item = {'id': aid, 'label': _text(element.get('name', aid), aid + '.name'),
                    'kind': source_type if source_type != 'position' else 'actor',
                    'source_type': source_type, 'source_attributes': dict(element.attrib), 'diagram_id': diagram_id}
            graphic(item, element, aid); graph['actors'].append(item); source_actors[aid] = element
            if source_type == 'position':
                legacy.append(f'{aid}: legacy position actor has no exact iStar 2.0 specialization mapping.')
            if set(element.attrib) - {'id', 'name', 'type'}:
                legacy.append(f'{aid}: custom actor attributes remain source metadata without inferred execution meaning.')
            if sum(_local(child.tag) == 'boundary' for child in element) > 1:
                raise ModelError(f'{aid}: one actor may have only one boundary in this display profile.')
            for child in element:
                if _local(child.tag) not in ('graphic', 'actorLink', 'boundary'):
                    raise ModelError(f'{aid}: intentional elements must be inside the actor boundary.')
                if _local(child.tag) == 'boundary':
                    boundary = {}; graphic(boundary, child, aid + '.boundary')
                    if boundary:
                        item['source_boundary'] = boundary
                collect(child, aid, diagram_id)
            return
        if tag == 'ielement':
            if element.get('iref') is not None:
                raise ModelError('Referenced intentional-element instances must appear inside an intentional link.')
            nid = _id(element.get('id'), 'Intentional element ID')
            if nid in used:
                raise ModelError(f'Diagram ID {nid!r} is repeated.')
            used.add(nid)
            source_type = element.get('type')
            kind = NODE_KINDS.get(source_type)
            if kind is None:
                raise ModelError(f'{nid}: unsupported iStarML intentional type {source_type!r}.')
            item = {'id': nid, 'label': _text(element.get('name', nid), nid + '.name'),
                    'kind': kind, 'owner': owner, 'source_type': source_type,
                    'source_attributes': dict(element.attrib), 'diagram_id': diagram_id}
            if set(element.attrib) - {'id', 'name', 'type'}:
                legacy.append(f'{nid}: custom intentional-element attributes remain source metadata without inferred execution meaning.')
            graphic(item, element, nid)
            elements[nid] = element; owners[nid] = owner; graph['nodes'].append(item)
            for child in element:
                ctag = _local(child.tag)
                if ctag == 'ielementLink':
                    xml_links.append((nid, child))
                    for nested in child:
                        if _local(nested.tag) == 'ielement' and nested.get('id') is not None:
                            collect(nested, owner, diagram_id)
                elif ctag == 'dependency':
                    dependencies.append((nid, child)); item['dependum'] = True
                elif ctag != 'graphic':
                    raise ModelError(f'{nid}: unsupported nested iStarML element <{ctag}>.')
            return
        if tag == 'actorLink':
            if owner is None:
                raise ModelError('An iStarML actorLink must be inside its source actor.')
            source_type = _text(element.get('type'), 'actorLink.type')
            meaning = {'is_a': 'isA', 'participates_in': 'participatesIn'}.get(source_type, f'source:actorLink:{source_type}')
            prefix = element.get('id', f'actor_link_{len(graph["links"]) + 1}')
            if element.get('id') is not None and prefix in used:
                raise ModelError(f'Diagram ID {prefix!r} is repeated.')
            _add_link(graph, owner, _id(element.get('aref'), 'actorLink.aref'), meaning, used,
                      prefix, source_type=source_type, source_attributes=dict(element.attrib))
            legacy.append(f'{owner}: legacy actor association {source_type!r} is preserved for visualization.')
            return
        if tag not in ('diagram', 'boundary'):
            raise ModelError(f'Misplaced iStarML semantic element <{tag}>.')
        if tag == 'boundary' and owner is None:
            raise ModelError('An iStarML boundary must belong to an actor.')
        for child in element:
            collect(child, owner, diagram_id)
    for index, diagram in enumerate(diagrams):
        did = diagram.get('id', f'diagram_{index + 1}')
        collect(diagram, diagram_id=did)
    for source, element in xml_links:
        source_type = _text(element.get('type'), 'ielementLink.type')
        value = element.get('value', '')
        references = [element.get('iref')] if element.get('iref') else [child.get('iref', child.get('id')) for child in element if _local(child.tag) == 'ielement']
        if not references or any(not isinstance(ref, str) or not ref for ref in references):
            raise ModelError(f'{source}: intentional link must reference existing intentional elements.')
        declared_id = element.get('id')
        if declared_id is not None:
            _id(declared_id, 'ielementLink.id')
            if declared_id in used:
                raise ModelError(f'Diagram ID {declared_id!r} is repeated.')
            if len(references) > 1:
                used.add(declared_id)
        for j, target in enumerate(references):
            if target not in elements:
                raise ModelError(f'{source}: unknown intentional link target {target!r}.')
            if source_type == 'decomposition' and value.lower() in ('and', 'or'):
                kind = value.lower(); start, end = target, source
            elif source_type == 'means-end':
                kind = 'or'; start, end = target, source
                legacy.append(f'{source}: legacy means-end relation is preserved with its original type.')
            elif source_type == 'contribution':
                kind = CONTRIBUTIONS.get(value, f'source:contribution:{value}'); start, end = source, target
                if kind not in ('make', 'break'):
                    legacy.append(f'{source}: contribution {value!r} has no exact executable effect mapping.')
            else:
                kind = f'source:ielementLink:{source_type}:{value}'; start, end = source, target
                legacy.append(f'{source}: intentional relation {source_type!r}/{value!r} is preserved for visualization.')
            prefix = (declared_id if len(references) == 1 else f'{declared_id}_{j + 1}') if declared_id else f'intentional_link_{len(graph["links"]) + 1}'
            _add_link(graph, start, end, kind, used, prefix, source_link_id=declared_id,
                      source_type=source_type, source_value=value, source_attributes=dict(element.attrib))
    node_index = {n['id']: n for n in graph['nodes']}
    for dependum, dependency in dependencies:
        if owners[dependum] is not None:
            raise ModelError(f'{dependum}: a dependency dependum must be outside actor boundaries.')
        endpoints = {}
        for kind in ('depender', 'dependee'):
            matches = [child for child in dependency if _local(child.tag) == kind]
            if len(matches) != 1:
                raise ModelError(f'{dependum}: a dependency requires one {kind}.')
            endpoint = matches[0]
            actor = _id(endpoint.get('aref'), dependum + '.' + kind + '.aref')
            local = endpoint.get('iref')
            if actor not in source_actors:
                raise ModelError(f'{dependum}: unknown {kind} actor {actor!r}.')
            if local is not None and (local not in owners or owners[local] != actor):
                raise ModelError(f'{dependum}: local {kind} endpoint has a different owner.')
            endpoints[kind] = local or actor
        _add_link(graph, endpoints['depender'], dependum, 'dependency', used,
                  f'{dependum}_dependency_in', dependency_id=dependum)
        _add_link(graph, dependum, endpoints['dependee'], 'dependency', used,
                  f'{dependum}_dependency_out', dependency_id=dependum)
        node_index[dependum]['dependency_source'] = endpoints['depender']
        node_index[dependum]['dependency_target'] = endpoints['dependee']
    warnings.extend(legacy)
    if len(diagrams) > 1:
        warnings.append('All source diagrams are retained as one display graph with diagram_id metadata.')
    # A piStar-shaped intermediate is used only for exact executable admission.
    types = {'goal': 'Goal', 'task': 'Task', 'quality': 'Quality', 'resource': 'Resource'}
    candidate = {'istar': '2.0', 'tool': 'PATPREF iStarML 1.0 adapter',
                 'diagram': {'name': diagrams[0].get('name', 'Imported iStarML model')},
                 'actors': [], 'orphans': [], 'dependencies': [], 'links': []}
    for actor in graph['actors']:
        candidate['actors'].append({'id': actor['id'], 'text': actor['label'],
                                     'type': 'istar.' + actor['kind'].title(), 'nodes': []})
    actor_index = {a['id']: a for a in candidate['actors']}
    for node in graph['nodes']:
        if node['kind'] not in types:
            legacy.append(f'{node["id"]}: precise-preference element is outside this XML execution mapping.')
            continue
        item = {'id': node['id'], 'text': node['label'], 'type': 'istar.' + types[node['kind']]}
        if node.get('dependum'):
            item.update(source=node['dependency_source'], target=node['dependency_target'])
            candidate['dependencies'].append(item)
        elif node['owner']:
            actor_index[node['owner']]['nodes'].append(item)
        else:
            candidate['orphans'].append(item)
    link_types = {'and': 'AndRefinementLink', 'or': 'OrRefinementLink', 'dependency': 'DependencyLink'}
    for link in graph['links']:
        item = {'id': link['id'], 'source': link['source'], 'target': link['target']}
        if link['kind'] in link_types:
            item['type'] = 'istar.' + link_types[link['kind']]
        elif link['kind'] in ('make', 'break'):
            item.update(type='istar.ContributionLink', label=link['kind'])
        else:
            legacy.append(f'{link["id"]}: relation is outside the exact XML execution mapping.')
            continue
        candidate['links'].append(item)
    name = ' / '.join(d.get('name', d.get('id', f'Diagram {i + 1}')) for i, d in enumerate(diagrams))
    return graph, _text(name, 'Diagram name'), list(dict.fromkeys(warnings + legacy)), candidate, legacy


def load_diagram(document, filename=None):
    """Return a full display graph and an optional exact PATPREF reasoning session."""
    original, xml = _parse(document)
    unsupported = []
    if xml:
        graph, name, warnings, execution_document, unsupported = _xml(original)
        fmt = 'istarml-1.0'
    elif 'actors' in original and 'links' in original:
        graph, name, warnings, execution_document = _pistar(original)
        fmt = 'pistar-2.0'
    else:
        graph, name, warnings, execution_document = _native(original)
        fmt = 'apate'
    _validate_graph(graph)
    session = None; id_map = {}; findings = list(dict.fromkeys(unsupported))
    if not findings:
        try:
            admitted = import_goal_model(execution_document)
            session = admitted['session']; id_map = admitted['report']['id_map']
            if xml:
                session['import_provenance'] = {'format': fmt, 'source_document': original,
                    'id_map': deepcopy(id_map), 'source': deepcopy(XML_SOURCE)}
        except ModelError as exc:
            findings = [str(exc), *exc.details]
    report = {'warnings': warnings, 'reasoning_supported': session is not None,
              'reasoning_findings': findings, 'id_map': id_map,
              'input_actors': len(graph['actors']), 'input_nodes': len(graph['nodes']),
              'input_links': len(graph['links']), 'format': fmt,
              'source': deepcopy(XML_SOURCE) if xml else {'format': fmt}}
    if filename is not None:
        report['filename'] = _text(filename, 'Filename', 1024)
    return {'name': name, 'format': fmt, 'graph': graph, 'session': session,
            'report': report, 'source_document': deepcopy(original)}
