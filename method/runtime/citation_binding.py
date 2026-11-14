"""Literal citation-location diagnostics for a parsed generator candidate.

This module reports exact substring membership and possible original locations.
It does not assess persona meaning, rule premises or preference direction. It
never rewrites the candidate, chooses a replacement location or changes the
final validator. No quoted text or complete source fields enter its output.
"""

TEXT_FIELDS = ('label', 'description', 'meaning')


def _nonempty_text(value):
    return isinstance(value, str) and bool(value.strip())


def _original_nodes(model):
    if not isinstance(model, dict):
        return {}
    original = model.get('M0', model)
    if not isinstance(original, dict):
        return {}
    nodes = original.get('nodes')
    return nodes if isinstance(nodes, dict) else {}


def citation_binding_diagnostics(candidate, persona, model):
    """Return booleans, ordinals and exact candidate ``node_id/field`` pairs.

    ``candidate`` is the actual already-parsed generator JSON, not text to parse
    or repair. ``persona`` is the original persona object. Source node iteration
    order and the fixed label/description/meaning order are retained. A correct
    declared binding is reported without enumerating alternative locations.

    Missing or malformed data produce false shape/membership flags. They do not
    trigger coercion, source guesses, quote normalization or semantic judgment.
    The unchanged fixed validator remains responsible for final acceptance.
    """
    proposals = candidate.get('proposals') if isinstance(candidate, dict) else None
    proposals_is_array = isinstance(proposals, list)
    result = {'proposals_is_array': proposals_is_array, 'proposals': []}
    if not proposals_is_array:
        return result
    description = persona.get('description') if isinstance(persona, dict) else None
    nodes = _original_nodes(model)
    for proposal_ordinal, raw_proposal in enumerate(proposals):
        proposal = raw_proposal if isinstance(raw_proposal, dict) else {}
        persona_quote = proposal.get('persona_quote')
        evidence = proposal.get('model_evidence')
        row = {
            'proposal_ordinal': proposal_ordinal,
            'proposal_is_object': isinstance(raw_proposal, dict),
            'persona_quote_literal': bool(_nonempty_text(persona_quote)
                and isinstance(description, str) and persona_quote in description),
            'model_evidence_is_array': isinstance(evidence, list),
            'model_evidence': [],
        }
        if isinstance(evidence, list):
            for evidence_ordinal, raw_citation in enumerate(evidence):
                citation = raw_citation if isinstance(raw_citation, dict) else {}
                node_id, field, quote = (citation.get(key) for key in ('node_id', 'field', 'quote'))
                node = nodes.get(node_id) if isinstance(node_id, str) else None
                node_exists = isinstance(node, dict)
                field_allowed = isinstance(field, str) and field in TEXT_FIELDS
                field_exists = bool(node_exists and isinstance(field, str) and field in node)
                value = node.get(field) if field_exists else None
                quote_nonempty = _nonempty_text(quote)
                literal_binding = bool(node_exists and field_allowed and quote_nonempty
                    and isinstance(value, str) and quote in value)
                matches = []
                if not literal_binding and quote_nonempty:
                    for original_id, original_node in nodes.items():
                        if not isinstance(original_id, str) or not isinstance(original_node, dict):
                            continue
                        for original_field in TEXT_FIELDS:
                            original_value = original_node.get(original_field)
                            if isinstance(original_value, str) and quote in original_value:
                                matches.append({'node_id': original_id, 'field': original_field})
                row['model_evidence'].append({
                    'evidence_ordinal': evidence_ordinal,
                    'citation_is_object': isinstance(raw_citation, dict),
                    'quote_nonempty': quote_nonempty,
                    'declared_node_exists': node_exists,
                    'declared_field_allowed': field_allowed,
                    'declared_field_exists': field_exists,
                    'literal_binding': literal_binding,
                    'literal_matches': matches,
                })
        result['proposals'].append(row)
    return result
