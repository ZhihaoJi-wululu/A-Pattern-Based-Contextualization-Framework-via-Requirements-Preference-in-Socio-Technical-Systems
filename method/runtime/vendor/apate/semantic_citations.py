"""Literal evidence protocol for the immutable original persona (v43-07).

Normalize an existing supported facet quotation only when a separately derived
certificate quotes the original persona verbatim. This is evidence-protocol
repair, not a semantic review or a source of new preference bindings. The caller
must retain the physical response and run all ordinary validation afterwards.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re

from .semantic_contracts import persona_evidence, persona_quote_evidence


POLICY = 'apate.persona-quotation-reconciliation.v2'


def persona_quotation_domain(description, *, max_segments=32, extra_character_budget=4096):
    """Neutral original quotation choices shared by every selected facet.

    Preserve the complete original description as a fallback. Additional
    original sentence/line spans improve citation precision without selecting
    them by trait, predicted relation, case identity or evaluation reference.
    Budgets limit added schema text, never truncate the underlying persona.
    """
    if not isinstance(description, str) or not description:
        return ['']
    candidates = ['', description]
    remaining = max(0, extra_character_budget)
    for segment in re.split(r'(?<=[.!?。！？])\s+|\n+', description):
        quote = segment.strip()
        if len(candidates) >= max_segments + 2:
            break
        if not quote or quote in candidates or quote not in description:
            continue
        if len(quote) < 15 or len(quote) > remaining:
            continue
        candidates.append(quote)
        remaining -= len(quote)
    return candidates


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def reconcile_persona_quotations(response, persona, rules, *, stage):
    """Return ``(working_response, audit)`` without modifying any argument.

    Only a well-typed ``supported=True`` row with a string quote is eligible.
    A literal span must also establish the selected persona facet: occupational
    or object mentions do not become personality evidence. Relevant literal
    quotes remain unchanged. Malformed/missing protocol fields remain errors.

    Without an independent supported literal certificate, the facet becomes
    unsupported and its dependent proposals are suppressed in the working copy;
    existing corresponding reviews become unknown. No decision/review is added.
    Such a downgrade always requires information, even if other proposals remain.
    This helper never marks a semantic stage completed and never retries a call.
    """
    output = deepcopy(response)
    audit = {'policy': POLICY, 'stage': stage, 'raw_response_sha256': _hash(response),
             'repairs': [], 'decision_updates': [], 'needs_information': False}
    rows = output.get('facet_evidence') if isinstance(output, dict) else None
    description = persona.get('description') if isinstance(persona, dict) else None
    rules_by_facet = {}
    for rule in rules.values():
        if isinstance(rule, dict) and isinstance(rule.get('id'), str):
            rules_by_facet.setdefault(rule.get('facet'), []).append(rule)
    unsupported_rules = set()
    if isinstance(rows, dict) and isinstance(description, str):
        for facet, row in rows.items():
            if not (isinstance(row, dict) and row.get('supported') is True
                    and isinstance(row.get('quote'), str)):
                continue
            quote = row['quote']
            applicable = sorted(rules_by_facet.get(facet, []), key=lambda item: item['id'])
            literal = bool(quote.strip()) and quote in description
            if literal and any(persona_quote_evidence(persona, rule, quote).get('supported') is True
                               for rule in applicable):
                continue
            certificates = [{'rule_id': rule['id'], **persona_evidence(persona, rule)}
                            for rule in applicable]
            certificate = next((item for item in certificates
                                if item.get('supported') is True
                                and isinstance(item.get('quote'), str)
                                and item['quote'].strip()
                                and item['quote'] in description), None)
            previous = deepcopy(row)
            if certificate:
                row['quote'] = certificate['quote']
                reason = ('Independent original-persona certificate replaces a literal quotation without relevant trait evidence.'
                          if literal else 'Independent original-persona certificate replaces a nonliteral quotation.')
                action = 'replace_quote_from_independent_certificate'
            else:
                row.update(supported=False, quote='')
                unsupported_rules.update(rule['id'] for rule in applicable)
                audit['needs_information'] = True
                reason = 'No independent supported literal persona certificate; dependent support is unresolved.'
                action = 'downgrade_unsupported'
            audit['repairs'].append({'path': ['facet_evidence', facet], 'facet': facet,
                                     'raw': previous, 'repaired': deepcopy(row),
                                     'action': action, 'reason': reason,
                                     'independent_certificates': certificates})
    decisions = output.get('decisions') if isinstance(output, dict) else None
    if unsupported_rules and isinstance(decisions, dict):
        for identity, row in decisions.items():
            # No reconstruction of omitted/malformed protocol matrices.
            if not (isinstance(row, dict) and isinstance(row.get('proposals'), list)
                    and isinstance(row.get('rule_reviews'), dict)):
                continue
            matrix = row['rule_reviews']
            affected = sorted(set(matrix) & unsupported_rules)
            removed = [p for p in row['proposals']
                       if isinstance(p, dict) and p.get('rule_id') in unsupported_rules]
            if not affected and not removed:
                continue
            previous = deepcopy(row)
            row['proposals'] = [p for p in row['proposals']
                                if not (isinstance(p, dict) and p.get('rule_id') in unsupported_rules)]
            for rule_id in affected:
                matrix[rule_id] = 'unknown'
            row['status'] = 'proposed' if row['proposals'] else 'needs_information'
            audit['decision_updates'].append({'decision_id': identity, 'affected_rules': affected,
                                              'removed_proposals': removed,
                                              'raw': previous, 'repaired': deepcopy(row),
                                              'reason': 'Unsupported facet cannot supply an accepted rule binding.'})
    audit['repaired_response_sha256'] = _hash(output)
    return output, audit
