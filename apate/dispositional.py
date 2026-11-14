"""Model-semantic, qualitative design preferences over an immutable goal model.

The language model maps supplied personality descriptions and original model
semantics to reviewed pattern branches. Python independently owns identifier,
structure, role, quotation and complete-plan checks. No episode is synthesized.
"""
from copy import deepcopy
from functools import lru_cache
from itertools import islice
from pathlib import Path
import hashlib
import json
import re
import time

from . import provider, workbench as wb
from .compiler import compile_model
from .contextualize import _ModelView, evaluate_concern
from .provider_schema import _shared_enums
from .schema import ModelError, business_projection, model_hash, validate_model
from .semantics import attained, selected_attainment_model, validate_plan
from .store import SessionConflict
from .semantic_anchors import compile_bindings, merge_bindings
from .semantic_evidence import contact_quality_matches, direct_contact_evidence, direct_solitary_evidence
from .scheduling_guards import prepare_npr_forward_checks, npr_prefix_impossible
from .semantic_contracts import check_semantic_contract, derive_semantic_bindings, persona_quote_evidence
from .semantic_citations import persona_quotation_domain, reconcile_persona_quotations
from .semantic_packets import compact_semantic_bindings
from .final_model import POLICY_ID, finalize_model_result, failed_model_result

CATALOGUE = Path(__file__).resolve().parents[1] / 'data' / 'pattern_catalogue_v43.json'
METHOD_ID = 'apate.model-semantics.v2'
INPUT_ID = 'apate.input.three.v1'
SEMANTIC_MAX_TOKENS = 18000
SEMANTIC_TRANSPORT_RETRIES = 9
SEMANTIC_RETRY_BACKOFF_SECONDS = 5
SEMANTIC_RETRY_BACKOFF_CAP_SECONDS = 30
SEMANTIC_RETRY_BUDGET_SECONDS = 600

INSTRUCTION = """Model qualitative persona-driven preference requirements using
only the supplied persona, pattern branches and immutable goal model. The
branches describe literature-inspired design preferences, not actual current
behavior or a unique mandatory action. Use task/goal labels, original quality
effects and ownership to identify their existing semantic opportunities.
Python constructs and validates execution witnesses and hard constraints; do
not simulate plan enumeration in this response. Review the original semantic
meaning, every relevant scope implementation and contrary evidence. Internal
certificate summaries reference the unchanged original inputs and do not make
a binding exempt from semantic review. Keep rationales brief and specific.
Original declared qualities and their makes/breaks contributions are semantic
evidence alongside task labels. A generic task label can implement a specific
quality through those existing effects. For compassion, an explicit empathetic
or caring assistance quality, linked to the same beneficiary's alternatives by
makes/breaks, can establish a design-level care difference without asserting
actual current distress. A generic help label alone is insufficient.
Do not require unstated current awareness, perceived disorder, current emotion,
resource amounts or deadlines for a dispositional branch. Do not invent any
event, current state, permission, promise, effect, node or hard constraint.
Existing hard constraints and explicit contrary model/persona facts prevail.
Quote personality evidence verbatim from persona.description. A selected facet
alone is insufficient. The quoted words must describe this person's actual
trait or customary disposition; job titles, organization names, object mentions
and descriptions of other people do not establish that trait. Quote model
evidence verbatim from one original node
label, description or meaning field. Keep node_id+quote; never concatenate
different fields or paraphrase their text into a quotation.
Review EVERY supplied OR/optional/temporal decision, including not_applicable.
For EVERY selected rule allowed at that decision, fill rule_reviews using its
own fixed semantic outcome. Use no_strict_difference when both implementations
offer that same outcome. Proposals require source_effect=present and
target_effect=absent for one identical outcome_id; unknown is not a strict
difference. For optional/temporal proposals these refer to the preferred and
other complete executions, respectively, not whether the x node executes.
Thus a never preference can have the favored outcome present in the omission
execution and absent when the optional activity is performed. For a quality
criterion, positive polarity means satisfying that quality realizes the chosen
rule outcome; negative polarity means avoiding that quality's modeled effect
realizes it. Use negative only when the rule actually favors that avoidance.
A different facet's benefit cannot
substitute for this rule's outcome. Original quality bindings must identify
that exact rule_id::outcome_id, remain in the compared business scope and agree
with its original contribution effects. Do not replace an explicitly modeled
matching quality distinction with a general intuition about ordinary tasks.
In quality_bindings, map each original quality only to rule outcomes that its
declared meaning actually measures; leave unrelated qualities unmapped.
For Intellectual Curiosity, explanatory understanding and independent new
unanswered-question generation are distinct outcomes. Turn-taking and asking
questions in conversation do not by themselves establish new-question output.
When both channels provide the same explanation, interactivity alone creates
no strict curiosity preference, although another facet may distinguish them.
The catalogue may authorize narrow canonical action grammars. Their derived
bindings are not defeated by a general claim that an unrelated audit quality
is not personality. They remain subject to literal persona counterevidence:
use canonical_persona_exceptions only for an explicitly contrary preference or
standard in persona.description, quoting that statement exactly. A general
trait description is not an exception. Original equal indexed/structured
effects in both implementations also defeat a strict canonical contrast.
For each applicable selected rule emit exactly one support per directed relation;
different applicable facets may support the same relation. Do not omit an
applicable branch merely because another facet already supports its relation.
Choice source and target are original direct OR children: if a child is a goal,
the comparison concerns its complete existing implementation subtree. Select
the direction from the branch semantics and original labels/effects; do not
compare two mandatory AND siblings as a choice. Optional participation names
the full existing optional scope, never only a required leaf inside that scope.
Decision ownership differs from execution ownership. The owner of an original
OR goal chooses its direct implementation, and the owner of an optional work
unit chooses whether that complete unit participates. Its third-party review
and other-role execution tasks keep their original owners and hard constraints.
Do not discard that decision because an independent reviewer executes a required
descendant. Do not transfer another role's nested OR decisions to this persona.
An optional-scope preference requires the rule's favored semantic effect in
EVERY feasible implementation of that scope. Review every nested OR child in
semantic_coverage. If any implementation lacks the effect, mark it unsupported
and do not propose the parent's participation. An internal OR preference may
still be applicable. An optional activity containing both reciprocal discussion
and solitary reading does not as a whole guarantee social contact.
For never, apply this universal test to the modeled contrasted activity being
avoided: all admitted implementations must exhibit the relevant extra effect,
and omission must realize the favored outcome while retaining necessary work.
For a semantic_coverage entry, evidence may come from the selected branch or
from a mandatory AND sibling that runs in every realization under that branch.
An unselected OR sibling or a nested optional activity is not guaranteed proof.
Responsibility needs a model-explicit promised/committed activity. A general
preference for keeping promises does not make every optional task promised.
Productiveness ordering needs model-explicit started/remaining work and a
deferrable nonurgent diversion. Ordinary AND structure creates no soft order.
Curiosity can support extra explanation or new questions, aesthetics genuine
artistic exposure, and imagination optional idea generation with an existing
independent review; none creates authorization to adopt an implementation.
Do not infer reciprocal communication merely from remote execution. Depression
does not imply a current symptom, and volatility does not create provocation or
anger. Apply every branch's own semantic boundaries. Preserve unknowns.
For each proposal cite all model labels needed to establish its semantic fit,
including relevant descendant tasks and qualities. Rationale explains semantic
binding, not new facts. Return only the exact typed schema.
"""


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':')).encode('utf-8')).hexdigest()


def load_semantic_catalogue():
    value = json.loads(CATALOGUE.read_text(encoding='utf-8'))
    rows = value.get('model_semantic_rules')
    if not isinstance(rows, list) or not rows:
        raise ModelError('The model-semantic pattern catalogue is unavailable.')
    ids = [row['id'] for row in rows]
    if len(ids) != len(set(ids)):
        raise ModelError('Model-semantic pattern IDs must be unique.')
    return value


def decision_authorized(model, role, decision, endpoint=None):
    """Check who chooses a work unit, without reassigning its execution.

    An OR goal's owner chooses its direct implementation. The owner of an
    optional goal/task chooses whether that complete unit participates. Existing
    reviewers, other-role tasks and every hard constraint remain in its subtree.
    Ownership of an ancestor does not grant another role's nested OR decisions.
    Temporal control retains the stricter execution-scope check.
    """
    view = _ModelView(model)
    scope = decision['node_id']
    kind = decision['kind']
    if kind in ('choice', 'optional_participation'):
        node = model['nodes'][scope]
        if node.get('role') == role:
            return endpoint is None or endpoint in decision['endpoints']
        scopes = deepcopy(model.get('role_discretion', {}).get(role, []))
        if isinstance(scopes, str): scopes = [scopes]
        meta = model.get('roles', {}).get(role)
        extra = meta.get('discretion', meta.get('discretion_scopes', [])) if isinstance(meta, dict) else []
        scopes += [extra] if isinstance(extra, str) else extra
        candidates = [endpoint] if endpoint is not None else decision['endpoints']
        if all(any(item in model['nodes'] and view.leaves(candidate) <= view.leaves(item)
                   for item in scopes) for candidate in candidates):
            return True
        if node.get('role'):
            # Performing another owner's work does not transfer its choice.
            return False
    candidates = [endpoint] if endpoint is not None else decision['endpoints']
    return all(view.authorized(role, item) for item in candidates)


