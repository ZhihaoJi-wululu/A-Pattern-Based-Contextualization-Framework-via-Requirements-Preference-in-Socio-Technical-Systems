"""Adapt interactive workspaces to the frozen P10 case runner."""
from copy import deepcopy
from threading import Lock
import uuid

from . import p10_runtime, workbench as wb
from .final_model import POLICY_ID, failed_model_result
from .preferred_protocol import digest, project_inputs
from .schema import ModelError, business_projection
from .store import SessionConflict
from .three_input import CONTRACT_ID, public_three_input_workspace


# P10 runs one case at a time, with parallelism confined to the selected facets.
ACTIVE_CASE = Lock()


def contextualize_workspace(identity, payload):
    if (not isinstance(payload, dict) or set(payload) - {'persona', 'revision', 'material'}
            or payload.get('material', '') != ''):
        raise ModelError('Three-input modeling accepts persona, revision and empty material compatibility only.')
    if 'revision' in payload and (type(payload['revision']) is not int or payload['revision'] < 1):
        raise ModelError('Workspace revision must be a positive integer.')
    if not ACTIVE_CASE.acquire(blocking=False):
        raise SessionConflict('The workbench is already contextualizing a model. Try again after it finishes.')
    try:
        return _contextualize(identity, payload)
    finally:
        ACTIVE_CASE.release()


def _contextualize(identity, payload):
    value = wb.get_workspace(identity)
    revision = value['revision']
    if payload.get('revision', revision) != revision:
        raise SessionConflict('This workspace input revision is stale.')

    persona = wb._persona(value, payload)
    contract = {'id': CONTRACT_ID, 'method': p10_runtime.METHOD_ID,
                'prompt_version': p10_runtime.PROMPT_VERSION,
                'inputs': ['persona', 'pattern', 'goal_model'],
                'finalization_policy': POLICY_ID}
    value.update(persona=persona, material='', result=None, analysis_session=None,
                 artifacts={'input_contract': contract})
    base = value.get('base_session')
    if base is None:
        value['result'] = failed_model_result(
            'The imported graph has no complete supported execution projection.',
            code='unsupported_goal_model')
    elif not (persona['role_ids'] and persona['facets'] and persona['description'].strip()):
        value['result'] = failed_model_result(
            'A usual-trait description, selected facets and original role are required.',
            code='invalid_persona_input')
    else:
        _run(value, base['model'], persona, contract)
    wb._commit(value, revision)
    return public_three_input_workspace(value)


def _run(value, original_model, persona, contract):
    model = business_projection(original_model)
    canonical = {**persona, 'role_ids': [wb._canonical_reference(value, role) for role in persona['role_ids']]}
    # The existing model allowlist separates execution declarations from
    # imported metadata. P10 loads its own byte-verified catalogue.
    prepared = project_inputs(canonical, model, {})
    case = {'source_document': {'model': prepared['goal_model']}, 'persona': prepared['persona']}
    contract.update(persona_sha256=prepared['hashes']['persona'],
                    goal_model_sha256=prepared['hashes']['goal_model'],
                    projection=prepared['projection'])

    archive = wb.DATA.parent / 'runs' / 'p10' / uuid.uuid4().hex
    run = {'archive': archive.relative_to(wb.DATA.parent).as_posix()}
    value['artifacts']['p10_run'] = run
    try:
        output = p10_runtime.run_case(archive, case)
    except p10_runtime.P10RuntimeError as exc:
        run.update(status='failed', error=str(exc))
        value['result'] = failed_model_result(str(exc), code='p10_runtime_failed')
        return
    except (OSError, ValueError) as exc:
        run.update(status='failed', error=str(exc))
        value['result'] = failed_model_result(
            'The workbench could not save or read the P10 run.', code='p10_archive_failed')
        return

    result = output['result']
    run.update(output['run'], status=result['status'])
    contract.update({key: run[key] for key in ('framework_sha256', 'pattern_file_sha256',
                                              'prompt_sha256', 'checker_prompt_sha256')})
    value['result'] = {**result, 'preferences': [wb._display_relation(value, row)
                                                 for row in result['preferences']]}
    if result['is_final']:
        value['analysis_session'] = {
            'model': model, 'persona': canonical, 'sources': {},
            'context': {'id': 'D_' + digest(case)[:16], 'facts': {}, 'current_work': {}},
            'concerns': deepcopy(model.get('concerns', {})), 'witnesses': [], 'candidate_bundle': None,
            'result': {**result, 'method': p10_runtime.METHOD_ID, 'relations': result['preferences'],
                       'supports': output['supports'], 'conflicts': output['conflicts']},
        }
