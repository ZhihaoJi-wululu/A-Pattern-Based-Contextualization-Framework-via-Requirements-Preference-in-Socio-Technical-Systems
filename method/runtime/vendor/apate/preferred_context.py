"""Deterministic source-record focus for already enumerated opportunity batches.

The complete projected catalogue remains the input authority. This helper never
enumerates opportunities, interprets their meaning, or consumes model judgments.
It retains complete source records and their structured reference closure.
"""
from copy import deepcopy

from .preferred_protocol import digest


POLICY_ID = 'apate.preferred-pattern-focus.family-closure.v1'
COLLECTIONS = ('patterns', 'rules', 'model_semantic_rules')
SCOPED_FIELDS = frozenset((*COLLECTIONS, 'facets'))


class FocusError(ValueError):
    pass


def _strings(value):
    if isinstance(value, str) and value:
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) and item for item in value):
        return value
    raise FocusError('A structured pattern reference is not a nonempty ID or ID list.')


def _references(value, *, facet_metadata=False):
    result = []
    if isinstance(value, dict):
        for key, child in value.items():
            namespace = ('pattern' if key in ('pattern_id', 'pattern_ids') or key == 'patterns' and facet_metadata
                         else 'rule' if key in ('rule_id', 'rule_ids', 'model_semantic_rule_ids')
                         else 'facet' if key in ('facet', 'facets') else None)
            if namespace:
                result.extend((namespace, identity) for identity in _strings(child))
            elif isinstance(child, (dict, list)):
                result.extend(_references(child))
    elif isinstance(value, list):
        for child in value:
            if isinstance(child, (dict, list)):
                result.extend(_references(child))
    return result


def _rows(source):
    if not isinstance(source, dict):
        raise FocusError('The projected pattern must be an object.')
    records = {}
    for field in COLLECTIONS:
        rows = source.get(field, [])
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise FocusError('Pattern record collections must be arrays of objects.')
        for index, row in enumerate(rows):
            records[(field, index)] = row
    facets = source.get('facets', {})
    if not isinstance(facets, dict) or any(not isinstance(row, dict) for row in facets.values()):
        raise FocusError('Facet metadata must map IDs to objects.')
    records.update({('facets', key): row for key, row in facets.items()})
    return records


def _root_references(batch):
    if not isinstance(batch, list) or not batch:
        raise FocusError('Pattern focus requires a nonempty opportunity batch.')
    refs = []
    for unit in batch:
        if not isinstance(unit, dict):
            raise FocusError('Every opportunity must be an object.')
        for key, namespace in [('rule_id', 'rule'), ('pattern_id', 'pattern'), ('facet', 'facet')]:
            if not isinstance(unit.get(key), str) or not unit[key]:
                raise FocusError('Every opportunity requires an exact ' + key + '.')
            refs.append((namespace, unit[key]))
    return refs


def _resolve(records, namespace, identity):
    if namespace == 'facet':
        matches = [('facets', identity)] if ('facets', identity) in records else []
    else:
        collections = ('patterns',) if namespace == 'pattern' else ('rules', 'model_semantic_rules')
        matches = [path for path, row in records.items() if path[0] in collections
                   and identity in {row.get('id'), row.get('rule_id')}]
        # rules_for also permits a parent record carrying its own legacy
        # instantiation when there is no separately declared rule record.
        if namespace == 'rule' and not matches:
            matches = [path for path, row in records.items() if path[0] == 'patterns'
                       and 'instantiation' in row and identity in {row.get('id'), row.get('rule_id')}]
    if len(matches) != 1:
        raise FocusError('Pattern reference has no unique source: ' + namespace + ':' + identity)
    return matches[0]


def _family_paths(records, path):
    """Reverse family links prevent removal of a sibling semantic branch."""
    row = records[path]
    if path[0] == 'facets':
        facet = path[1]
        return [other for other, value in records.items() if other[0] != 'facets'
                and (value.get('facet') == facet or facet in value.get('facets', []))]
    if path[0] == 'patterns':
        identity = row.get('id')
        return [other for other, value in records.items() if other[0] in ('rules', 'model_semantic_rules')
                and (value.get('pattern_id') == identity or identity in value.get('pattern_ids', []))]
    return []


def _select_paths(source, batch):
    records = _rows(source)
    pending = [_resolve(records, *ref) for ref in _root_references(batch)]
    selected = set()
    while pending:
        path = pending.pop()
        if path in selected:
            continue
        selected.add(path)
        pending.extend(_family_paths(records, path))
        pending.extend(_resolve(records, *ref) for ref in
                       _references(records[path], facet_metadata=path[0] == 'facets'))
    return selected