def decision_space(model, role):
    view = _ModelView(model)
    output = {}
    for ref in model.get('refinements', []):
        if ref['kind'] == 'OR' and model['nodes'][ref['parent']]['kind'] == 'goal':
            children = ref['children']
            candidate = {'kind': 'choice', 'node_id': ref['parent'], 'endpoints': list(children)}
            if len(children) > 1 and decision_authorized(model, role, candidate):
                output['or:' + ref['parent']] = candidate
    for identity, node in model['nodes'].items():
        candidate = {'kind': 'optional_participation', 'node_id': identity, 'endpoints': [identity]}
        if (node['kind'] in ('goal', 'task') and node.get('optional')
                and decision_authorized(model, role, candidate)):
            output['optional:' + identity] = candidate
    started = [identity for identity, node in model['nodes'].items()
               if node['kind'] in ('goal', 'task')
               and re.search(r'\b(started|in.progress|under.way|remaining)\b', node.get('label', ''), re.I)]
    if started:
        endpoints = [identity for identity, node in model['nodes'].items()
                     if node['kind'] in ('goal', 'task') and view.authorized(role, identity)]
        if len(endpoints) > 1:
            output['temporal:' + role] = {'kind': 'temporal', 'node_id': model['root'],
                'endpoints': endpoints}
    return output


def canonical_continuation_endpoint(model, source, target):
    """Normalize a started container to an equivalent remaining work unit.

    Equivalence is proved only when there is one explicitly remaining unit and
    every other task in the source container is already a hard prerequisite of
    the diversion. Thus completion-before-diversion has the same truth for the
    container and that remaining unit; no task order is added to the model.
    """
    if model['nodes'][source]['kind'] != 'goal' or model['nodes'][target]['kind'] != 'task':
        return source, None
    view = _ModelView(model); region = business_region(model, source)
    candidates = [k for k in region if k != source and re.search(r'\bremaining\b', model['nodes'][k]['label'], re.I)]
    candidates = [k for k in candidates if not any(a != k and a in candidates for a in view.ancestor_chain(k))]
    if len(candidates) != 1: return source, None
    unit = candidates[0]; other = set(view.leaves(source)) - set(view.leaves(unit))
    incoming = {}; paths = {}
    def active_business(node):
        if node == target: return True  # Both temporal witnesses include it.
        return (model['nodes'][node]['kind'] in ('goal', 'task')
                and not model['nodes'][node].get('optional')
                and not any(model['nodes'][p].get('optional') for p in view.ancestor_chain(node)))
    def add_predecessor(src, dst, index):
        if active_business(src) and active_business(dst):
            incoming.setdefault(dst, set()).add(src); paths[(src, dst)] = index
    for i, edge in enumerate(model.get('hard_constraints', [])):
        if edge['type'] != 'pre': continue
        # Preserve an unconditional original goal-level pre chain. Replacing
        # an OR-source goal by the intersection of its task alternatives loses
        # that every legal realization still obeys the original pre relation.
        if all(model['nodes'][edge[k]]['kind'] in ('goal', 'task') for k in ('source', 'target')):
            add_predecessor(edge['source'], edge['target'], i)
        mandatory_sources = [k for k in guaranteed_implementation_nodes(model, edge['source'], edge['source'])
                             if model['nodes'][k]['kind'] == 'task']
        for dst in view.leaves(edge['target']):
            for src in mandatory_sources:
                add_predecessor(src, dst, i)
    before = set(); pending = [target]; proof_paths = {target: []}
    while pending:
        node = pending.pop()
        for predecessor in incoming.get(node, set()):
            if predecessor not in before:
                before.add(predecessor); pending.append(predecessor)
                proof_paths[predecessor] = [paths[(predecessor, node)]] + proof_paths[node]
    if not other <= before: return source, None
    return unit, {'kind': 'original_remaining_unit_completion_equivalence',
        'original_source': source, 'canonical_source': unit, 'target': target,
        'other_container_tasks': sorted(other), 'original_predecessors_of_diversion': sorted(before),
        'original_pre_edge_indices': sorted({i for node in other for i in proof_paths[node]}),
        'source_quotes': [{'node_id': k, 'quote': model['nodes'][k]['label']} for k in (source, unit)],
        'claim': 'All other container tasks precede the diversion by original pre constraints; container and remaining-unit completion order are equivalent.'}


def literal_model_quote(model, node_id, quote):
    """One nonempty exact original semantic-field fragment at the cited ID."""
    if not isinstance(node_id, str) or node_id not in model['nodes'] or not isinstance(quote, str) or not quote.strip():
        return False
    return any(isinstance(model['nodes'][node_id].get(field), str)
               and quote in model['nodes'][node_id][field]
               for field in ('label', 'description', 'meaning'))


def _object(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties),
            'additionalProperties': False}


def _enum(values):
    return {'type': 'string', 'enum': sorted(set(values))}


def optional_implementation_nodes(model, scope):
    view = _ModelView(model)
    region = view.leaves(scope)
    alternatives = [child for ref in model['refinements']
        if ref['kind'] == 'OR' and view.leaves(ref['parent']) <= region
        for child in ref['children']]
    return sorted(set(alternatives or [scope]))


def business_region(model, scope):
    refs = {row['parent']: row for row in model['refinements']}
    result = set(); pending = [scope]
    while pending:
        node = pending.pop()
        if node not in result:
            result.add(node)
            pending.extend(child for child in refs.get(node, {}).get('children', [])
                           if model['nodes'][child]['kind'] in ('goal', 'task'))
    return result


def guaranteed_implementation_nodes(model, scope, implementation):
    """Must-execute nodes under one OR-child condition inside an adopted scope.

    AND contributes mandatory siblings, OR contributes only its forced child or
    the intersection of its alternatives. Nested optional work is never proof.
    """
    refs = {row['parent']: row for row in model['refinements']}
    parents = {child: row['parent'] for row in refs.values() for child in row['children']
               if model['nodes'][child]['kind'] in ('goal', 'task')}
    if implementation not in business_region(model, scope):
        return set()
    forced = {}; child = implementation
    while child != scope and child in parents:
        parent = parents[child]
        if refs[parent]['kind'] == 'OR': forced[parent] = child
        child = parent
    def must(node, root=False):
        if not root and model['nodes'][node].get('optional'):
            return set()
        output = {node}; ref = refs.get(node)
        if not ref: return output
        if ref['kind'] == 'AND':
            for child in ref['children']:
                output |= must(child)
        elif node in forced:
            output |= must(forced[node])
        else:
            children = [must(child) for child in ref['children']]
            if children: output |= set.intersection(*children)
        return output
    return must(scope, root=True)


def schema_enum_value_count(schema):
    if isinstance(schema, dict):
        return len(schema.get('enum', [])) + sum(schema_enum_value_count(value) for value in schema.values())
    if isinstance(schema, list):
        return sum(schema_enum_value_count(value) for value in schema)
    return 0


def semantic_outcomes(rule):
    return rule.get('semantic_outcomes') or [
        {'id': rule['id'] + '_outcome_' + str(index + 1), 'description': text}
        for index, text in enumerate(rule['preferred_semantics'])]


def _outcome_tags(rules):
    return [rule['id'] + '::' + outcome['id'] for rule in rules.values()
            for outcome in semantic_outcomes(rule)]


