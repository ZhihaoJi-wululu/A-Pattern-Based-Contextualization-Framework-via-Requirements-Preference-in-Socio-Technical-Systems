"""Sound forward checks for a fixed selected task set.

These checks eliminate dead prefixes, not candidate orders. In normalized
models, attainment of a task/goal is monotone. Once such a source is attained,
an unstarted selected npr target can never pass its first-start guard later.
A target that has already started (including in this very candidate) is not
subject to this check. Quality sources can lose truth after breaks and are
deliberately excluded.
"""
from typing import NamedTuple

from .semantics import attained


class NprForwardCheck(NamedTuple):
    source: str
    target: str
    selected_target_leaves: frozenset


def prepare_npr_forward_checks(model, selected, leaves):
    """Prepare immutable checks once per selected, normalized task set.

    ``leaves(node_id)`` must return all original/normalized descendant tasks.
    An unchosen OR branch or omitted original optional target has no selected
    leaves and therefore imposes no future start requirement.
    """
    # A flat original model can ignore an optional child before its eventual
    # adoption is known. Its effective final attainment need not equal that
    # flat prefix interpretation. Fail open unless optional selection has
    # already been compiled to fixed wrappers/dummy tasks.
    if any(node.get('optional') for node in model['nodes'].values()
           if node.get('kind') in ('task', 'goal')):
        return ()
    chosen = frozenset(selected)
    checks = []
    for edge in model.get('hard_constraints', []):
        if edge.get('type') != 'npr': continue
        source, target = edge.get('source'), edge.get('target')
        if not isinstance(source, str) or not isinstance(target, str): continue
        if model['nodes'].get(source, {}).get('kind') not in ('task', 'goal'): continue
        if model['nodes'].get(target, {}).get('kind') not in ('task', 'goal'): continue
        target_tasks = chosen.intersection(leaves(target))
        if target_tasks:
            checks.append(NprForwardCheck(source, target, frozenset(target_tasks)))
    return tuple(checks)


def npr_prefix_impossible(model, done_after, checks):
    """True only when a monotone attained source blocks a future first start.

    ``done_after`` includes the proposed task. Checking the target's started
    condition first preserves simultaneous source completion/target start and
    source completion after an earlier target start. This function is not a
    replacement for the existing pre/npr guards or final plan validation.
    """
    for check in checks:
        if not check.selected_target_leaves.isdisjoint(done_after): continue
        if model['nodes'].get(check.source, {}).get('kind') not in ('task', 'goal'): continue
        if attained(model, check.source, done_after): return True
    return False
