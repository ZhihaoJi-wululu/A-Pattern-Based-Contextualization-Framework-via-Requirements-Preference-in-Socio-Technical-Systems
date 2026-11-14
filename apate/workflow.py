"""The five paper transformations connect validated augmentation to plan scoring."""
from copy import deepcopy
from .compiler import compile_model
from .schema import model_hash
from .planner import run_planner
from .ranking import rank_plans


def current_relations(session):
    result=session.get('result')
    if not result:return []
    if result.get('model_hash')!=model_hash(session['model']) or not result.get('base_preserved'):
        raise ValueError('The completion does not match the current M0. Please validate again.')
    support_ids={s['id'] for s in result.get('supports',[])}
    return [deepcopy(r) for r in result.get('relations',[]) if any(s in support_ids for s in r.get('support_ids',[]))]


def invalidate_after_contextualization(session):
    for key in ('compilation','planner_result','ranking_result'):session.pop(key,None)
    valid={k for k,n in session['model']['nodes'].items() if n['kind'] in {'softgoal','hard_preference'}}
    valid.update(p['id'] for p in session['model'].get('temporal_preferences',[]))
    valid.update('apate:'+r['id'] for r in current_relations(session))
    profile=session.get('preference_profile',{'weights':{}})
    session['preference_profile']={'weights':{k:v for k,v in profile['weights'].items() if k in valid}}


def compile_session(session,payload=None):
    payload=payload or {}
    include=payload.get('include_contextualization',True)
    if not isinstance(include,bool):raise ValueError('include_contextualization must be a boolean.')
    profile=payload.get('paper_profile',session.get('preference_profile'))
    if 'weights' in payload:profile={'weights':payload['weights']}
    relations=current_relations(session) if include else []
    compiled=compile_model(session['model'],profile,relations)
    compiled['contextualization']={'included':include,'accepted_relation_count':len(relations),'model_hash':model_hash(session['model'])}
    if include and not session.get('result'):
        compiled['warnings'].append('There is no validated PATPREF completion yet; S3 contains only baseline preferences.')
    session['compilation']=compiled
    if profile is not None:session['preference_profile']=deepcopy(profile)
    session.pop('ranking_result',None)
    return compiled


def rank_session(session,payload):
    source=payload.get('candidate_source','shop2')
    if source not in {'shop2','witnesses'}:raise ValueError('Candidate source must be shop2 or witnesses.')
    compiled=compile_session(session,payload)
    weights=(compiled.get('paper_profile') or {'weights':{}})['weights']
    generator=None
    if source=='shop2':
        count=payload.get('max_plans',50);timeout=payload.get('timeout',30)
        if isinstance(count,bool) or not isinstance(count,int) or not 1<=count<=50:raise ValueError('max_plans must be between 1 and 50.')
        if isinstance(timeout,bool) or not isinstance(timeout,(int,float)) or not 0<timeout<=60:raise ValueError('timeout must be between 0 and 60 seconds.')
        generator=run_planner(compiled,max_plans=count,timeout=timeout)
        session['planner_result']=generator
        result=rank_plans(compiled,generator['plans'],weights,search_complete=generator['search_complete'],source='original-SHOP2')
        result['generator']={k:deepcopy(generator[k]) for k in ('status','termination','elapsed','search_complete','preference_optimized') if k in generator}
        result['planner_result']=generator
    else:
        raw=session.get('witnesses',[])
        if len(raw)>2000:raise ValueError('Finite witness ranking accepts up to 2,000 entries.')
        dummies=set(compiled['dummy_tasks']);plans=[];inconsistent=[]
        for i,witness in enumerate(raw):
            if not isinstance(witness,dict):inconsistent.append(str(i));continue
            normalized=witness.get('normalized_sequence')
            if normalized is not None and (not isinstance(normalized,list) or any(not isinstance(t,str) for t in normalized) or [t for t in normalized if t not in dummies]!=witness.get('sequence')):
                inconsistent.append(witness.get('id',str(i)));continue
            plans.append({'plan_id':str(witness.get('id','witness_'+str(i))),'normalized_sequence':normalized if normalized is not None else witness.get('sequence')})
        result=rank_plans(compiled,plans,weights,search_complete=False,source='imported normalized witnesses')
        result['inconsistent_witnesses']=inconsistent
        result['candidate_warning']='A business sequence that omits optional tasks requires an actual normalized_sequence; the tool will not guess dummy timestamps. See the details for rejected records.'
    result['compilation']=compiled
    result['candidate_source']=source
    session['ranking_result']=result
    return result