def scoped_quality_criterion(model, quality, region):
    """Project original contribution formulas onto one comparison's work.

    This is a local contribution criterion, never a claim that the original
    global quality changes truth. Cross-boundary business sources stay unknown.
    """
    view = _ModelView(model); region = frozenset(region)
    refs = {row['parent']: row for row in model['refinements']}
    used = []; mixed = []; projected_refs = []
    def combine(operator, children):
        return children[0] if len(children) == 1 else {operator: children}
    def visit(node):
        positive = []; negative = []
        for index, edge in enumerate(model.get('contributions', [])):
            if edge['target'] != node: continue
            leaves = view.leaves(edge['source'])
            if not leaves.intersection(region): continue
            if not leaves <= region:
                mixed.append({'index': index, 'edge': deepcopy(edge)}); continue
            used.append({'index': index, 'edge': deepcopy(edge)})
            expression = {'attains': edge['source']}
            (positive if edge['type'] == 'makes' else negative).append(expression)
        ref = refs.get(node)
        if ref:
            children = [visit(child) for child in ref['children']
                        if model['nodes'][child]['kind'] in ('softgoal', 'hard_preference')
                        and (ref['kind'] != 'AND' or not model['nodes'][child].get('optional'))]
            local = [child for child in children if child is not None]
            if local:
                positive.append(combine(ref['kind'].lower(), local))
                projected_refs.append({'parent': node, 'operator': ref['kind'],
                    'local_child_count': len(local), 'original_child_count': len(children)})
        parts = ([combine('or', positive)] if positive else [])
        parts += [{'not': expression} for expression in negative]
        return combine('and', parts) if parts else None
    ast = visit(quality)
    if mixed:
        return {'status': 'unknown_mixed_business_source', 'mixed_sources': mixed,
                'quality_id': quality, 'ast': None}
    if ast is None:
        return {'status': 'no_local_contribution', 'quality_id': quality, 'ast': None}
    result = {'status': 'local_contribution_criterion', 'quality_id': quality,
        'comparison_region': sorted(region), 'ast': ast,
        'original_contributions': used, 'projected_quality_refinements': projected_refs,
        'interpretation': 'Effects contributed by this comparison scope; original global quality is diagnosed separately.'}
    result['signature'] = _hash({'model_hash': model_hash(model), **result})
    return result


def _compact_schema(schema):
    """Share identical identifier/evidence definitions without changing domains."""
    output = _shared_enums(schema)
    fragments = {}
    evidence_shapes = [{'node_id', 'quote'}, {'supported', 'quote'}, {'supported', 'node_id', 'quote'}]
    def collect(value):
        if isinstance(value, dict):
            if value.get('type') == 'object' and set(value.get('properties', {})) in evidence_shapes:
                key = json.dumps(value, sort_keys=True, separators=(',', ':'))
                record = fragments.setdefault(key, {'count': 0, 'definition': deepcopy(value)})
                record['count'] += 1
            for child in value.values(): collect(child)
        elif isinstance(value, list):
            for child in value: collect(child)
    collect(output)
    shared = {key: {'name': 'evidence_' + str(index + 1), **record}
              for index, (key, record) in enumerate((item for item in fragments.items() if item[1]['count'] > 1))}
    def rewrite(value):
        if isinstance(value, dict):
            key = json.dumps(value, sort_keys=True, separators=(',', ':'))
            if key in shared:
                return {'$ref': '#/$defs/' + shared[key]['name']}
            return {key: rewrite(child) for key, child in value.items()}
        if isinstance(value, list): return [rewrite(child) for child in value]
        return value
    output = rewrite(output)
    if shared:
        output.setdefault('$defs', {}).update({record['name']: record['definition'] for record in shared.values()})
    enum_count = schema_enum_value_count(output)
    if enum_count > 1000:
        raise provider.ProviderError(f'The complete semantic schema contains {enum_count} enum values after lossless sharing; the provider limit is 1000.')
    return output


def response_schema(persona, model, decisions, rules, *, _compact=True):
    quote = {'type': 'string'}
    persona_quotes = persona_quotation_domain(persona.get('description', ''))
    persona_quote = _enum(persona_quotes)
    exception_quotes = [item for item in persona_quotes if item.strip()]
    evidence = _object({'node_id': _enum(model['nodes']), 'quote': quote})
    reviews = {}
    qualities = [identity for identity, node in model['nodes'].items()
                 if node['kind'] in ('softgoal', 'hard_preference')]
    for identity, decision in decisions.items():
        applicable = [rule for rule in rules.values() if decision['kind'] in rule['allowed_kinds']]
        if applicable:
            formulas = ['preferred_to'] if decision['kind'] == 'choice' else sorted({formula
                for rule in applicable for formula in rule.get('allowed_formulas', ['sometime'])})
            coverage = optional_implementation_nodes(model, decision['node_id']) if decision['kind'] == 'optional_participation' else []
            item = _object({'rule_id': _enum(rule['id'] for rule in applicable),
                'source': _enum(decision['endpoints']),
                'target': _enum(decision['endpoints']), 'formula': _enum(formulas),
                'model_evidence': {'type': 'array', 'items': evidence},
                'contrast': _object({'outcome_id': _enum(outcome['id'] for rule in applicable
                                                       for outcome in semantic_outcomes(rule)),
                    'source_effect': _enum(['present', 'absent', 'unknown']),
                    'target_effect': _enum(['present', 'absent', 'unknown']),
                    'criterion_quality_id': _enum(['__none__'] + qualities),
                    'criterion_polarity': _enum(['positive', 'negative'])}),
                'semantic_coverage': _object({key: _object({'supported': {'type': 'boolean'},
                    'node_id': _enum(guaranteed_implementation_nodes(model, decision['node_id'], key)),
                    'quote': quote}) for key in coverage}),
                'rationale': quote})
            proposals = {'type': 'array', 'items': item}
        else:
            proposals = {'type': 'array', 'items': _object({}), 'maxItems': 0}
        reviews[identity] = _object({'status': _enum(['proposed', 'not_applicable', 'needs_information']),
            'proposals': proposals, 'reason': quote,
            'rule_reviews': _object({rule['id']: _enum(['proposed', 'no_strict_difference', 'not_applicable', 'unknown'])
                                     for rule in applicable})})
    schema = _object({'facet_evidence': _object({facet: _object({
        'supported': {'type': 'boolean'}, 'quote': persona_quote}) for facet in persona['facets']}),
        'quality_bindings': _object({quality: {'type': 'array', 'items': _enum(_outcome_tags(rules))}
                                    for quality in qualities}),
        'canonical_persona_exceptions': {'type': 'array', 'items': _object({
            'decision_id': _enum(decisions), 'rule_id': _enum(rules), 'quote': _enum(exception_quotes), 'reason': quote})}
            if decisions and rules and exception_quotes else {'type': 'array', 'items': _object({}), 'maxItems': 0},
        'decisions': _object(reviews)})
    return _compact_schema(schema) if _compact else schema


class WitnessSearch:
    """Bounded fresh constructive search, independently checked on normalized M0."""
    def __init__(self, model):
        compilation = compile_model(model)
        self.model = compilation['normalized_model']
        self.original = model
        self.dummies = set(compilation['dummy_tasks'])
        self.refs = {r['parent']: r for r in self.model['refinements']}
        self.parents = {c: r['parent'] for r in self.refs.values() for c in r['children']}
        self.leaves = lru_cache(None)(self._leaves)
        self.cache = {}

    def _leaves(self, identity):
        if self.model['nodes'][identity]['kind'] == 'task':
            return frozenset([identity])
        return frozenset().union(*(self.leaves(c) for c in self.refs.get(identity, {}).get('children', [])))

    def _force(self, identity, choices):
        child = identity
        while child in self.parents:
            parent = self.parents[child]
            if self.refs[parent]['kind'] == 'OR':
                if parent in choices and choices[parent] != child:
                    return False
                choices[parent] = child
            child = parent
        return True

    def _sets(self, identity, choices):
        if self.model['nodes'][identity]['kind'] == 'task':
            yield frozenset([identity]); return
        ref = self.refs[identity]
        if ref['kind'] == 'OR':
            children = [choices[identity]] if identity in choices else sorted(ref['children'],
                key=lambda child: (not child.startswith('__skip_'), ref['children'].index(child)))
            for child in children:
                yield from self._sets(child, choices)
        else:
            def combine(index, selected):
                if index == len(ref['children']):
                    yield selected; return
                for part in self._sets(ref['children'][index], choices):
                    yield from combine(index + 1, selected | part)
            yield from combine(0, frozenset())

    def _schedule(self, selected, order, unrelated_order=()):
        model = self.model
        npr_checks = prepare_npr_forward_checks(model, selected, self.leaves)
        task_order = {identity: index for index, identity in enumerate(model['nodes'])}
        incoming = {}
        for edge in model.get('hard_constraints', []):
            incoming.setdefault(edge['target'], []).append(edge)
        ancestors = {}
        for task in selected:
            values = []; identity = task
            while identity in self.parents:
                identity = self.parents[identity]; values.append(identity)
            ancestors[task] = values
        failed = set(); visited = [0]
        def visit(done, sequence):
            visited[0] += 1
            if visited[0] > 50000 or done in failed:
                return None
            if done == selected:
                check = validate_plan(model, sequence)
                if order:
                    prefixes = [frozenset(sequence[:i]) for i in range(len(sequence) + 1)]
                    tx = next((i for i, state in enumerate(prefixes) if attained(model, order[0], state)), None)
                    ty = next((i for i, state in enumerate(prefixes) if attained(model, order[1], state)), None)
                    if tx is None or ty is None or tx >= ty:
                        return None
                return (sequence, check) if check['valid'] else None
            for task in sorted(selected - done, key=lambda identity: task_order[identity]):
                if task in unrelated_order and not set(unrelated_order[:unrelated_order.index(task)]) <= done:
                    continue
                if (order and attained(model, order[1], done | {task})
                        and not attained(model, order[0], done)):
                    # Preference order concerns attainment, not the first
                    # action of an AND subtree. Other target work may start
                    # earlier while its completion remains after the source.
                    continue
                starts = [task] + [key for key in ancestors[task] if not self.leaves(key).intersection(done)]
                if any(attained(model, edge['source'], done) != (edge['type'] == 'pre')
                       for key in starts for edge in incoming.get(key, [])):
                    continue
                if npr_prefix_impossible(model, done | {task}, npr_checks):
                    continue
                found = visit(done | {task}, sequence + [task])
                if found:
                    return found
            failed.add(done)
            return None
        return visit(frozenset(), [])

    def find(self, *, choice=None, optional=None, order=None, unrelated_order=()):
        key = (choice, optional, order, tuple(unrelated_order))
        if key in self.cache:
            return self.cache[key]
        choices = {}
        valid = True
        if choice:
            parent, child = choice; choices[parent] = child
            valid = self._force(parent, choices)
        if optional:
            identity, include = optional
            wrapper = '__opt_' + identity
            choices[wrapper] = identity if include else '__skip_' + identity
            valid = valid and self._force(wrapper, choices)
        if order:
            valid = valid and all(self._force(identity, choices) for identity in order)
        result = None
        if valid:
            for selected in islice(self._sets(self.model['root'], choices), 2048):
                if not set(unrelated_order) <= selected:
                    continue
                found = self._schedule(selected, order, unrelated_order)
                if found:
                    sequence, checked = found
                    result = {'normalized_sequence': sequence,
                        'sequence': [task for task in sequence if task not in self.dummies],
                        'normalized_validation': checked, 'source': 'fresh-bounded-constructive-search'}
                    break
        self.cache[key] = result
        return result


