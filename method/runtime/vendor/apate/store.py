"""Atomic, local-only research sessions; never write through user-controlled paths."""
from copy import deepcopy
from pathlib import Path
from threading import RLock
import json
import math
import os
import re
import uuid
from .schema import validate_model, model_hash, FACETS, ModelError

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data' / 'sessions'
SAFE = re.compile(r'^[a-f0-9]{32}$')
LOCK = RLock()

class SessionConflict(ModelError):
    pass

def _path(sid):
    if not isinstance(sid, str) or not SAFE.fullmatch(sid):
        raise ValueError('Invalid session ID.')
    return DATA / (sid + '.json')

def get_session(sid):
    with LOCK:
        path = _path(sid)
        if not path.exists(): raise KeyError('Session not found.')
        return json.loads(path.read_text(encoding='utf-8'))

def save_session(session):
    with LOCK:
        value = deepcopy(session)
        value['model'] = validate_model(value['model'])
        if not isinstance(value.get('persona'), dict) or not isinstance(value.get('context'), dict):
            raise ModelError('Persona and context must be objects.')
        facets = value['persona'].get('facets', [])
        if not isinstance(facets, list) or any(f not in FACETS for f in facets):
            raise ModelError('Facets must reference the current fifteen facet IDs.')
        if len(facets) != len(set(facets)):
            raise ModelError('Each persona facet must be listed once.')
        for field in ('actor_id', 'name'):
            item = value['persona'].get(field)
            if not isinstance(item, str) or not item.strip() or len(item) > 200:
                raise ModelError(f'Persona {field} must be a nonempty string of at most 200 characters.')
        role_ids = value['persona'].get('role_ids', [])
        if not isinstance(role_ids, list) or any(not isinstance(r, str) or r not in value['model'].get('roles', {}) for r in role_ids):
            raise ModelError('Persona role_ids must reference existing model actors or roles.')
        if len(role_ids) != len(set(role_ids)):
            raise ModelError('Each persona role assignment must be listed once.')
        for field in ('id', 'episode_id'):
            item = value['context'].get(field)
            if not isinstance(item, str) or not item.strip() or len(item) > 200:
                raise ModelError(f'Context {field} must be a nonempty string of at most 200 characters.')
        facts = value['context'].get('facts', {})
        if not isinstance(facts, dict): raise ModelError('context.facts must be an object.')
        for fact in facts.values():
            if not isinstance(fact, dict) or (fact.get('value') is not None and not isinstance(fact.get('value'), bool)):
                raise ModelError('Each fact must be an object with value true, false or null.')
        if not isinstance(value['context'].get('current_work', {}), dict):
            raise ModelError('context.current_work must be an object.')
        for field in ('sources', 'concerns'):
            if not isinstance(value.get(field, {}), dict):
                raise ModelError(f'{field} must be an object.')
        witnesses = value.get('witnesses', [])
        if not isinstance(witnesses, list):
            raise ModelError('witnesses must be a list.')
        for witness in witnesses:
            if not isinstance(witness, dict):
                raise ModelError('Each witness must be an object.')
            if 'id' in witness and (not isinstance(witness['id'], str) or not witness['id'].strip()):
                raise ModelError('Witness id must be a nonempty string when supplied.')
            sequence = witness.get('sequence')
            if not isinstance(sequence, list) or any(not isinstance(task, str) for task in sequence):
                raise ModelError('Each witness sequence must be a list of task ID strings.')
        bundle = value.get('candidate_bundle')
        if bundle is not None and not isinstance(bundle, dict):
            raise ModelError('candidate_bundle must be an object or null.')
        profile=value.get('preference_profile',{'weights':{}})
        if not isinstance(profile,dict) or not isinstance(profile.get('weights'),dict) or len(profile['weights'])>1500:
            raise ModelError('preference_profile requires a weights object.')
        for key,weight in profile['weights'].items():
            if not isinstance(key,str):raise ModelError('Weight keys must be preference IDs.')
            if weight is None or isinstance(weight,str) and not weight.strip():profile['weights'][key]=0;continue
            if isinstance(weight,bool) or not isinstance(weight,(int,float)) or not math.isfinite(weight) or not 0<=weight<=1:raise ModelError('Manual weights must be in [0,1].')
        value['preference_profile']=profile
        value['model_hash'] = model_hash(value['model'])
        path = _path(value['id'])
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            previous = json.loads(path.read_text(encoding='utf-8'))
            if value.get('revision', 0) != previous.get('revision', 0):
                raise SessionConflict('Inputs changed during this operation. The stale result was not saved; run the operation again.')
        value['revision'] = value.get('revision', 0) + 1
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temp, path)
        return value

def create_session(payload):
    value = deepcopy(payload)
    if 'model' not in value:
        value = {'model': value.get('M0', value)}
    value['id'] = uuid.uuid4().hex
    value['revision'] = 0
    value.setdefault('persona', {'actor_id': 'Actor', 'name': 'Research Actor', 'facets': [], 'role_ids': []})
    value.setdefault('context', {'id': 'Context', 'episode_id': 'Episode', 'facts': {}, 'current_work': {}})
    for key in ('sources', 'concerns'): value.setdefault(key, {})
    value.setdefault('witnesses', [])
    value.setdefault('candidate_bundle', None)
    value['result'] = None
    value.pop('compilation', None)
    value.pop('planner_result', None)
    value.pop('ranking_result', None)
    return save_session(value)

def update_session(sid, patch):
    with LOCK:
        value = get_session(sid)
        if 'model' in patch:
            proposed = validate_model(patch['model'])
            if model_hash(proposed) != model_hash(value['model']):
                raise ModelError('The imported goal model is fixed for this preference session. Import a model to start a new session.')
        input_keys=('model', 'persona', 'context', 'sources', 'concerns', 'witnesses', 'candidate_bundle')
        for key in (*input_keys,'preference_profile'):
            if key in patch: value[key] = deepcopy(patch[key])
        # A dirty input never retains an apparently current augmentation.
        if any(key in patch for key in input_keys):value['result'] = None
        value.pop('compilation', None)
        value.pop('planner_result', None)
        value.pop('ranking_result', None)
        return save_session(value)
