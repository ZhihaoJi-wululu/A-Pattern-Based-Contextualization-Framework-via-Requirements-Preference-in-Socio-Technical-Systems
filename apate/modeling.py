"""Modeling diagnostics for PATPREF's integrated goal model.

The canvas uses iStar 2.0 actors and typed dependencies together with PATPREF's
finite execution tree, hard ordering and qualitative preference annotations.
The diagnostics classify execution annotations independently of core iStar.
"""
from copy import deepcopy

from .schema import BUSINESS, QUALITY, validate_model


def validate_workspace_model(model):
    """Validate input and return the model, presentation diagnostics and profile.

    Structural errors raise ModelError with English details. Informational
    profile differences do not invalidate an existing verified execution model.
    This function never modifies the caller's model or invents dependencies.
    """
    checked = validate_model(model)
    nodes = checked['nodes']
    actors = checked.get('roles', {})
    diagnostics = []
    local, cross_scope, quality_extensions = [], [], []

    for index, refinement in enumerate(checked.get('refinements', [])):
        parent = refinement['parent']
        ids = [parent, *refinement['children']]
        owners = {nodes[key].get('role') for key in ids}
        row = {'refinement_index': index, **deepcopy(refinement)}
        if nodes[parent]['kind'] in QUALITY:
            quality_extensions.append(row)
            diagnostics.append({
                'severity': 'info', 'code': 'quality_refinement_extension',
                'message': 'This quality decomposition is displayed as an PATPREF preference annotation.',
                'node_ids': ids, 'refinement_index': index,
            })
        elif len(owners) == 1 and None not in owners:
            local.append(row)
        else:
            cross_scope.append(row)
            diagnostics.append({
                'severity': 'warning', 'code': 'execution_coordination_refinement',
                'message': 'This complete decomposition group is displayed as dashed blue execution coordination. Its original AND/OR meaning and endpoints are preserved.',
                'node_ids': ids, 'refinement_index': index,
            })

    unowned = [key for key, node in nodes.items() if node.get('role') is None]
    if actors and unowned:
        diagnostics.append({
            'severity': 'info', 'code': 'unowned_execution_elements',
            'message': 'These existing business elements are displayed outside actor boundaries because they have no actor owner.',
            'node_ids': unowned,
        })

    if any(row['kind'] == 'OR' for row in checked.get('refinements', [])
           if nodes[row['parent']]['kind'] in BUSINESS):
        diagnostics.append({
            'severity': 'info', 'code': 'exclusive_execution_alternatives',
            'message': 'The executable profile selects exactly one OR alternative. Core iStar OR refinement is inclusive; this is an explicit planning policy.',
        })

    if checked.get('dependencies'):
        diagnostics.append({
            'severity': 'info', 'code': 'declarative_dependencies',
            'message': 'Dependencies record reliance between actors. They do not create execution operators, hard precedence constraints or automatic preference requirements.',
            'dependency_ids': [item['id'] for item in checked['dependencies']],
        })

    resources = [key for key, node in nodes.items() if node['kind'] == 'resource']
    if resources:
        diagnostics.append({
            'severity': 'info', 'code': 'descriptive_resources',
            'message': 'Resources are descriptive intentional elements. Execution requires a separately modeled task; no resource operator is generated.',
            'node_ids': resources,
        })

    cross_contributions = [edge for edge in checked.get('contributions', [])
                           if nodes[edge['source']].get('role') != nodes[edge['target']].get('role')]
    if cross_contributions:
        diagnostics.append({
            'severity': 'warning', 'code': 'cross_scope_execution_effects',
            'message': 'These cross-actor execution effects are displayed as PATPREF contribution annotations.',
            'edges': deepcopy(cross_contributions),
        })

    profile = {
        'id': 'apate.istar2.execution.v1',
        'notation': 'Integrated PATPREF goal model with iStar 2.0 actor and dependency notation',
        'execution_or_policy': 'exactly_one',
        'istar_or_semantics': 'inclusive',
        'dependency_execution': 'declarative_only',
        'actor_types': {key: value.get('type', 'role') if isinstance(value, dict) else 'role'
                        for key, value in actors.items()},
        'actor_local_refinements': local,
        'cross_scope_refinements': cross_scope,
        'quality_refinement_extensions': quality_extensions,
        'scope_layout': 'disjoint_computed_boundaries',
        'standard_reference': 'https://arxiv.org/abs/1605.07767',
        'extensions': ['finite_execution_tree', 'hard_pre_npr', 'optional_execution',
                       'makes_breaks_effects', 'soft_temporal_preferences',
                       'persona_role_binding', 'contextual_preferred_to'],
    }
    return {'model': checked, 'diagnostics': diagnostics, 'profile': profile}
