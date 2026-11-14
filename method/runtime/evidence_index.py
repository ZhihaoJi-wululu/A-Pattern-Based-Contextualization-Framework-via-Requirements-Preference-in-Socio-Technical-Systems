"""ID-only protocol index derived from the unchanged active choice-rule resolver.

The index exposes legal rule/outcome identifiers, never semantic applicability,
preference endpoints, model evidence, expected relations or external answers.
"""
from apate.preferred_protocol import rules_for

INDEX_ID = 'apate.eligible-choice-rule-outcome-ids.v1'

def eligible_rule_outcome_index(pattern, active_facet):
    """Preserve resolver order and ambiguity; do not deduplicate invalid rules."""
    return [{'rule_id': rule['id'], 'pattern_id': rule['pattern_id'], 'outcome_id': outcome['id']}
        for rule in rules_for(pattern, [active_facet]) for outcome in rule['outcomes']]
