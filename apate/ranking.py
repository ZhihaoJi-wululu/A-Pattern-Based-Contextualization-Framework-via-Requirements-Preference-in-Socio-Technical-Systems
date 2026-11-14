"""Manual paper-profile scoring over independently checked finite plans.

SHOP2 remains the plan generator. This module evaluates the compiler's literal
PDDL3 preference ASTs over the complete normalized trace, including skip
operators, then sums the manually supplied weights of satisfied preferences.
It neither invents plans nor implements HTNPlan-P's search heuristics.
"""
from copy import deepcopy
from decimal import Decimal
from functools import lru_cache
import math

from .compiler import symbol
from .semantics import validate_plan


def _freeze_formula(formula, atoms):
    if not isinstance(formula, (list, tuple)) or not formula or not isinstance(formula[0], str):
        raise ValueError('Preference formula must be a compiler AST.')
    op, *args = formula
    if op == 'const':
        if len(args) != 1 or not isinstance(args[0], bool):
            raise ValueError('const requires one Boolean.')
        return (op, args[0])
    if op == 'atom':
        if len(args) != 1 or not isinstance(args[0], str) or args[0] not in atoms:
            raise ValueError('Preference atom must reference a compiled performance predicate.')
        return (op, args[0])
    arities = {'not': 1, 'at_end': 1, 'sometime': 1, 'always': 1,
               'sometime-before': 2, 'sometime-after': 2}
    if op not in {'and', 'or'} and (op not in arities or len(args) != arities[op]):
        raise ValueError('Unsupported or malformed preference operator: ' + op)
    return (op, *(_freeze_formula(arg, atoms) for arg in args))


def _trace_evaluator(sequence):
    states, done = [frozenset()], set()
    for task in sequence:
        done.add('v_' + symbol(task))
        states.append(frozenset(done))

    @lru_cache(None)
    def evaluate(ast, index=0):
        op, *args = ast
        if op == 'const': return args[0]
        if op == 'atom': return args[0] in states[index]
        if op == 'not': return not evaluate(args[0], index)
        if op == 'and': return all(evaluate(arg, index) for arg in args)
        if op == 'or': return any(evaluate(arg, index) for arg in args)
        if op == 'at_end': return evaluate(args[0], len(states) - 1)
        if op == 'sometime': return any(evaluate(args[0], i) for i in range(len(states)))
        if op == 'always': return all(evaluate(args[0], i) for i in range(len(states)))
        if op == 'sometime-before':
            return all(not evaluate(args[0], i) or any(evaluate(args[1], j) for j in range(i))
                       for i in range(len(states)))
        if op == 'sometime-after':
            # Literal finite PDDL3 permits j == i; first-attainment order is
            # deliberately not substituted for the paper's Table 4 formula.
            return all(not evaluate(args[0], i) or any(evaluate(args[1], j) for j in range(i, len(states)))
                       for i in range(len(states)))
        raise ValueError('Unsupported preference operator: ' + op)
    return evaluate


def _weights(preferences, weights):
    if weights is None: weights = {}
    if not isinstance(weights, dict):
        raise ValueError('Manual weights must be an object keyed by preference id.')
    ids = {p['id'] for p in preferences}
    if any(key not in ids for key in weights):
        raise ValueError('Unknown preference weight id: ' + ', '.join(str(k) for k in weights if k not in ids))
    values = {}
    for key in ids:
        value = weights.get(key)
        if value is None or isinstance(value, str) and not value.strip():
            values[key] = Decimal(0)
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1 or not math.isfinite(value):
            raise ValueError('Manual weight for ' + key + ' must be a finite number in [0,1].')
        values[key] = Decimal(str(value))
    return values