def _validate_response(response, persona, model, decisions, rules):
    if not isinstance(response, dict) or set(response) != {'facet_evidence', 'quality_bindings', 'canonical_persona_exceptions', 'decisions'}:
        raise provider.ProviderError('Semantic mapping did not return the typed top-level fields.')
    if not isinstance(response['facet_evidence'], dict) or set(response['facet_evidence']) != set(persona['facets']):
        raise provider.ProviderError('Semantic mapping omitted a selected facet review.')
    if not isinstance(response['decisions'], dict) or set(response['decisions']) != set(decisions):
        raise provider.ProviderError('Semantic mapping omitted an existing decision review.')
    qualities = {identity for identity, node in model['nodes'].items()
                 if node['kind'] in ('softgoal', 'hard_preference')}
    bindings = response['quality_bindings']
    if not isinstance(bindings, dict) or set(bindings) != qualities:
        raise provider.ProviderError('Semantic mapping omitted an original quality outcome review.')
    tags = set(_outcome_tags(rules))
    if any(not isinstance(values, list) or any(not isinstance(tag, str) or tag not in tags for tag in values)
           or len(values) != len(set(values)) for values in bindings.values()):
        raise provider.ProviderError('Quality mappings must reference existing rule outcomes uniquely.')
    exceptions = response['canonical_persona_exceptions']
    if not isinstance(exceptions, list) or len(exceptions) > 100:
        raise provider.ProviderError('Canonical exceptions must be a bounded list of literal persona evidence.')
    for exception in exceptions:
        if (not isinstance(exception, dict) or exception.get('decision_id') not in decisions or exception.get('rule_id') not in rules
                or not isinstance(exception.get('quote'), str) or not exception['quote'].strip()
                or exception['quote'] not in persona['description']):
            raise provider.ProviderError('A canonical exception must quote actual contrary persona text.')
    for facet, record in response['facet_evidence'].items():
        if not isinstance(record, dict) or type(record.get('supported')) is not bool or not isinstance(record.get('quote'), str):
            raise provider.ProviderError('Semantic mapping returned malformed persona evidence.')
        if record['supported'] and (not record['quote'].strip() or record['quote'] not in persona['description']):
            raise provider.ProviderError('Personality evidence is not a literal supplied persona quotation.')
        if record['supported'] and not any(
                rule.get('facet') == facet and persona_quote_evidence(persona, rule, record['quote']).get('supported') is True
                for rule in rules.values()):
            raise provider.ProviderError('Personality quotation does not establish the cited persona facet.')
    for identity, record in response['decisions'].items():
        if (not isinstance(record, dict) or record.get('status') not in ('proposed', 'not_applicable', 'needs_information')
                or not isinstance(record.get('proposals'), list) or len(record['proposals']) > 100):
            raise provider.ProviderError('Semantic mapping returned a malformed decision review.')
        if (record['status'] == 'proposed') != bool(record['proposals']):
            raise provider.ProviderError('Decision status disagrees with its actual proposals.')
        expected_rules = {rule['id'] for rule in rules.values() if decisions[identity]['kind'] in rule['allowed_kinds']}
        matrix = record.get('rule_reviews')
        if not isinstance(matrix, dict) or set(matrix) != expected_rules or any(
                status not in ('proposed', 'no_strict_difference', 'not_applicable', 'unknown') for status in matrix.values()):
            raise provider.ProviderError('Semantic mapping omitted the closed rule-by-decision review matrix.')
        proposed = {proposal.get('rule_id') for proposal in record['proposals'] if isinstance(proposal, dict)}
        if proposed != {rule for rule, status in matrix.items() if status == 'proposed'}:
            raise provider.ProviderError('Rule review status disagrees with its actual supports.')
    return response


def reconcile_bookkeeping(response, decisions, rules):
    """Repair report labels only; never create or change a proposed binding."""
    output = deepcopy(response); repairs = []
    if not isinstance(output, dict) or not isinstance(output.get('decisions'), dict):
        return output, repairs
    def change(record, field, value, path, reason):
        if record.get(field) != value:
            repairs.append({'path': path, 'previous': record.get(field), 'current': value, 'reason': reason})
            record[field] = value
    for identity, record in output['decisions'].items():
        if identity not in decisions or not isinstance(record, dict) or not isinstance(record.get('proposals'), list): continue
        matrix = record.get('rule_reviews')
        if not isinstance(matrix, dict): continue
        actual = {proposal.get('rule_id') for proposal in record['proposals'] if isinstance(proposal, dict)}
        for rule in matrix:
            if rule in actual:
                change(matrix, rule, 'proposed', f'{identity}.rule_reviews.{rule}', 'Actual proposal is present.')
            elif matrix[rule] == 'proposed':
                change(matrix, rule, 'unknown', f'{identity}.rule_reviews.{rule}', 'Reported support has no actual binding; no candidate was invented.')
        status = ('proposed' if record['proposals'] else 'needs_information'
                  if 'unknown' in matrix.values() or record.get('status') == 'needs_information' else 'not_applicable')
        change(record, 'status', status, f'{identity}.status', 'Decision report derives from actual proposals and unresolved rule reviews.')
    return output, repairs


def _request_semantic_stage(stage, instruction, packet, schema, calls):
    stage_started = time.monotonic()
    for attempt in range(1, SEMANTIC_TRANSPORT_RETRIES + 2):
        started = time.monotonic()
        try:
            response, metadata = provider.request_json(instruction, packet,
                max_tokens=SEMANTIC_MAX_TOKENS, response_schema=schema)
        except provider.ProviderError as exc:
            delay = min(SEMANTIC_RETRY_BACKOFF_CAP_SECONDS,
                        SEMANTIC_RETRY_BACKOFF_SECONDS * 2 ** (attempt - 1))
            # Only schedule another physical call while the stage's retry
            # budget permits its backoff. An already running provider request
            # retains its configured timeout and is never extended/interrupted.
            retry = (exc.retryable and attempt <= SEMANTIC_TRANSPORT_RETRIES
                     and time.monotonic() - stage_started + delay <= SEMANTIC_RETRY_BUDGET_SECONDS)
            backoff = delay if retry else 0
            calls.append({'stage': stage, 'attempt': attempt, 'status': 'error',
                'payload': deepcopy(packet), 'error': str(exc), 'retryable': exc.retryable,
                'options': {'max_tokens': SEMANTIC_MAX_TOKENS, 'response_schema': deepcopy(schema)},
                'retry_scheduled': retry, 'backoff_seconds': backoff,
                'elapsed_seconds': time.monotonic() - started})
            if not retry: raise
            time.sleep(backoff)
        else:
            calls.append({'stage': stage, 'attempt': attempt, 'status': 'success',
                'payload': deepcopy(packet), 'response': deepcopy(response), 'provider': metadata,
                'options': {'max_tokens': SEMANTIC_MAX_TOKENS, 'response_schema': deepcopy(schema)},
                'elapsed_seconds': time.monotonic() - started})
            return response