def _record_audit(source, paths):
    records = _rows(source)
    # Source insertion order, including numeric list order, is authoritative.
    return [{'path': list(path), 'sha256': digest(row)}
            for path, row in records.items() if path in paths]


def _build_focused(source, paths):
    focused = deepcopy(source)
    for field in COLLECTIONS:
        if field in source:
            focused[field] = [deepcopy(row) for index, row in enumerate(source[field]) if (field, index) in paths]
    if 'facets' in source:
        focused['facets'] = {key: deepcopy(row) for key, row in source['facets'].items() if ('facets', key) in paths}
    return focused


def focus_pattern(source, batch):
    """Return (focused original records, provenance audit), or the full source.

    Missing/ambiguous references conservatively keep the entire source. This
    never edits the original pattern, source objects, batch, or opportunity IDs.
    """
    source_hash = digest(source)
    mode, reason = 'focused', None
    try:
        paths = _select_paths(source, batch)
        focused = _build_focused(source, paths)
    except (FocusError, TypeError, KeyError) as exc:
        mode, reason = 'full_source_fallback', str(exc)
        focused = deepcopy(source)
        paths = set(_rows(source))
    audit = {'policy': POLICY_ID, 'mode': mode, 'fallback_reason': reason,
             'source_pattern_sha256': source_hash,
             'batch_units_sha256': digest(batch),
             'batch_unit_ids': [unit.get('id') for unit in batch] if isinstance(batch, list) else None,
             'global_fields': [key for key in source if key not in SCOPED_FIELDS],
             'records': _record_audit(source, paths), 'focused_pattern_sha256': digest(focused)}
    verify_focus(source, batch, focused, audit)
    return focused, audit


def verify_focus(source, batch, focused, audit):
    """Independently check source equality, lineage and complete family closure.

    This does not call the selection algorithm. It checks necessary invariants
    directly on the transmitted records and rejects altered, missing, reordered
    or injected records even when a caller recomputes their hashes.
    """
    def require(condition, message):
        if not condition:
            raise FocusError(message)
    require(isinstance(audit, dict) and audit.get('policy') == POLICY_ID, 'Unknown focus audit policy.')
    require(audit.get('source_pattern_sha256') == digest(source), 'Source pattern identity mismatch.')
    require(audit.get('batch_units_sha256') == digest(batch), 'Opportunity batch identity mismatch.')
    require(audit.get('batch_unit_ids') == ([unit.get('id') for unit in batch] if isinstance(batch, list) else None),
            'Opportunity IDs differ from the sealed batch.')
    require(isinstance(focused, dict) and set(focused) == set(source), 'Focused top-level fields differ.')
    require(audit.get('focused_pattern_sha256') == digest(focused), 'Transmitted pattern hash mismatch.')
    globals_ = [key for key in source if key not in SCOPED_FIELDS]
    require(audit.get('global_fields') == globals_, 'Global field audit differs.')
    require(all(focused[key] == source[key] for key in globals_), 'A complete public contract was altered.')
    records = _rows(source)
    paths = []
    for evidence in audit.get('records', []):
        require(isinstance(evidence, dict) and isinstance(evidence.get('path'), list), 'Invalid record lineage.')
        path = tuple(evidence['path'])
        require(path in records, 'Record lineage is outside the original catalogue.')
        require(evidence.get('sha256') == digest(records[path]), 'An original record hash differs.')
        paths.append(path)
    require(len(paths) == len(set(paths)), 'Duplicate record lineage.')
    selected = set(paths)
    require(paths == [path for path in records if path in selected], 'Original source record order changed.')
    for field in COLLECTIONS:
        if field in source:
            expected = [row for index, row in enumerate(source[field]) if (field, index) in selected]
            require(focused[field] == expected, 'A complete source record was altered, omitted or injected.')
    if 'facets' in source:
        expected = {key: row for key, row in source['facets'].items() if ('facets', key) in selected}
        require(focused['facets'] == expected, 'Facet metadata differs from its exact source.')
    if audit.get('mode') == 'full_source_fallback':
        require(focused == source and selected == set(records), 'Fallback must preserve the complete source.')
        require(isinstance(audit.get('fallback_reason'), str) and bool(audit['fallback_reason']),
                'Fallback must identify the source-selection problem.')
        return True
    require(audit.get('mode') == 'focused' and audit.get('fallback_reason') is None, 'Invalid selection mode.')
    for reference in _root_references(batch):
        require(_resolve(records, *reference) in selected, 'A batch rule, parent or facet was omitted.')
    for path in selected:
        for reference in _references(records[path], facet_metadata=path[0] == 'facets'):
            require(_resolve(records, *reference) in selected, 'A required structured reference was omitted.')
        require(set(_family_paths(records, path)) <= selected, 'A complete related facet family was omitted.')
    return True