def rank_plans(compilation, plans, weights, *, search_complete=False, source='SHOP2'):
    """Rank only supplied feasible normalized plans using the paper metric.

    Each plan is a normalized task-id list or an object containing
    ``normalized_sequence`` (``sequence`` also accepts a normalized witness).
    A business-only sequence is never expanded with invented dummy positions.
    Blank or omitted weights equal zero. All tied best plan ids are returned.
    """
    if not isinstance(compilation, dict) or not isinstance(compilation.get('normalized_model'), dict):
        raise ValueError('A compilation with normalized_model is required.')
    model = compilation['normalized_model']
    preferences = compilation.get('ir', {}).get('preferences')
    if not isinstance(preferences, list):
        raise ValueError('Compilation requires its preference AST list.')
    atoms = {'v_' + symbol(key) for key, node in model.get('nodes', {}).items() if node.get('kind') == 'task'}
    formulas, pref_ids = [], set()
    for pref in preferences:
        if not isinstance(pref, dict) or not isinstance(pref.get('id'), str) or not pref['id'] or pref['id'] in pref_ids:
            raise ValueError('Compiled preference ids must be unique nonempty strings.')
        pref_ids.add(pref['id'])
        formulas.append(_freeze_formula(pref.get('formula'), atoms))
    effective_weights = _weights(preferences, weights)
    if isinstance(plans, dict): plans = plans.get('plans')
    if not isinstance(plans, list): raise ValueError('plans must be a list of supplied candidate traces.')
    if not isinstance(search_complete, bool): raise ValueError('search_complete must be Boolean.')
    if not isinstance(source, str) or not source.strip(): raise ValueError('source must be a nonempty string.')

    ranked, rejected, plan_ids = [], [], set()
    dummies = set(compilation.get('dummy_tasks', []))
    for index, candidate in enumerate(plans):
        plan = candidate if isinstance(candidate, dict) else {}
        plan_id = plan.get('plan_id', plan.get('id', 'plan_' + str(index + 1)))
        if not isinstance(plan_id, str) or not plan_id or plan_id in plan_ids:
            raise ValueError('Candidate plan ids must be unique nonempty strings.')
        plan_ids.add(plan_id)
        if isinstance(candidate, list): sequence = candidate
        elif isinstance(candidate, dict):
            sequence = candidate.get('normalized_sequence', candidate.get('sequence'))
            if sequence is None and not dummies: sequence = candidate.get('business_sequence')
        else: sequence = None
        if not isinstance(sequence, list) or any(not isinstance(task, str) for task in sequence):
            rejected.append({'plan_id': plan_id, 'reason': 'requires_normalized_sequence',
                             'validation': {'valid': False, 'errors': ['Provide the actual normalized trace including any dummy operators.']}})
            continue
        checked = validate_plan(model, sequence)
        if not checked['valid']:
            rejected.append({'plan_id': plan_id, 'reason': 'infeasible_plan', 'validation': checked})
            continue
        evaluate = _trace_evaluator(sequence)
        rows, score, penalty = [], Decimal(0), Decimal(0)
        for pref, formula in zip(preferences, formulas):
            satisfied = evaluate(formula)
            weight = effective_weights[pref['id']]
            contribution = weight if satisfied else Decimal(0)
            violation_cost = Decimal(0) if satisfied else weight
            score += contribution
            penalty += violation_cost
            rows.append({'id': pref['id'], 'label': pref.get('label', pref['id']), 'kind': pref.get('kind'),
                         'origin': pref.get('origin', 'base'), 'satisfied': satisfied, 'weight': float(weight),
                         'contribution': float(contribution), 'violation': not satisfied, 'penalty': float(violation_cost)})
        record = {'plan_id': plan_id, 'normalized_sequence': deepcopy(sequence),
                  'business_sequence': [task for task in sequence if task not in dummies],
                  'removed_dummy_tasks': [task for task in sequence if task in dummies],
                  'source': source, 'score': float(score), 'penalty': float(penalty), 'preferences': rows,
                  'satisfied_preferences': [row['id'] for row in rows if row['satisfied']],
                  'violated_preferences': [row['id'] for row in rows if not row['satisfied']],
                  'validation': checked, '_decimal_score': score}
        if isinstance(plan.get('raw_operators'), list): record['raw_operators'] = deepcopy(plan['raw_operators'])
        ranked.append(record)

    ranked.sort(key=lambda plan: -plan['_decimal_score'])
    best = ranked[0]['_decimal_score'] if ranked else None
    previous, rank = None, 0
    for index, plan in enumerate(ranked):
        score = plan.pop('_decimal_score')
        if score != previous: rank = index + 1
        plan['rank'], plan['is_best'] = rank, score == best
        previous = score
    complete_scope = search_complete and source in {'SHOP2', 'original-SHOP2'} and not rejected
    return {'status': 'ok' if ranked else 'no_feasible_plans', 'ranked_plans': ranked,
            'best_plan_ids': [plan['plan_id'] for plan in ranked if plan['is_best']],
            'best_score': float(best) if best is not None else None, 'rejected_plans': rejected,
            'weights': {pref['id']: float(effective_weights[pref['id']]) for pref in preferences},
            'total_weight': float(sum(effective_weights.values(), Decimal(0))),
            'candidate_count': len(plans), 'feasible_count': len(ranked), 'source': source,
            'search_complete': search_complete,
            'optimality_scope': 'all plans in the completed SHOP2 search' if complete_scope else 'supplied finite candidate plans',
            'global_optimality_proven': bool(complete_scope and ranked), 'preference_optimized': False,
            'ranking_method': 'sum of manually weighted satisfied paper preferences',
            'metric': 'sum(weights) - sum(weight * is-violated)'}