def compile_contact_quality_bindings(model, persona, decisions, rules):
    search = WitnessSearch(model); view = _ModelView(model); output = []; seen = set()
    for rule in rules.values():
        guard = rule.get('required_semantic_evidence', {})
        if guard.get('grammar') != 'reciprocal_contact_v1' or not guard.get('allow_canonical_from_explicit_quality_contribution'):
            continue
        outcome = guard.get('outcome_id', semantic_outcomes(rule)[0]['id'])
        for identity, decision in decisions.items():
            if decision['kind'] != 'choice': continue
            for source in decision['endpoints']:
                for target in decision['endpoints']:
                    key = (identity, source, target, rule['id'])
                    if source == target or key in seen: continue
                    if direct_contact_evidence(model, target, guard, guaranteed_implementation_nodes): continue
                    region = view.leaves(source) | view.leaves(target)
                    a = search.find(choice=(decision['node_id'], source))
                    if not a: continue
                    outside = tuple(task for task in a['sequence'] if task not in region)
                    b = search.find(choice=(decision['node_id'], target), unrelated_order=outside)
                    if not b or tuple(task for task in b['sequence'] if task not in region) != outside: continue
                    for quality, node in model['nodes'].items():
                        if node['kind'] not in ('softgoal', 'hard_preference') or not contact_quality_matches(node['label'], guard): continue
                        criterion = scoped_quality_criterion(model, quality, region)
                        if criterion['status'] != 'local_contribution_criterion': continue
                        va = evaluate_concern(search.model, a['normalized_sequence'], criterion['ast'])
                        vb = evaluate_concern(search.model, b['normalized_sequence'], criterion['ast'])
                        if va is not True or vb is not False: continue
                        evidence_nodes = [source, target, quality] + [row['edge']['source'] for row in criterion['original_contributions']]
                        proposal = {'rule_id': rule['id'], 'source': source, 'target': target, 'formula': 'preferred_to',
                            'model_evidence': [{'node_id': item, 'quote': model['nodes'][item]['label']} for item in dict.fromkeys(evidence_nodes)],
                            'semantic_coverage': {}, 'contrast': {'outcome_id': outcome, 'source_effect': 'present', 'target_effect': 'absent',
                                'criterion_quality_id': quality, 'criterion_polarity': 'positive'},
                            'rationale': guard.get('description', 'Original reciprocal-contact quality contributions distinguish this existing OR implementation.')}
                        output.append({'decision_id': identity, 'proposal': proposal,
                            'origin': 'catalogue_canonical_quality_compiler', 'anchor_id': 'reciprocal_contact_quality_v1',
                            'grammar': 'reciprocal_contact_quality_v1', 'quality_id': quality,
                            'criterion': criterion, 'local_effects': {'preferred': va, 'other': vb},
                            'original_global_quality_values': {'preferred': a['normalized_validation']['qualities'][quality],
                                                               'other': b['normalized_validation']['qualities'][quality]},
                            'certified_witness_pair': {'preferred': a, 'other': b}})
                        seen.add(key); break
    return output


def compile_contact_task_bindings(model, persona, decisions, rules):
    """Certify an original contact-versus-document choice, never a lone head.

    Positive contact must be guaranteed in the source scope. Every admitted
    task in the other scope must be explicitly solitary document reading.
    Original contact-quality effects remain counterevidence, and the pair
    retains all unrelated work and the original hard business constraints.
    """
    search = WitnessSearch(model); view = _ModelView(model); output = []
    for rule in rules.values():
        guard = rule.get('required_semantic_evidence', {})
        if (guard.get('grammar') != 'reciprocal_contact_v1'
                or not guard.get('allow_canonical_from_certified_task_contrast')):
            continue
        for identity, decision in decisions.items():
            if decision['kind'] != 'choice': continue
            for source in decision['endpoints']:
                positive = direct_contact_evidence(model, source, guard, guaranteed_implementation_nodes)
                if not positive: continue
                for target in decision['endpoints']:
                    if source == target: continue
                    negative = direct_solitary_evidence(model, target, guard)
                    if not negative: continue
                    region = view.leaves(source) | view.leaves(target)
                    a = search.find(choice=(decision['node_id'], source))
                    if not a: continue
                    outside = tuple(task for task in a['sequence'] if task not in region)
                    b = search.find(choice=(decision['node_id'], target), unrelated_order=outside)
                    if not b: continue
                    counterevidence = []
                    for quality, node in model['nodes'].items():
                        if node['kind'] not in ('softgoal', 'hard_preference') or not contact_quality_matches(node['label'], guard): continue
                        criterion = scoped_quality_criterion(model, quality, region)
                        if criterion['status'] == 'unknown_mixed_business_source':
                            counterevidence.append(quality); continue
                        if criterion['status'] != 'local_contribution_criterion': continue
                        local_source = evaluate_concern(search.model, a['normalized_sequence'], criterion['ast'])
                        active_source_break = any(row['edge']['type'] == 'breaks'
                            and evaluate_concern(search.model, a['normalized_sequence'], {'attains': row['edge']['source']}) is True
                            for row in criterion['original_contributions'])
                        # A potentially positive original target effect is not
                        # absence merely because one witness omits its source.
                        target_leaves = view.leaves(target)
                        if ((local_source is False and active_source_break)
                                or evaluate_concern(search.model, b['normalized_sequence'], criterion['ast']) is True
                                or any(row['edge']['type'] == 'makes'
                                       and view.leaves(row['edge']['source']) <= target_leaves
                                       for row in criterion['original_contributions'])):
                            counterevidence.append(quality)
                    if counterevidence: continue
                    ids = list(dict.fromkeys([source, target] + [p['node_id'] for p in positive + negative]))
                    outcome = guard.get('outcome_id', semantic_outcomes(rule)[0]['id'])
                    proposal = {'rule_id': rule['id'], 'source': source, 'target': target, 'formula': 'preferred_to',
                        'model_evidence': [{'node_id': k, 'quote': model['nodes'][k]['label']} for k in ids],
                        'semantic_coverage': {}, 'contrast': {'outcome_id': outcome, 'source_effect': 'present',
                            'target_effect': 'absent', 'criterion_quality_id': '__none__', 'criterion_polarity': 'positive'},
                        'rationale': 'Original guaranteed reciprocal contact contrasts with exclusively solitary written-artifact tasks.'}
                    output.append({'decision_id': identity, 'proposal': proposal,
                        'origin': 'catalogue_certified_task_contrast_compiler',
                        'anchor_id': 'reciprocal_contact_vs_solitary_artifact_v1',
                        'grammar': 'reciprocal_contact_vs_solitary_artifact_v1',
                        'source_evidence': positive, 'target_absence_evidence': negative,
                        'certified_witness_pair': {'preferred': a, 'other': b}})
    return output


