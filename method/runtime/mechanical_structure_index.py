"""Optional original-structure/finite-pair evidence; no runtime integration.

No text, rule, trait, outcome, preference direction or oracle is classified.
This index never replaces the final original validator or its fresh search.
"""
from copy import deepcopy
import hashlib
from itertools import combinations
import json
import math
import time

from apate.preferred_structure import PlanSearch, authorized
from apate.schema import validate_model

POLICY_ID='apate.original-structure.finite-pair-evidence.v1'
HELPER_ID='apate.preferred_structure.PlanSearch.pair'
PAIR_LIMITS={'max_realizations':2048,'max_prefixes':50000,'max_seconds':30}
DEFAULT_INDEX_LIMITS={'max_seconds':5.0,'max_pair_calls':32,'max_nodes':128,'max_roles':32}
BOUNDARIES={
    'pair_quantifier':'exists_compatible_complete_witness_pair_after_complete_realization_classification',
    'execution_fragment':'finite_monotone_root_and_or_optional_and_hard_pre_npr_guards',
    'external_match':'same_external_business_tasks_selected_nodes_or_choices_and_relative_external_task_order',
    'all_realizations_feasible_implied':False,
    'all_schedules_feasible_implied':False,
    'existing_quality_or_temporal_preferences_satisfied_implied':False,
    'dependencies_fulfilled_or_resources_available_implied':False,
    'real_world_ability_energy_cooperation_or_episode_implied':False,
    'personality_rule_premises_or_direction_implied':False,
    'execution_ownership_transferred_by_decision_authority':False,
    'unknown_may_filter_original_opportunities':False,
    'final_original_validator_and_fresh_mechanical_check_required':True,
}


def _json(value):
    if value is None or type(value)in(str,bool,int):return
    if type(value)is float and math.isfinite(value):return
    if type(value)is list:
        for child in value:_json(child)
        return
    if type(value)is dict and all(type(k)is str for k in value):
        for child in value.values():_json(child)
        return
    raise ValueError('Only finite original JSON types are accepted.')


def digest(value):
    _json(value)
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,
        separators=(',',':'),allow_nan=False).encode('utf-8')).hexdigest()


class _IndexStop(Exception):pass


