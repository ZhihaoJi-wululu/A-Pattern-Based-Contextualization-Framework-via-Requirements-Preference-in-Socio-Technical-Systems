"""Narrow, catalogue-authorized action grammars for canonical pattern bindings.

These are inspectable design operationalizations, not keyword guesses about
people or episodes. Unmatched or ambiguous task language stays with semantic
review. No reference answers or case identifiers are available here.
"""
from copy import deepcopy
import re
from .material_objects import organization_direct_object


_OBJECT_STOP = {'a', 'an', 'the', 'by', 'in', 'on', 'at', 'to', 'of', 'for', 'with',
    'using', 'under', 'according', 'accepted', 'agreed', 'specified',
    'index', 'indexed', 'indexing', 'category', 'categories', 'classification',
    'directory', 'received', 'arrival', 'chronological', 'linear', 'order', 'date',
    'file', 'filed', 'filing', 'retained', 'handled', 'prepared', 'organized', 'organised', 'arranged', 'recorded'}

_MATERIAL_HEADS = {'record', 'evidence', 'material', 'document', 'data', 'note',
    'report', 'content', 'artifact', 'collection', 'archive', 'catalog', 'entry'}


def _object_words(text):
    result = set()
    for word in re.findall(r'[a-z]+', text.lower()):
        if word not in _OBJECT_STOP:
            result.add(word[:-1] if len(word) > 4 and word.endswith('s') else word)
    return result


def _action(label, anchor):
    text = ' '.join(label.lower().split())
    if '--' in text: return None
    if re.search(r"\b(if|unless|when|pending|provided|not|never|without|may|might)\b|"
            r"\b(subject to|only after|after approval|before approval|do not|don't)\b", text):
        return None
    head = re.match(r'^([a-z]+)\b\s*(.*)$', text)
    if not head: return None
    verb, tail = head.groups()
    material = organization_direct_object(text)
    if material is None: return None
    positive = set(anchor.get('preferred_action_heads', []))
    negative = set(anchor.get('contrasted_action_heads', []))
    if verb in positive:
        return {'polarity': 'preferred', 'objects': _object_words(material), 'grammar': 'preferred_action_head'}
    # Filing under an index is a specific organizational action. Merely reading
    # an indexing manual or running a command with --index is not that action.
    if verb in ('file', 'organize', 'organise') and re.search(
            r'\b(by|using|under|according to)\s+(?:the\s+)?(?:(?:accepted|agreed|specified|subject|category|directory)\s+)*'
            r'(?:index|categories|classification|directory)\b', tail):
        return {'polarity': 'preferred', 'objects': _object_words(material), 'grammar': 'file_under_index'}
    if re.search(r'\b(index\w*|categor\w*|classif\w*|structured|directory)\b', tail):
        return None
    if verb in negative and verb == 'append':
        return {'polarity': 'contrasted', 'objects': _object_words(material), 'grammar': 'linear_append_action_head'}
    if verb in ('file', 'keep', 'retain') and re.search(r'\b(received|arrival|chronological)\s+order\b', tail):
        return {'polarity': 'contrasted', 'objects': _object_words(material), 'grammar': 'received_or_chronological_order'}
    linear_forms = set(anchor.get('contrasted_linear_forms', []))
    if (verb in ('file', 'retain') and verb + '_by_date' in linear_forms
            and re.search(r'\bby\s+date\b', tail)):
        return {'polarity': 'contrasted', 'objects': _object_words(material), 'grammar': 'date_order_filing'}
    return None


def _same_material(left, right, parent):
    if not left or not right:
        if not parent.intersection(_MATERIAL_HEADS): return None
        left = left or parent; right = right or parent
    if left == right:
        return sorted(left)
    # A shortened label can omit modifiers explicitly supplied by its own OR
    # topic. Conflicting modifiers (source records vs completion records) are
    # not unified merely because a generic material noun occurs in both.
    if (left <= right or right <= left) and left | right <= parent:
        return sorted(left | right)
    return None