def _accept(response, persona, model, decisions, rules):
    view = _ModelView(model); search = WitnessSearch(model)
    relations = {}; supports = {}; findings = []
    context_id = 'D_' + _hash({'persona': persona, 'model': model})[:16]
    for decision_id, review in response['decisions'].items():
        decision = decisions[decision_id]
        for proposal in review['proposals']:
            finding = {'decision_id': decision_id, 'proposal': deepcopy(proposal)}
            temporal_normalization = None
            if (decision['kind'] == 'temporal' and isinstance(proposal, dict)
                    and proposal.get('source') in model['nodes'] and proposal.get('target') in model['nodes']):
                normalized, temporal_normalization = canonical_continuation_endpoint(model, proposal['source'], proposal['target'])
                if temporal_normalization:
                    proposal = deepcopy(proposal); proposal['source'] = normalized
                    proposal.setdefault('model_evidence', []).append({'node_id': normalized, 'quote': model['nodes'][normalized]['label']})
                    finding['temporal_endpoint_normalization'] = temporal_normalization
            def reject(reason):
                finding.update(status='rejected', reason=reason); findings.append(finding)
            if not isinstance(proposal, dict) or proposal.get('rule_id') not in rules:
                reject('Unknown semantic pattern branch.'); continue
            rule = rules[proposal['rule_id']]; facet = rule['facet']
            if not response['facet_evidence'][facet]['supported']:
                reject('Independent persona evidence is absent.'); continue
            if not persona_quote_evidence(persona, rule, response['facet_evidence'][facet].get('quote')).get('supported'):
                reject('The literal persona quotation does not establish this facet.'); continue
            kind = decision['kind']; source = proposal.get('source'); target = proposal.get('target')
            formula = proposal.get('formula')
            contrast = proposal.get('contrast')
            if (not isinstance(contrast, dict) or contrast.get('outcome_id') not in {row['id'] for row in semantic_outcomes(rule)}
                    or contrast.get('source_effect') != 'present' or contrast.get('target_effect') != 'absent'):
                reject('A strict preference requires present-versus-absent effects on one identical rule outcome.'); continue
            quality = contrast.get('criterion_quality_id')
            polarity = contrast.get('criterion_polarity')
            if polarity not in ('positive', 'negative'):
                reject('A quality criterion requires an explicit positive or negative outcome polarity.'); continue
            if quality != '__none__':
                tag = rule['id'] + '::' + contrast['outcome_id']
                if (quality not in model['nodes'] or model['nodes'][quality]['kind'] not in ('softgoal', 'hard_preference')
                        or tag not in response.get('quality_bindings', {}).get(quality, [])):
                    reject('The selected quality is not mapped to this exact rule outcome.'); continue
            if kind not in rule['allowed_kinds'] or source not in decision['endpoints'] or target not in decision['endpoints']:
                reject('Pattern kind or existing decision endpoints do not match.'); continue
            if not all(decision_authorized(model, persona['role_ids'][0], decision, node)
                       for node in (source, target)):
                reject('The selected role lacks model-declared discretion.'); continue
            authority = {'active_role': persona['role_ids'][0], 'decision_node': decision['node_id'],
                'decision_owner': model['nodes'][decision['node_id']].get('role'),
                'kind': decision['kind'], 'execution_roles_preserved': {
                    node: model['nodes'][node].get('role')
                    for node in sorted(view.leaves(source) | view.leaves(target))},
                'policy': 'Original decision ownership or explicit coordination grants selection only; execution ownership is unchanged.'}
            citations = proposal.get('model_evidence')
            if not isinstance(citations, list) or not citations or any(not isinstance(item, dict)
                    or not literal_model_quote(model, item.get('node_id'), item.get('quote'))
                    for item in citations):
                reject('Model evidence must quote one original node label, description or meaning field literally.'); continue
            cited = {item['node_id'] for item in citations}
            source_region = business_region(model, source)
            target_region = business_region(model, target)
            if not cited.intersection(source_region) or kind == 'choice' and not cited.intersection(target_region):
                reject('The evidence does not cover the compared implementation subtrees.'); continue
            promise_region = source_region | {edge['target'] for edge in model.get('contributions', [])
                if edge['type'] == 'makes' and edge['source'] in source_region and edge['target'] in cited}
            if rule['id'] == 'MS-RES-01' and not any(re.search(r'\b(promis\w*|commit\w*)\b',
                    model['nodes'][node]['label'], re.I) for node in promise_region):
                reject('The original activity does not explicitly carry a promise or commitment.'); continue
            if kind == 'choice':
                if formula != 'preferred_to' or source == target:
                    reject('A choice needs two distinct OR alternatives.'); continue
                a = search.find(choice=(decision['node_id'], source))
                b = search.find(choice=(decision['node_id'], target))
                core = {'kind': kind, 'type': 'preferred_to', 'source': source, 'target': target}
                region = view.leaves(source) | view.leaves(target)
            elif kind == 'optional_participation':
                if source != decision['node_id'] or target != source or formula not in rule.get('allowed_formulas', ['sometime']):
                    reject('Optional participation must retain its whole canonical scope and formula.'); continue
                coverage = proposal.get('semantic_coverage', {})
                expected_coverage = optional_implementation_nodes(model, source)
                if not isinstance(coverage, dict) or set(coverage) != set(expected_coverage):
                    reject('Optional participation omitted implementation-wide semantic coverage.'); continue
                invalid_coverage = False
                for implementation, record in coverage.items():
                    node = record.get('node_id') if isinstance(record, dict) else None
                    if (not isinstance(record, dict) or record.get('supported') is not True
                            or not literal_model_quote(model, node, record.get('quote'))
                            or node not in guaranteed_implementation_nodes(model, source, implementation)):
                        invalid_coverage = True; break
                if invalid_coverage:
                    reject('The preferred semantic effect is not supported for every optional implementation.'); continue
                include = formula == 'sometime'
                a = search.find(optional=(source, include)); b = search.find(optional=(source, not include))
                core = {'kind': kind, 'type': formula, 'formula': formula, 'x': source, 'y': None}
                region = view.leaves(source)
            else:
                source_context = source_region | {node for node in view.ancestor_chain(source)
                    if not view.leaves(target) <= view.leaves(node)}
                source_labels = ' '.join(model['nodes'][node]['label'] for node in source_context)
                target_labels = ' '.join(model['nodes'][node]['label'] for node in target_region)
                if (formula != 'precedes' or source == target
                        or not re.search(r'\b(started|remaining|in.progress|under.way)\b', source_labels, re.I)
                        or not re.search(r'\b(nonurgent|non.urgent|deferr\w*|diversion|distraction)\b', target_labels, re.I)):
                    reject('Temporal preferences need explicit started/remaining work semantics.'); continue
                a = search.find(order=(source, target)); b = search.find(order=(target, source))
                core = {'kind': kind, 'type': formula, 'formula': formula, 'x': source, 'y': target}
                region = frozenset()
            if not a or not b:
                reject('Fresh bounded search found no complete feasible witness pair.'); continue
            if kind != 'temporal':
                outside = tuple(task for task in a['sequence'] if task not in region)
                if outside != tuple(task for task in b['sequence'] if task not in region):
                    if kind == 'choice':
                        b = search.find(choice=(decision['node_id'], target), unrelated_order=outside)
                    else:
                        b = search.find(optional=(source, not include), unrelated_order=outside)
                    if not b:
                        reject('No feasible comparison preserves the same unrelated business order.'); continue
            quality_check = None
            if quality != '__none__':
                comparison_region = set(view.leaves(source)) | set(view.leaves(target))
                criterion = scoped_quality_criterion(model, quality, comparison_region)
                if criterion['status'] == 'unknown_mixed_business_source':
                    reject('A mixed original contribution source crosses the comparison scope and cannot be truncated.'); continue
                if criterion['ast'] is None:
                    reject('The criterion quality has no original contribution in this comparison scope.'); continue
                local_a = evaluate_concern(search.model, a['normalized_sequence'], criterion['ast'])
                local_b = evaluate_concern(search.model, b['normalized_sequence'], criterion['ast'])
                desired_quality = polarity == 'positive'
                if local_a is not desired_quality or local_b is not (not desired_quality):
                    reject('The scoped quality has no true-versus-false effect in the original-contribution criterion.'); continue
                quality_check = {'criterion': criterion,
                    'local_effects': {'preferred': local_a, 'other': local_b},
                    'original_global_quality_values': {
                        'preferred': a['normalized_validation']['qualities'].get(quality),
                        'other': b['normalized_validation']['qualities'].get(quality)},
                    'outcome_polarity': polarity}
            semantic_contract = check_semantic_contract(model, persona, rule, decision, proposal,
                witness_pair={'preferred': a, 'other': b}, quality_check=quality_check)
            if not semantic_contract['supported']:
                finding['semantic_contract'] = semantic_contract
                finding['resolved_inapplicable'] = semantic_contract['status'] == 'contradicted'
                reject('Original-model semantic contract: ' + semantic_contract['reason']); continue
            semantic_guard = None
            guard = rule.get('required_semantic_evidence', {})
            if guard.get('grammar') == 'reciprocal_contact_v1':
                expected_outcome = guard.get('outcome_id', semantic_outcomes(rule)[0]['id'])
                if contrast['outcome_id'] != expected_outcome:
                    reject('The necessary contact evidence is bound to a different rule outcome.'); continue
                direct_source = direct_contact_evidence(model, source, guard, guaranteed_implementation_nodes)
                direct_target = direct_contact_evidence(model, target, guard, guaranteed_implementation_nodes) if kind == 'choice' else []
                source_contact = bool(direct_source); other_contact = bool(direct_target); quality_proofs = []
                source_contact_break = False
                for qid, node in model['nodes'].items():
                    if node['kind'] not in ('softgoal', 'hard_preference') or not contact_quality_matches(node['label'], guard): continue
                    local = scoped_quality_criterion(model, qid, set(view.leaves(source)) | set(view.leaves(target)))
                    if local['status'] != 'local_contribution_criterion': continue
                    va = evaluate_concern(search.model, a['normalized_sequence'], local['ast'])
                    vb = evaluate_concern(search.model, b['normalized_sequence'], local['ast'])
                    source_contact_break |= va is False and any(row['edge']['type'] == 'breaks'
                        and evaluate_concern(search.model, a['normalized_sequence'], {'attains': row['edge']['source']}) is True
                        for row in local['original_contributions'])
                    source_contact |= va is True; other_contact |= vb is True
                    quality_proofs.append({'quality_id': qid, 'criterion': local,
                        'local_effects': {'preferred': va, 'other': vb},
                        'original_global_quality_values': {'preferred': a['normalized_validation']['qualities'][qid],
                                                           'other': b['normalized_validation']['qualities'][qid]}})
                if source_contact_break:
                    reject('An active original scoped reciprocal-contact break defeats the direct positive task claim.'); continue
                if not source_contact:
                    reject('Reciprocal contact requires an actual communication action or an original scoped communication-quality effect; joint action alone is insufficient.'); continue
                if other_contact:
                    reject('Both compared implementations already provide reciprocal contact on this rule outcome.'); continue
                semantic_guard = {'grammar': guard['grammar'], 'rule_outcome': rule['id'] + '::' + expected_outcome,
                    'direct_source_evidence': direct_source, 'direct_target_evidence': direct_target,
                    'quality_evidence': quality_proofs}
            if rule['id'] == 'MS-CI-01':
                generators = [node for node in source_region if model['nodes'][node]['kind'] == 'task'
                    and re.search(r'\b(generat\w*|imagin\w*|brainstorm\w*|creat\w*)\b', model['nodes'][node]['label'], re.I)]
                reviewers = [node for node, item in model['nodes'].items() if node in source_region and item['kind'] == 'task'
                    and re.search(r'\breview\w*\b', item['label'], re.I)
                    and item.get('role') and item['role'] != persona['role_ids'][0]]
                if not any(generator in a['sequence'] and reviewer in a['sequence']
                        and a['sequence'].index(generator) < a['sequence'].index(reviewer)
                        for generator in generators for reviewer in reviewers):
                    reject('Creative generation lacks a selected existing independent review after generation.'); continue
            if kind == 'temporal':
                if set(a['sequence']) != set(b['sequence']):
                    reject('A temporal comparison must retain the same selected activities.'); continue
            elif [task for task in a['sequence'] if task not in region] != [task for task in b['sequence'] if task not in region]:
                reject('The witness comparison changes unrelated business work.'); continue
            core.update(actor_id=persona['actor_id'], role_id=persona['role_ids'][0], context_id=context_id)
            rid = 'R_' + _hash(core)[:20]
            relation = relations.setdefault(rid, {'id': rid, **core, 'support_ids': [],
                'pattern_ids': [], 'rule_ids': [], 'facets': []})
            sid = 'S_' + _hash({'relation': rid, 'rule': rule['id']})[:20]
            support = {'id': sid, 'relation_id': rid, 'pattern_id': rule['pattern_id'],
                'rule_id': rule['id'], 'facet': facet, 'persona_evidence': deepcopy(response['facet_evidence'][facet]),
                'model_evidence': deepcopy(citations), 'rationale': proposal.get('rationale', ''),
                'decision_authority': authority,
                'temporal_endpoint_normalization': temporal_normalization,
                'semantic_contrast': deepcopy(contrast),
                'semantic_contract': semantic_contract,
                'quality_effect_check': quality_check,
                'required_semantic_evidence': semantic_guard,
                'witness_pairs': [{'preferred': a, 'other': b}],
                'inference_boundary': rule.get('inference_boundary'), 'status': 'design_preference_hypothesis'}
            supports[sid] = support
            for field, value in [('support_ids', sid), ('pattern_ids', rule['pattern_id']),
                                 ('rule_ids', rule['id']), ('facets', facet)]:
                if value not in relation[field]: relation[field].append(value)
            finding.update(status='accepted', relation_id=rid, support_id=sid); findings.append(finding)
    conflicts = []
    values = list(relations.values())
    for relation in values:
        if relation['kind'] in ('choice', 'temporal'):
            left, right = ((relation['source'], relation['target']) if relation['kind'] == 'choice'
                           else (relation['x'], relation['y']))
            graph = {}
            for other in values:
                if other['kind'] == relation['kind']:
                    x, y = ((other['source'], other['target']) if other['kind'] == 'choice'
                            else (other['x'], other['y']))
                    graph.setdefault(x, []).append(y)
            seen = set(); pending = [right]
            while pending:
                node = pending.pop()
                if node == left:
                    conflicts.append({'relation_id': relation['id'], 'reason': 'directed_preference_cycle'}); break
                if node not in seen:
                    seen.add(node); pending.extend(graph.get(node, []))
        elif any(other['kind'] == 'optional_participation' and other['x'] == relation['x']
                 and other['formula'] != relation['formula'] for other in values):
            conflicts.append({'relation_id': relation['id'], 'reason': 'opposed_participation_preferences'})
    return {'relations': values, 'supports': list(supports.values()), 'conflicts': conflicts,
        'decisions': findings, 'base_preserved': True, 'method': METHOD_ID,
        'scope': 'LLM semantic mapping and same-provider semantic review produce qualitative design hypotheses. '
                 'Python checks quotations, original structure, role and bounded fresh feasible witnesses. '
                 'Independent reference correctness is evaluated externally; these are not behavior predictions.'}


