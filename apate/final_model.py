"""Terminal output contract for modeling from the supplied three inputs.

An unestablished pattern premise does not become a fact or a strict preference.
It also does not keep an otherwise completed modeling pass open. Technical
failure remains a failure and cannot be converted to an empty final model.
"""
from copy import deepcopy

POLICY_ID = 'apate.output.final.v1'
SEMANTIC_METHOD_ID = 'apate.model-semantics.v2'


def finalize_model_result(preferences, *, supports=0, rejected=0, conflicts=0):
    """Format already validated relations; the caller must establish completion."""
    preferences = deepcopy(preferences)
    return {'status': 'complete', 'is_final': True, 'finalization_policy': POLICY_ID,
            'preferences': preferences,
            'summary': {'accepted': len(preferences), 'supports': supports,
                        'rejected': rejected, 'conflicts': conflicts},
            'message': 'Preference modeling is complete for the supplied inputs.'}


def failed_model_result(message, *, code):
    """A failed attempt contains no publishable final preferences."""
    return {'status': 'failed', 'is_final': False, 'finalization_policy': POLICY_ID,
            'failure_code': code, 'preferences': [],
            'summary': {'accepted': 0, 'errors': 1}, 'message': message}


def completed_modeling_evidence(artifacts):
    """Require both successful stages, or the original zero-call terminal proof."""
    if (artifacts.get('completion_kind') == 'structural_no_op'
            and artifacts.get('semantic_review_required') is False
            and artifacts.get('structural_terminal_proof')
            and not artifacts.get('semantic_calls')):
        return True
    calls = artifacts.get('semantic_calls', [])
    if not isinstance(calls, list) or any(not isinstance(call, dict) for call in calls):
        return False
    return (artifacts.get('semantic_review_completed') is True
            and not artifacts.get('semantic_stage_error')
            and all(any(call.get('stage') == stage and call.get('status') == 'success'
                        for call in calls) for stage in ('mapping', 'semantic_review')))


def apply_final_output_policy(value):
    """Read-only projection of a stored semantic-method result into this contract.

    This does not rerun the method, rewrite the stored attempt or change its
    accepted relations. Historical experiment files remain historical files.
    """
    result = value.get('result')
    artifacts = value.get('artifacts', {})
    contract = artifacts.get('input_contract', {})
    if (not isinstance(result, dict) or result.get('finalization_policy') == POLICY_ID
            or result.get('status') not in ('complete', 'needs_information')
            or contract.get('method') != SEMANTIC_METHOD_ID):
        return value
    output = deepcopy(value)
    if completed_modeling_evidence(artifacts):
        summary = result.get('summary', {})
        output['result'] = finalize_model_result(result.get('preferences', []),
            supports=summary.get('supports', 0), rejected=summary.get('rejected', 0),
            conflicts=summary.get('conflicts', 0))
    else:
        output['result'] = failed_model_result(
            'Modeling did not complete successfully. Run contextualization again.',
            code='incomplete_stored_attempt')
    return output