def _equal_explicit_index_effect(model, source_nodes, target_nodes):
    for quality, node in model['nodes'].items():
        if node['kind'] not in ('softgoal', 'hard_preference') or not re.search(
                r'\b(indexed|categor(?:ized|ised)|classified|structured)\b', node['label'], re.I):
            continue
        positive = {edge['source'] for edge in model.get('contributions', [])
                    if edge['target'] == quality and edge['type'] == 'makes'}
        negative = {edge['source'] for edge in model.get('contributions', [])
                    if edge['target'] == quality and edge['type'] == 'breaks'}
        if (positive.intersection(source_nodes) and positive.intersection(target_nodes)
                and not negative.intersection(source_nodes | target_nodes)):
            return quality
    return None


def explicit_persona_counterevidence(description):
    for sentence in re.split(r'(?<=[.!?])\s+|\n+', description):
        opposite = re.search(r'\b(prefer\w*|favo\w*)\b.{0,90}\b(chronological|received.order|date.order)\b'
            r'.{0,60}\b(over|rather than|instead of|to)\b.{0,40}\b(index\w*|categor\w*|structur\w*)\b', sentence, re.I)
        rejection = re.search(r'\b(rejects?|avoids?|dislikes?)\s+(?:the\s+|additional\s+)?'
            r'(indexing|categorization|categorisation|structuring)\b', sentence, re.I)
        if opposite or rejection:
            match = opposite or rejection
            if not re.search(r'\b(not|never|no)\b', sentence[max(0, match.start() - 18):match.start()], re.I):
                return sentence
    return None


def compile_bindings(model, persona, decisions, rules, must_nodes):
    output = []
    for rule in rules.values():
        for anchor in rule.get('canonical_semantic_anchors', []):
            if anchor.get('grammar') != 'organization_action_heads_v1':
                continue
            for decision_id, decision in decisions.items():
                if decision['kind'] != 'choice' or 'choice' not in anchor.get('allowed_kinds', ['choice']):
                    continue
                endpoints = {}
                for endpoint in decision['endpoints']:
                    matches = []
                    for node in sorted(must_nodes(model, endpoint, endpoint)):
                        if model['nodes'][node]['kind'] != 'task': continue
                        match = _action(model['nodes'][node]['label'], anchor)
                        if match: matches.append({'node_id': node, **match})
                    polarities = {match['polarity'] for match in matches}
                    # Mixed operations and branch-dependent semantics are not a
                    # canonical contrast. They require normal semantic review.
                    if len(polarities) == 1:
                        endpoints[endpoint] = {'polarity': next(iter(polarities)), 'matches': matches}
                for source, preferred in endpoints.items():
                    if preferred['polarity'] != 'preferred': continue
                    for target, other in endpoints.items():
                        if other['polarity'] != 'contrasted': continue
                        parent_label = model['nodes'][decision['node_id']]['label']
                        inherited = _object_words(parent_label)
                        pair = None
                        for a in preferred['matches']:
                            for b in other['matches']:
                                common = _same_material(a['objects'], b['objects'], inherited)
                                if common:
                                    pair = (a, b, sorted(common)); break
                            if pair: break
                        if not pair: continue
                        if _equal_explicit_index_effect(model,
                                must_nodes(model, source, source), must_nodes(model, target, target)):
                            continue
                        a, b, material = pair
                        citations = [{'node_id': node, 'quote': model['nodes'][node]['label']}
                                     for node in (a['node_id'], b['node_id'], decision['node_id'])]
                        proposal = {'rule_id': rule['id'], 'source': source, 'target': target,
                            'formula': 'preferred_to', 'model_evidence': citations, 'semantic_coverage': {},
                            'contrast': {'outcome_id': anchor['outcome_id'], 'source_effect': 'present',
                                'target_effect': 'absent', 'criterion_quality_id': '__none__', 'criterion_polarity': 'positive'},
                            'rationale': anchor['description']}
                        output.append({'decision_id': decision_id, 'proposal': proposal,
                            'origin': 'catalogue_canonical_pattern_compiler', 'anchor_id': anchor['id'],
                            'grammar': anchor['grammar'], 'shared_material_terms': material,
                            'source_action': {'grammar': a['grammar'], 'material_terms': sorted(a['objects'])},
                            'target_action': {'grammar': b['grammar'], 'material_terms': sorted(b['objects'])},
                            'source_task_id': a['node_id'], 'target_task_id': b['node_id']})
    return output