def contextualize_workspace(identity, payload):
    if not isinstance(payload, dict):
        raise ModelError('Contextualization input must be an object.')
    unexpected = sorted(set(payload) - {'persona', 'revision', 'material'})
    if unexpected or payload.get('material', '') != '':
        raise ModelError('Three-input modeling accepts persona, revision and empty material compatibility only.')
    value = wb.get_workspace(identity); revision = value['revision']
    if 'revision' in payload and (type(payload['revision']) is not int or payload['revision'] < 1):
        raise ModelError('Workspace revision must be a positive integer.')
    if 'revision' in payload and payload['revision'] != revision:
        raise SessionConflict('This workspace input revision is stale.')
    persona = wb._persona(value, payload)
    value.update(persona=persona, material='', result=None, analysis_session=None, artifacts={})
    catalogue = load_semantic_catalogue()
    model = business_projection(value['base_session']['model']) if value.get('base_session') else None
    contract = {'id': INPUT_ID, 'method': METHOD_ID, 'inputs': ['persona', 'pattern', 'goal_model'],
        'finalization_policy': POLICY_ID,
        'persona_sha256': _hash(persona), 'pattern_sha256': _hash(catalogue),
        'goal_model_sha256': model_hash(model) if model else None,
        'endpoint_policy': 'Direct original OR children; canonical optional scope; original temporal endpoints.',
        'extraction_policy': 'Fresh typed semantic mapping and review; immutable persona description.',
        'processing_policy': {'semantic_stages': 2, 'max_tokens_per_request': SEMANTIC_MAX_TOKENS,
            'transport_retries_per_stage': SEMANTIC_TRANSPORT_RETRIES,
            'retry_backoff_seconds': SEMANTIC_RETRY_BACKOFF_SECONDS,
            'retry_scope': 'ProviderError.retryable only; semantic/schema failures never retried.'}}
    value['artifacts']['input_contract'] = contract
    if model is None:
        value['result'] = failed_model_result(
            'The goal model requires a supported execution projection for preference validation.',
            code='unsupported_goal_model')
        return wb._commit(value, revision)
    validate_model(model)
    if not persona['role_ids'] or not persona['facets'] or len(persona['description'].strip()) < 15:
        value['result'] = failed_model_result(
            'Modeling requires a persona description, selected facets and an existing role.',
            code='invalid_persona_input')
        return wb._commit(value, revision)
    canonical = deepcopy(persona)
    canonical['role_ids'] = [wb._canonical_reference(value, role) for role in persona['role_ids']]
    rules = {row['id']: deepcopy(row) for row in catalogue['model_semantic_rules'] if row['facet'] in persona['facets']}
    decisions = decision_space(model, canonical['role_ids'][0])
    # Empty structural opportunity is decidable from the supplied graph alone.
    # It needs neither an invented persona conclusion nor an empty-schema LLM
    # request. A semantic unknown inside a real decision still uses both stages.
    eligible = {key: item for key, item in decisions.items()
                if any(item['kind'] in row['allowed_kinds'] for row in rules.values())}
    if not eligible:
        checked = {'relations': [], 'supports': [], 'conflicts': [], 'decisions': [],
            'base_preserved': True, 'method': METHOD_ID,
            'scope': 'No original decision is controlled by the active role for the selected pattern kinds.'}
        proof = {'kind': 'no_eligible_original_decision', 'active_role': canonical['role_ids'][0],
            'original_decisions': deepcopy(decisions), 'selected_rules': sorted(rules),
            'goal_model_sha256': model_hash(model), 'emitted_relations': 0}
        contract['processing_policy'].update(semantic_stages_required=0,
            terminal_path='structural_no_op')
        value['analysis_session'] = {'model': model, 'persona': canonical, 'sources': {},
            'context': {'id': 'D_' + _hash(proof)[:16], 'facts': {}, 'current_work': {}},
            'concerns': deepcopy(model.get('concerns', {})), 'witnesses': [],
            'candidate_bundle': None, 'result': checked}
        value['artifacts'].update(semantic_calls=[], semantic_review_completed=False,
            semantic_review_required=False, completion_kind='structural_no_op',
            structural_terminal_proof=proof, semantic_validation=checked,
            decision_coverage={'reviewed': [], 'needs_information': 0, 'missing_facet_evidence': 0})
        value['result'] = finalize_model_result([])
        return wb._commit(value, revision)
    compiled_bindings = compile_bindings(model, canonical, decisions, rules, guaranteed_implementation_nodes)
    compiled_bindings += compile_contact_quality_bindings(model, canonical, decisions, rules)
    compiled_bindings += compile_contact_task_bindings(model, canonical, decisions, rules)
    compiled_bindings += derive_semantic_bindings(model, canonical, decisions, rules)
    # Persist complete proofs before the first network call, including failures.
    value['artifacts']['canonical_pattern_bindings'] = deepcopy(compiled_bindings)
    compact_bindings = compact_semantic_bindings(compiled_bindings)
    packet = {'persona': canonical, 'pattern': {'version': catalogue['version'], 'model_semantic_rules': list(rules.values())},
        'goal_model': model, 'decision_space': decisions, 'input_contract': contract,
        'canonical_pattern_bindings': compact_bindings}
    schema = response_schema(canonical, model, decisions, rules)
    calls = []
    value['artifacts']['semantic_calls'] = calls
    bookkeeping = []
    try:
        raw_draft = _request_semantic_stage('mapping', INSTRUCTION, packet, schema, calls)
    except provider.ProviderError as exc:
        value['artifacts']['semantic_stage_error'] = {'stage': 'mapping', 'error': str(exc), 'retryable': exc.retryable}
        value['result'] = failed_model_result(
            'Modeling failed during semantic mapping after the bounded request policy.',
            code='semantic_mapping_failed')
        return wb._commit(value, revision)
    draft, repairs = reconcile_bookkeeping(raw_draft, decisions, rules)
    bookkeeping.append({'stage': 'mapping', 'repairs': repairs})
    draft, citation_audit = reconcile_persona_quotations(draft, canonical, rules, stage='mapping')
    # Bookkeeping has a separate retained repair log. Bind this source hash
    # to the actual immutable provider response before either working repair.
    citation_audit.update(response_source='actual_provider_response', source_stage='mapping',
                         raw_response_sha256=_hash(raw_draft))
    value['artifacts']['persona_quotation_reconciliation'] = [citation_audit]
    try:
        _validate_response(draft, canonical, model, decisions, rules)
    except provider.ProviderError as exc:
        calls[-1]['semantic_validation_error'] = str(exc)
        value['artifacts'].update(bookkeeping_reconciliation=bookkeeping,
            semantic_stage_error={'stage': 'mapping', 'error': str(exc), 'retryable': False, 'kind': 'semantic_protocol_error'})
        value['result'] = failed_model_result(
            'The semantic mapping failed validation; no final model was produced.',
            code='semantic_mapping_invalid')
        return wb._commit(value, revision)
    review_packet = {**packet, 'untrusted_draft': draft}
    review_incomplete = False
    review_response_source = 'actual_provider_response'
    try:
        raw_final = _request_semantic_stage('semantic_review', INSTRUCTION + '\nRe-evaluate every decision and selected branch. '
            'Correct draft omissions, reversed directions and unsupported mappings using only the original three inputs. '
            'An unknown rule review without a binding is an omission to examine, not a fabricated candidate. '
            'Return the full final reviewed mapping, not a diff.', review_packet, schema, calls)
    except provider.ProviderError as exc:
        raw_final = deepcopy(draft); review_incomplete = True
        review_response_source = 'validated_mapping_fallback'
        value['artifacts']['semantic_stage_error'] = {'stage': 'semantic_review', 'error': str(exc),
            'retryable': exc.retryable, 'fallback': 'Python-validated safe initial mapping; semantic review incomplete.',
            'fallback_working_response_sha256': _hash(raw_final),
            'mapping_raw_response_sha256': value['artifacts']['persona_quotation_reconciliation'][0]['raw_response_sha256']}
    final, repairs = reconcile_bookkeeping(raw_final, decisions, rules)
    bookkeeping.append({'stage': 'semantic_review', 'repairs': repairs})
    final, citation_audit = reconcile_persona_quotations(final, canonical, rules, stage='semantic_review')
    citation_audit.update(response_source=review_response_source,
                         source_stage='mapping' if review_incomplete else 'semantic_review',
                         raw_response_sha256=_hash(raw_final))
    value['artifacts']['persona_quotation_reconciliation'].append(citation_audit)
    try:
        _validate_response(final, canonical, model, decisions, rules)
    except provider.ProviderError as exc:
        calls[-1]['semantic_validation_error'] = str(exc)
        review_incomplete = True; final = deepcopy(draft)
        value['artifacts']['semantic_stage_error'] = {'stage': 'semantic_review', 'error': str(exc), 'retryable': False,
            'kind': 'semantic_protocol_error', 'fallback': 'Python-validated safe initial mapping; semantic review incomplete.'}
    if review_incomplete:
        value['artifacts'].update(semantic_mapping=draft,
            bookkeeping_reconciliation=bookkeeping, semantic_review_completed=False,
            completion_kind='failed_semantic_review')
        value['result'] = failed_model_result(
            'The semantic review did not complete successfully; no final model was produced.',
            code='semantic_review_failed')
        return wb._commit(value, revision)
    try:
        accepted_mapping, compiler_changes = merge_bindings(final, compiled_bindings, canonical, rules=rules, model=model)
        _validate_response(accepted_mapping, canonical, model, decisions, rules)
        checked = _accept(accepted_mapping, canonical, model, decisions, rules)
    except (provider.ProviderError, ModelError) as exc:
        value['artifacts'].update(semantic_mapping=final,
            semantic_review_completed=True, completion_kind='failed_final_validation',
            final_validation_error={'kind': type(exc).__name__, 'message': str(exc)})
        value['result'] = failed_model_result(
            'Final model validation failed; no final model was produced.',
            code='final_validation_failed')
        return wb._commit(value, revision)
    if business_projection(value['base_session']['model']) != model:
        raise ModelError('Semantic modeling changed the original goal model.')
    rejected = sum(row['status'] != 'accepted' for row in checked['decisions'])
    unresolved_rejections = sum(row['status'] != 'accepted' and not row.get('resolved_inapplicable')
                               for row in checked['decisions'])
    unresolved = sum(row['status'] == 'needs_information' or 'unknown' in row['rule_reviews'].values()
                     for row in accepted_mapping['decisions'].values())
    missing = sum(not row['supported'] for row in accepted_mapping['facet_evidence'].values())
    value['analysis_session'] = {'model': model, 'persona': canonical, 'sources': {},
        'context': {'id': 'D_' + _hash(packet)[:16], 'facts': {}, 'current_work': {}},
        'concerns': deepcopy(model.get('concerns', {})), 'witnesses': [],
        'candidate_bundle': None, 'result': checked}
    value['artifacts'].update(semantic_calls=calls, semantic_mapping=final,
        canonical_pattern_bindings=compiled_bindings, canonical_compiler_changes=compiler_changes,
        accepted_mapping=accepted_mapping,
        bookkeeping_reconciliation=bookkeeping, semantic_review_completed=not review_incomplete,
        completion_kind='final_model', finalization_policy=POLICY_ID,
        semantic_validation=checked, decision_coverage={'reviewed': list(decisions),
            'not_instantiated_unestablished_reviews': unresolved,
            'unsupported_facet_evidence': missing,
            'rejected_without_established_inapplicability': unresolved_rejections})
    value['result'] = finalize_model_result(
        [wb._display_relation(value, row) for row in checked['relations']],
        supports=len(checked['supports']), rejected=rejected,
        conflicts=len(checked['conflicts']))
    return wb._commit(value, revision)