def build_mechanical_structure_index(model,role_ids,*,stop=None,max_seconds=5.0,
        max_pair_calls=32,max_nodes=128,max_roles=32,proof_callback=None):
    """Return ID-only structure and bounded optional evidence for every OR pair.

    ``stop`` must check the caller's existing case/global clock and stop state.
    Its true value or exception cancels optional work as unknown. The complete
    original inputs, every selected facet and the final gate remain unchanged.
    The overall index limit is cooperative; original validation/compilation
    preparation is finite/input-capped but is not forcibly preempted mid-call.
    """
    began=time.monotonic();stop_reason=None;calls=0
    limits={'max_seconds':max_seconds,'max_pair_calls':max_pair_calls,
        'max_nodes':max_nodes,'max_roles':max_roles}
    output={'schema':POLICY_ID,'status':'unresolved','input_sha256':{},
        'helper_identity':HELPER_ID,'helper_per_pair_limits':deepcopy(PAIR_LIMITS),
        'optional_index_limits':limits,'boundaries':deepcopy(BOUNDARIES),
        'structure':None,'decisions':[],'pairs':[],'all_original_pairs_listed':False,
        'helper_calls':0,'termination_reason':None}
    try:_json(limits)
    except Exception:
        output['optional_index_limits']=None
        output['termination_reason']='invalid_configuration'
        output['elapsed_seconds']=time.monotonic()-began
        output['index_sha256']=digest(output)
        return output
    def guard():
        nonlocal stop_reason
        try:
            if stop is not None:
                requested=stop() if callable(stop) else stop.is_set()
                if requested:stop_reason='external_stop';raise _IndexStop()
        except _IndexStop:raise
        except Exception:stop_reason='external_guard_exception';raise _IndexStop()
        if time.monotonic()-began>=max_seconds:
            stop_reason='optional_index_max_seconds';raise _IndexStop()
    def stopped():
        try:guard();return False
        except _IndexStop:return True
    try:
        if isinstance(max_seconds,bool)or not isinstance(max_seconds,(int,float))or not 0<=max_seconds<float('inf'):
            raise ValueError('Invalid optional time cap.')
        for name,value in limits.items():
            if name!='max_seconds'and(type(value)is not int or value<0):raise ValueError('Invalid optional size/call cap.')
        if stop is not None and not callable(stop)and not callable(getattr(stop,'is_set',None)):
            raise ValueError('Invalid external guard.')
        guard();_json(model);_json(role_ids)
        raw=model.get('M0',model)if type(model)is dict else None
        if type(raw)is not dict or type(raw.get('nodes'))is not dict or type(raw.get('roles'))is not dict:
            raise ValueError('Complete original model and role map required.')
        if len(raw['nodes'])>max_nodes or len(raw['roles'])>max_roles:
            stop_reason='optional_input_size_cap';raise _IndexStop()
        if type(role_ids)is not list or not role_ids or any(type(r)is not str or r not in raw['roles']for r in role_ids)or len(set(role_ids))!=len(role_ids):
            raise ValueError('Distinct existing persona-bound original role IDs required.')
        checked=validate_model(model);guard()
        output['input_sha256']={'original_model':digest(model),'bound_original_role_ids':digest(role_ids)}
        nodes=checked['nodes'];refs={r['parent']:r for r in checked.get('refinements',[])}
        region_cache={}
        def region(identity):
            guard()
            if identity not in region_cache:
                result={identity}
                for child in refs.get(identity,{}).get('children',[]):result.update(region(child))
                region_cache[identity]=result
            return region_cache[identity]
        structure={
            'root_id':checked['root'],
            'nodes':{k:{'kind':n['kind'],'role_id':n.get('role'),'optional':bool(n.get('optional',False))}for k,n in nodes.items()},
            'refinements':[{'parent':r['parent'],'operator':r['kind'],'children':list(r['children'])}for r in checked.get('refinements',[])],
            'hard_constraints':[{'source':e['source'],'target':e['target'],'type':e['type']}for e in checked.get('hard_constraints',[])],
            'dependencies':[{'dependency_id':d['id'],'depender_role_id':d['depender'],'dependee_role_id':d['dependee'],
                'depender_node_id':d.get('depender_node'),'dependee_node_id':d.get('dependee_node'),
                'dependum_id':d['dependum'].get('id'),'declarative_only':True}for d in checked.get('dependencies',[])],
            'bound_role_ids':list(role_ids),
        }
        output['structure']=structure
        for scope,ref in sorted(refs.items()):
            if ref['kind']!='OR'or nodes[scope]['kind']!='goal':continue
            guard();authority={};unknown_authority=False
            for role in role_ids:
                guard()
                try:authority[role]=authorized(model,role,scope)
                except Exception:authority[role]=None;unknown_authority=True
            allowed=[r for r,v in authority.items()if v is True]
            authority_status='unknown'if unknown_authority else'unique'if len(allowed)==1 else'none'if not allowed else'ambiguous'
            alternatives=[]
            for endpoint in ref['children']:
                members=region(endpoint)
                alternatives.append({'endpoint_id':endpoint,'region_node_ids':sorted(members),
                    'original_task_role_ids':{k:nodes[k].get('role')for k in sorted(members)if nodes[k]['kind']=='task'},
                    'nested_original_or_ids':[k for k in sorted(members)if k in refs and refs[k]['kind']=='OR'and nodes[k]['kind']=='goal']})
            output['decisions'].append({'scope_id':scope,'direct_child_ids':list(ref['children']),
                'bound_role_authorized':authority,'authorized_bound_role_ids':allowed,
                'authority_status':authority_status,'alternatives':alternatives})
            for endpoints in combinations(sorted(ref['children']),2):
                output['pairs'].append({'scope_id':scope,'endpoint_ids':list(endpoints),
                    'endpoint_order_policy':'canonical_id_order_no_preference_direction',
                    'authority_status':authority_status,'authorized_bound_role_ids':list(allowed),
                    'helper_status':None,'evidence_state':'unknown','termination_reason':'not_queried',
                    'compatible_complete_pair_exists':None,'enumeration_complete':{e:None for e in endpoints},
                    'same_external_context_witness_found':None,'helper_budget':None,
                    'helper_input_hash':None,'raw_helper_proof_sha256':None,'id_evidence_sha256':None})
        output['all_original_pairs_listed']=True
        engine=None
        for row in output['pairs']:
            if row['authority_status']!='unique':
                row['termination_reason']='authority_'+row['authority_status'];continue
            try:
                guard()
                if calls>=max_pair_calls:
                    row['termination_reason']='optional_max_pair_calls';continue
                if engine is None:engine=PlanSearch(model,**PAIR_LIMITS,stop=stopped)
                guard();calls+=1
                left,right=row['endpoint_ids'];proof=engine.pair(row['scope_id'],left,right)
                state=proof.get('status')if type(proof)is dict else None
                if state not in('complete_feasible','infeasible','search_incomplete','stopped'):
                    row['termination_reason']='invalid_helper_result';continue
                if proof.get('scope')!=row['scope_id']or proof.get('source')!=left or proof.get('target')!=right or proof.get('raw_input_sha256')!=digest(model):
                    row['termination_reason']='helper_input_binding_mismatch';continue
                if state in('complete_feasible','infeasible')and proof.get('enumeration_complete')!={'source':True,'target':True}:
                    row['termination_reason']='invalid_helper_completion_claim';continue
                if state=='complete_feasible'and type(proof.get('witness_pair'))is not dict:
                    row['termination_reason']='invalid_helper_witness_claim';continue
                _json(proof)
                proof_bytes=json.dumps(proof,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
                proof_sha256=hashlib.sha256(proof_bytes).hexdigest()
                if proof_callback is not None:proof_callback(row['scope_id'],list(row['endpoint_ids']),proof_bytes,proof_sha256,state)
                row.update(helper_status=state,termination_reason=proof.get('termination_reason'),
                    evidence_state='known'if state in('complete_feasible','infeasible')else'unknown',
                    compatible_complete_pair_exists=True if state=='complete_feasible'else False if state=='infeasible'else None,
                    same_external_context_witness_found=True if state=='complete_feasible'else None,
                    helper_budget=deepcopy(proof['budget']),helper_input_hash=proof.get('input_hash'),
                    raw_helper_proof_sha256=proof_sha256)
                for side,endpoint in(('source',left),('target',right)):
                    complete=proof['enumeration_complete'][side]
                    row['enumeration_complete'][endpoint]=complete
                row['id_evidence_sha256']=digest({k:v for k,v in row.items()if k not in('id_evidence_sha256','raw_helper_proof_sha256','helper_budget')})
                # A stop raised by the original helper remains unknown; later
                # rows are retained and guarded, never removed as inapplicable.
            except _IndexStop:row['termination_reason']=stop_reason
            except Exception:row['termination_reason']='helper_exception'
        output['status']='complete'if all(r['evidence_state']=='known'or r['authority_status']in('none','ambiguous')for r in output['pairs'])else'partial'
    except _IndexStop:output['status']='partial';output['termination_reason']=stop_reason
    except Exception:output['termination_reason']='invalid_input_or_preparation_exception'
    output['helper_calls']=calls;output['elapsed_seconds']=time.monotonic()-began
    if output['termination_reason']is None:output['termination_reason']=stop_reason or'optional_index_finished'
    output['index_sha256']=digest({k:v for k,v in output.items()if k!='index_sha256'})
    return output



def compact_structure_index(index):
    """One immutable case view; omit helper raw proof, counters and timings.

    Complete original domain inputs remain alongside this ID-only evidence.
    Unknown is preserved; no original opportunity is filtered or selected.
    """
    fields=('scope_id','endpoint_ids','endpoint_order_policy','authority_status',
        'authorized_bound_role_ids','helper_status','evidence_state','termination_reason',
        'compatible_complete_pair_exists','enumeration_complete',
        'same_external_context_witness_found','id_evidence_sha256')
    return {'schema':'apate.original-structure.finite-pair-evidence.compact.v1',
        'policy_id':POLICY_ID,'helper_identity':HELPER_ID,
        'input_sha256':deepcopy(index.get('input_sha256',{})),
        'source_index_sha256':index.get('index_sha256'),
        'status':index['status'],'all_original_pairs_listed':index['all_original_pairs_listed'],
        'boundaries':deepcopy(BOUNDARIES),'structure':deepcopy(index.get('structure')),
        'decisions':deepcopy(index.get('decisions',[])),
        'pairs':[{k:deepcopy(row[k])for k in fields}for row in index.get('pairs',[])]}