def merge_bindings(response, bindings, persona=None, *, rules=None, model=None):
    # Local import avoids a module cycle: contracts reuse the original
    # organization action grammar, while this merger validates exceptions.
    from .semantic_contracts import validated_persona_counterevidence
    output = deepcopy(response); changes = []
    for binding in bindings:
        proposal = binding['proposal']; record = output['decisions'][binding['decision_id']]
        explicit = (explicit_persona_counterevidence(persona.get('description', ''))
                    if persona and binding['grammar'] == 'organization_action_heads_v1' else None)
        rule = (rules or {}).get(proposal['rule_id']) or {'facet': binding.get('facet') or
            ('Organization' if binding['grammar'] == 'organization_action_heads_v1' else None)}
        supplied = []
        for item in response.get('canonical_persona_exceptions', []):
            if item['decision_id'] != binding['decision_id'] or item['rule_id'] != proposal['rule_id']: continue
            certificate = validated_persona_counterevidence(persona or {}, rule, item.get('quote'), model, proposal)
            if certificate: supplied.append({**deepcopy(item), 'validated_counterevidence': certificate})
        if explicit or supplied:
            blocked = [item for item in record['proposals'] if all(item.get(key) == proposal[key]
                for key in ('rule_id', 'source', 'target', 'formula'))]
            record['proposals'] = [item for item in record['proposals'] if item not in blocked]
            record['rule_reviews'][proposal['rule_id']] = ('proposed' if any(
                item['rule_id'] == proposal['rule_id'] for item in record['proposals']) else 'not_applicable')
            record['status'] = 'proposed' if record['proposals'] else 'not_applicable'
            changes.append({'decision_id': binding['decision_id'], 'anchor_id': binding['anchor_id'],
                'action': 'blocked_by_persona_counterevidence', 'literal_persona_quote': explicit,
                'semantic_review_exceptions': deepcopy(supplied), 'blocked_same_direction_proposals': deepcopy(blocked)})
            continue
        same = [item for item in record['proposals'] if all(item.get(key) == proposal[key]
            for key in ('rule_id', 'source', 'target', 'formula'))]
        record['proposals'] = [item for item in record['proposals'] if item not in same] + [deepcopy(proposal)]
        record['status'] = 'proposed'
        record['rule_reviews'][proposal['rule_id']] = 'proposed'
        # This evidence is independently compiled from the unchanged persona
        # description, not manufactured from the generated preference.
        pe = binding.get('persona_evidence')
        facet = rule.get('facet')
        if facet and pe and pe.get('supported'):
            quote = pe.get('quote', '')
            if quote and quote in persona.get('description', ''):
                output['facet_evidence'][facet] = {'supported': True, 'quote': quote}
        quality = proposal.get('contrast', {}).get('criterion_quality_id')
        if quality and quality != '__none__':
            tag = proposal['rule_id'] + '::' + proposal['contrast']['outcome_id']
            if tag not in output['quality_bindings'].setdefault(quality, []):
                output['quality_bindings'][quality].append(tag)
        changes.append({'decision_id': binding['decision_id'], 'anchor_id': binding['anchor_id'],
            'replaced_same_relation_bindings': deepcopy(same), 'compiled_proposal': deepcopy(proposal)})
    return output, changes
