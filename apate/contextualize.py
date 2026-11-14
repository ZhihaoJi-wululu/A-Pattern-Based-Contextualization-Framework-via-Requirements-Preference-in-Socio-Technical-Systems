"""Evidence-bound candidate import and constrained qualitative augmentation.

This module never calls a model API and never accepts a cached relation/effect
as its conclusion. It starts from M0 and recomputes every imported witness.
"""
from collections import defaultdict
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path

from .patterns import (CandidateBindingError, catalogue_overview, load_catalogue,
                       machine_contracts, resolve_candidate_binding, rule_contracts)
from .schema import business_projection, model_hash, validate_model
from .semantics import attained, validate_plan, selected_attainment_model, omitted_optional_timing, temporal_report

EXAMPLES=Path(__file__).resolve().parents[1]/'examples'


def _stable(prefix,value):
    raw=json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'))
    return prefix+hashlib.sha256(raw.encode('utf-8')).hexdigest()[:20]


def load_example(name):
    allowed={p.stem:p for p in EXAMPLES.glob('*.json')}
    if name not in allowed:raise ValueError('Unknown example: '+str(name))
    return json.loads(allowed[name].read_text(encoding='utf-8'))


def list_examples():
    output=[]
    for p in sorted(EXAMPLES.glob('*.json')):
        session=json.loads(p.read_text(encoding='utf-8'))
        if 'model' in session:
            output.append({'id':p.stem,'name':session.get('name',p.stem),'label':session.get('label',p.stem),
              'nodes':len(session['model']['nodes']),'witnesses':len(session.get('witnesses',[]))})
    return output


def _evidence_valid(reference,sources):
    if isinstance(reference,list):return bool(reference) and all(_evidence_valid(r,sources) for r in reference)
    if not isinstance(reference,dict) or not isinstance(sources,dict):return False
    source_id,span_id=reference.get('source_id'),reference.get('span_id')
    if not isinstance(source_id,str) or not isinstance(span_id,str):return False
    source=sources.get(source_id)
    if not isinstance(source,dict):return False
    spans=source.get('spans',{})
    if not isinstance(spans,dict):return False
    span=spans.get(span_id)
    if isinstance(span,dict):span=span.get('text')
    if not isinstance(span,str) or not span.strip():return False
    quote=reference.get('quote')
    return quote is None or (isinstance(quote,str) and bool(quote.strip()) and quote in span)


class _ModelView:
    def __init__(self,model):
        self.model=model
        self.nodes=model['nodes']
        self.refs={r['parent']:r for r in model.get('refinements',[])}
        self.parents={c:r['parent'] for r in self.refs.values() for c in r['children'] if self.nodes[c]['kind'] in {'goal','task'}}
        # Cache only for this model view; a class-level method cache retains
        # every session through its self keys for the server's whole life.
        self.leaves=lru_cache(None)(self.leaves)
        self._contains=lru_cache(None)(self._contains)
        self._time_of=lru_cache(None)(self._time_of)
    def leaves(self,key):
        if self.nodes[key]['kind']=='task':return frozenset({key})
        return frozenset().union(*(self.leaves(c) for c in self.refs.get(key,{}).get('children',[])))
    def ancestor_chain(self,key):
        output=[key]
        while output[-1] in self.parents:output.append(self.parents[output[-1]])
        return output
    def endpoint_nodes(self,value):
        if isinstance(value,str):values=[value]
        elif isinstance(value,list):values=value
        elif isinstance(value,dict):values=value.get('tasks',[]) if 'tasks' in value else [value.get('goal')]
        else:raise ValueError('Endpoint must name an existing task or task group.')
        if not values or any(not isinstance(k,str) or k not in self.nodes or self.nodes[k]['kind'] not in {'goal','task'} for k in values):
            raise ValueError('Endpoint contains an unknown or non-business node.')
        return values
    def endpoint_leaves(self,value):
        return frozenset().union(*(self.leaves(k) for k in self.endpoint_nodes(value)))
    def fact_scope(self,fact):
        """An absent/empty scope is global; declared scopes name business nodes."""
        if 'scope_ids' not in fact:return None
        ids=fact['scope_ids']
        if not isinstance(ids,list) or any(not isinstance(k,str) for k in ids) or len(set(ids))!=len(ids):
            raise ValueError('Fact scope_ids must be a list of unique business node IDs.')
        return self.endpoint_leaves(ids) if ids else None
    def contains(self,value,done):
        return self._contains(tuple(self.endpoint_nodes(value)),frozenset(done))
    def _contains(self,keys,done):
        if omitted_optional_timing(self.model,keys,done):return False
        effective=selected_attainment_model(self.model,done)
        return all(attained(effective,k,done) for k in keys)
    def time_of(self,value,sequence):
        return self._time_of(tuple(self.endpoint_nodes(value)),tuple(sequence))
    def _time_of(self,keys,sequence):
        if omitted_optional_timing(self.model,keys,sequence):return None
        effective=selected_attainment_model(self.model,sequence)
        contains=lambda done:all(attained(effective,k,done) for k in keys)
        done=set()
        if contains(done):return 0
        for index,task in enumerate(sequence,1):
            done.add(task)
            if contains(done):return index
        return None
    def optional_scope(self,value):
        keys=self.endpoint_nodes(value)
        # A complete optional scope can include required descendant tasks, e.g.
        # GenerateIdeas plus its independent Review, with only the parent optional.
        for parent in self.ancestor_chain(keys[0]):
            if not self.nodes[parent].get('optional'):continue
            grand=self.parents.get(parent)
            if grand and self.refs[grand]['kind']=='AND' and all(self.leaves(k)<=self.leaves(parent) for k in keys):return parent
        return None
    def comparison_or(self,left,right):
        a,b=self.endpoint_leaves(left),self.endpoint_leaves(right)
        candidates=[]
        for key,ref in self.refs.items():
            if ref['kind']!='OR' or self.nodes[key]['kind']!='goal':continue
            ca=[c for c in ref['children'] if a<=self.leaves(c)]
            cb=[c for c in ref['children'] if b<=self.leaves(c)]
            if ca and cb and ca[0]!=cb[0]:candidates.append(key)
        return min(candidates,key=lambda k:len(self.leaves(k))) if candidates else None
    def authorized(self,role,value):
        scopes=deepcopy(self.model.get('role_discretion',{}).get(role,[]))
        meta=self.model.get('roles',{}).get(role)
        if isinstance(meta,dict):scopes+=meta.get('discretion',meta.get('discretion_scopes',[]))
        if isinstance(scopes,str):scopes=[scopes]
        leaves=self.endpoint_leaves(value)
        for scope in scopes:
            if scope in self.nodes and leaves<=self.leaves(scope):return True
        return all(self.nodes[k].get('role')==role for k in leaves)


def evaluate_concern(model,sequence,expression):
    """Evaluate only the explicit pre-registered effect language, never text."""
    view=_ModelView(model)
    def evaluate(ast):
        if not isinstance(ast,dict) or len(ast)!=1:raise ValueError('Concern AST requires one supported operator per object.')
        op,value=next(iter(ast.items()))
        if op=='attains':
            if omitted_optional_timing(model,value,sequence):return None
            effective=selected_attainment_model(model,sequence)
            return all(attained(effective,k,set(sequence)) for k in view.endpoint_nodes(value))
        if op=='not':
            result=evaluate(value)
            return None if result is None else not result
        if op in {'and','or'}:
            if not isinstance(value,list) or not value:raise ValueError('and/or concern requires nonempty children.')
            values=[evaluate(child) for child in value]
            if op=='and':return False if False in values else None if None in values else True
            return True if True in values else None if None in values else False
        if op=='before':
            if not isinstance(value,list) or len(value)!=2:raise ValueError('before concern requires two existing business references.')
            a,b=(view.time_of(n,sequence) for n in value)
            return None if a is None or b is None else a<b
        raise ValueError('Unsupported concern AST operator: '+str(op))
    return evaluate(expression)


def _coverage(model,relations):
    view=_ModelView(model)
    positions={}
    for key,ref in view.refs.items():
        if ref['kind']=='OR' and view.nodes[key]['kind']=='goal':
            positions['or:'+key]={'id':'or:'+key,'node_id':key,'kind':'choice','label':view.nodes[key]['label'],'covered':False,'relation_ids':[]}
    for key,node in view.nodes.items():
        if node['kind'] in {'goal','task'} and node.get('optional'):
            positions['optional:'+key]={'id':'optional:'+key,'node_id':key,'kind':'optional_participation','label':node['label'],'covered':False,'relation_ids':[]}
    for relation in relations:
        key=None
        if relation['kind']=='choice':
            parent=view.comparison_or(relation['source'],relation['target'])
            if parent:key='or:'+parent
        elif relation['kind']=='optional_participation':
            parent=view.optional_scope(relation['x'])
            if parent:key='optional:'+parent
        if key in positions:
            positions[key]['covered']=True
            positions[key]['relation_ids'].append(relation['id'])
    total=len(positions);covered=sum(p['covered'] for p in positions.values())
    return {'definition':'Each business OR and optional participation once, including conditional branches; temporal relations and support counts do not inflate coverage.',
      'positions':list(positions.values()),'choice_positions_total':total,'choice_positions_covered':covered,
      'choice_coverage_ratio':covered/total if total else None,'choice_coverage_percent':round(covered/total*100,1) if total else None,
      'OR_total':sum(p['kind']=='choice' for p in positions.values()),
      'OR_covered':sum(p['kind']=='choice' and p['covered'] for p in positions.values()),
      'optional_total':sum(p['kind']=='optional_participation' for p in positions.values()),
      'optional_covered':sum(p['kind']=='optional_participation' and p['covered'] for p in positions.values()),
      'preferred_to_relations':sum(r['kind']=='choice' for r in relations),
      'participation_relations':sum(r['kind']=='optional_participation' for r in relations),
      'temporal_relations':sum(r['kind']=='temporal' for r in relations),
      'scope':'Only the current declared model, persona, evidence and finite feasible witnesses; not prediction accuracy.'}


def _result(base,persona,bundle,relations,supports,decisions,witness_report):
    bindings=[]
    if persona.get('actor_id') and bundle.get('role_id'):
        bindings=[{'source':persona['actor_id'],'relation':'playsRole','target':bundle['role_id']}]
    augmented={'base':deepcopy(base),'actor_bindings':bindings,'relations':deepcopy(relations)}
    return {'base':deepcopy(base),'augmented_model':augmented,'relations':relations,'supports':supports,'decisions':decisions,
      'coverage':_coverage(base,relations),'base_preserved':business_projection(augmented['base'])==business_projection(base),
      'model_hash':model_hash(base),'provider':deepcopy(bundle.get('provider',{'kind':'assistant-import','model_reported':None,'snapshot':None})),
      'witness_validation':witness_report,
      'scope':'Independent evidence and finite-plan checks. Candidate generation is a separate reviewed input stage.'}


def contextualize_session(session,candidate_bundle=None):
    base=validate_model(session['model'])
    view=_ModelView(base)
    persona=deepcopy(session.get('persona',{}));context=session.get('context',{});sources=session.get('sources',{})
    concerns=session.get('concerns',{})
    for name,value in [('persona',persona),('context',context),('sources',sources),('concerns',concerns)]:
        if not isinstance(value,dict):raise ValueError(name+' must be an object.')
    for field in ('facts','current_work'):
        if not isinstance(context.get(field,{}),dict):raise ValueError('context.'+field+' must be an object.')
    raw_witnesses=session.get('witnesses',[])
    if not isinstance(raw_witnesses,list):raise ValueError('witnesses must be a list.')
    bundle=deepcopy(candidate_bundle if candidate_bundle is not None else session.get('candidate_bundle') or {})
    if not isinstance(bundle,dict):raise ValueError('The candidate bundle must be a JSON object.')
    candidates=bundle.get('candidates',[])
    if not isinstance(candidates,list):raise ValueError('candidates must be a JSON list.')
    if len(candidates)>500:raise ValueError('At most 500 candidates are accepted per import.')
    catalogue=load_catalogue()
    parents={card['id']:card for card in catalogue['patterns']}
    contracts=rule_contracts()
    witnesses={};bad_witnesses=[]
    for index,raw in enumerate(raw_witnesses):
        if not isinstance(raw,dict):bad_witnesses.append({'id':str(index),'errors':['Witness must be an object.']});continue
        wid=raw.get('id',str(index));sequence=raw.get('sequence')
        if not isinstance(wid,str) or not wid.strip():
            bad_witnesses.append({'id':str(index),'errors':['Witness id must be a nonempty string.']});continue
        checked=validate_plan(base,sequence)
        if checked['valid'] and wid not in witnesses:
            witnesses[wid]={'id':wid,'sequence':deepcopy(sequence),'done':frozenset(sequence),'checked':checked}
        else:bad_witnesses.append({'id':wid,'errors':checked.get('errors') or ['Duplicate witness ID.']})
    witness_report={'provided':len(raw_witnesses),'valid':len(witnesses),'invalid':bad_witnesses,
      'scope':'Finite imported or actual-planner witnesses; no claim of exhaustive search.'}
    relations_by_id={};supports_by_id={};decisions=[]
    common=[]
    if bundle.get('schema_version')!='apate.candidates.v1':common.append(('candidate_schema','Candidate schema_version must be apate.candidates.v1.'))
    if bundle.get('model_hash')!=model_hash(base):common.append(('model_hash_mismatch','M0 changed or this candidate bundle belongs to another model.'))
    if not persona.get('actor_id') or bundle.get('actor_id')!=persona.get('actor_id'):common.append(('actor_mismatch','Candidate Actor does not match the concrete persona.'))
    role=bundle.get('role_id')
    if not isinstance(role,str) or role not in base.get('roles',{}) or role not in persona.get('role_ids',[]):common.append(('role_binding_missing','Actor does not currently play the claimed existing Role.'))
    if not context.get('id') or bundle.get('context_id')!=context.get('id'):common.append(('context_mismatch','Candidate context does not match current context.'))
    if not _evidence_valid(persona.get('evidence'),sources):common.append(('persona_evidence_missing','Persona requires an existing source span; a facet label is not evidence.'))
    provider=bundle.get('provider')
    if not isinstance(provider,dict) or not isinstance(provider.get('kind'),str):common.append(('provider_missing','Provider metadata is required.'))

    def decision(candidate,status,code,message,**extra):
        value={'candidate_id':candidate.get('id'),'pattern_id':candidate.get('pattern_id'),
          'rule_id':candidate.get('rule_id'),'status':status,
          'reason_code':code,'reason':message,**extra}
        decisions.append(value)
        return value

    for index,candidate in enumerate(candidates):
        if not isinstance(candidate,dict):
            decision({'id':str(index)},'rejected','candidate_not_object','Candidate must be an object.');continue
        if common:
            decision(candidate,'rejected',common[0][0],common[0][1],diagnostics=[{'code':c,'message':m} for c,m in common]);continue
        malformed=[field for field in ('id','pattern_id','rule_id','facet','kind','formula','concern_id','current_work_id','review_node')
                   if candidate.get(field) is not None and not isinstance(candidate[field],str)]
        if malformed:
            decision(candidate,'rejected','candidate_field_type','Candidate identifier fields must be strings: '+', '.join(malformed));continue
        try:
            binding=resolve_candidate_binding(candidate,parents=parents,rules=contracts)
        except CandidateBindingError as exc:
            decision(candidate,'rejected',exc.code,str(exc));continue
        candidate={**candidate,'pattern_id':binding['pattern_id'],'rule_id':binding['rule_id']}
        contract=binding['contract']
        matching=[f for f in binding['facets'] if f in persona.get('facets',[])]
        if candidate.get('facet') is not None:matching=[f for f in matching if f==candidate['facet']]
        if not matching:decision(candidate,'rejected','facet_missing','The relevant facet is absent from this persona.');continue
        kind=candidate.get('kind')
        if kind not in contract['allowed_kinds']:decision(candidate,'rejected','kind_not_supported','This pattern does not support that relation kind.');continue
        bindings=candidate.get('fact_bindings',{})
        if not isinstance(bindings,dict):decision(candidate,'rejected','fact_bindings_invalid','fact_bindings must map required predicates to existing facts.');continue
        if any(fid is not None and not isinstance(fid,str) for fid in bindings.values()):
            decision(candidate,'rejected','fact_bindings_invalid','Fact bindings must contain existing fact ID strings.');continue
        guard_details=[];false_guards=[];unknown_guards=[];bad_guards=[]
        for predicate in contract['required_predicates']:
            fid=bindings.get(predicate);fact=context.get('facts',{}).get(fid)
            row={'predicate':predicate,'fact_id':fid}
            if isinstance(fact,dict) and 'scope_ids' in fact:row['scope_ids']=deepcopy(fact['scope_ids'])
            if not isinstance(fact,dict):unknown_guards.append(predicate);row.update(value=None,status='missing_fact')
            elif fact.get('predicate')!=predicate:bad_guards.append(predicate);row.update(value=fact.get('value'),status='wrong_predicate')
            elif fact.get('value') is not True and fact.get('value') is not False and fact.get('value') is not None:
                bad_guards.append(predicate);row.update(value=None,status='invalid_truth_value')
            elif fact.get('value') is False:false_guards.append(predicate);row.update(value=False,status='false')
            elif fact.get('value') is None:unknown_guards.append(predicate);row.update(value=None,status='unknown')
            elif not _evidence_valid(fact.get('evidence'),sources):unknown_guards.append(predicate);row.update(value=True,status='unresolved_evidence')
            else:row.update(value=True,status='true',evidence=deepcopy(fact['evidence']))
            guard_details.append(row)
        if bad_guards:decision(candidate,'rejected','fact_binding_invalid','A fact has an incompatible predicate or truth type.',guards=guard_details);continue
        scoped_guards=[row for row in guard_details if 'scope_ids' in row]
        if false_guards and not scoped_guards:decision(candidate,'rejected','guard_false','Necessary facts are false: '+', '.join(false_guards),guards=guard_details);continue
        if unknown_guards:decision(candidate,'unknown','guard_unknown','Necessary facts or source spans remain unknown: '+', '.join(unknown_guards),guards=guard_details);continue
        concern=concerns.get(candidate.get('concern_id'))
        if not isinstance(concern,dict) or 'ast' not in concern:decision(candidate,'rejected','concern_missing','Concern and its effect AST must be registered before candidate import.');continue
        if kind!='temporal' and isinstance(concern['ast'],dict) and set(concern['ast'])=={'before'}:
            decision(candidate,'rejected','concern_kind_mismatch','A direct before criterion measures temporal order and cannot support an implementation choice or optional participation.');continue
        try:
            if kind=='choice':
                source,target=candidate.get('source'),candidate.get('target')
                view.endpoint_nodes(source);view.endpoint_nodes(target)
                parent=view.comparison_or(source,target)
                if parent is None:raise ValueError('Choice endpoints must locate different existing implementations of the same OR.')
                region=view.leaves(parent)
                relation_core={'kind':kind,'type':'preferred_to','source':deepcopy(source),'target':deepcopy(target)}
                endpoints=[source,target]
            else:
                formula=candidate.get('formula');x=candidate.get('x');y=candidate.get('y')
                if formula not in contract['allowed_formulas']:raise ValueError('Formula is not supported by this CPS card.')
                view.endpoint_nodes(x);endpoints=[x]
                if kind=='optional_participation':
                    scope=view.optional_scope(x)
                    if scope is None:raise ValueError('Participation must reference an actual optional AND subtree or its existing activity.')
                    region=view.leaves(scope)
                else:
                    view.endpoint_nodes(y);endpoints.append(y);region=frozenset()
                relation_core={'kind':kind,'type':formula,'formula':formula,'x':deepcopy(x),'y':deepcopy(y)}
            if not all(view.authorized(role,e) for e in endpoints):
                decision(candidate,'rejected','outside_role_discretion','This Role neither owns the compared work nor has an explicit coordination scope.');continue
            # Validate the complete AST even if no witness is available.
            evaluate_concern(base,[],concern['ast'])
        except (ValueError,KeyError,TypeError) as exc:
            decision(candidate,'rejected','binding_invalid',str(exc));continue
        # New scoped evidence must apply to every compared implementation. Keep
        # legacy records unchanged; explicit [] denotes episode-wide evidence.
        if scoped_guards:
            compared=frozenset().union(*(view.endpoint_leaves(e) for e in endpoints))
            invalid_scopes=[];scope_mismatches=[];scope_conflicts=[]
            for row in scoped_guards:
                fact=context['facts'][row['fact_id']]
                try:scope=view.fact_scope(fact)
                except (ValueError,KeyError,TypeError) as exc:
                    row.update(status='invalid_scope',scope_error=str(exc));invalid_scopes.append(row['fact_id']);continue
                if scope is not None and not compared<=scope:
                    row.update(value=None,claimed_value=fact['value'],status='scope_mismatch')
                    scope_mismatches.append(row['predicate']);continue
                row['scope_status']='global' if scope is None else 'covers_comparison'
                applicable=[]
                for other_id,other in context['facts'].items():
                    if not isinstance(other,dict) or other.get('predicate')!=row['predicate'] or (other.get('value') is not True and other.get('value') is not False):continue
                    if not _evidence_valid(other.get('evidence'),sources):continue
                    try:other_scope=view.fact_scope(other)
                    except (ValueError,KeyError,TypeError) as exc:
                        invalid_scopes.append(other_id);row.update(status='invalid_scope',scope_error=str(exc));continue
                    if other_scope is None or other_scope & compared:applicable.append((other_id,other['value']))
                if any(value is True for _,value in applicable) and any(value is False for _,value in applicable):
                    row.update(value=None,claimed_value=fact['value'],status='scope_conflict',conflicting_fact_ids=sorted(str(fid) for fid,_ in applicable))
                    scope_conflicts.append(row['predicate'])
            if invalid_scopes:decision(candidate,'rejected','fact_scope_invalid','Fact scope_ids contain malformed or non-business references.',fact_ids=sorted(set(str(fid) for fid in invalid_scopes)),guards=guard_details);continue
            if scope_mismatches:decision(candidate,'unknown','fact_scope_mismatch','Evidence scope does not cover every compared endpoint: '+', '.join(scope_mismatches),guards=guard_details);continue
            if scope_conflicts:decision(candidate,'unknown','fact_scope_conflict','Overlapping evidence disagrees on required conditions: '+', '.join(scope_conflicts),guards=guard_details);continue
            if false_guards:decision(candidate,'rejected','guard_false','Necessary facts are false: '+', '.join(false_guards),guards=guard_details);continue
        work=None
        if contract['requires_current_work']:
            work=context.get('current_work',{}).get(candidate.get('current_work_id'))
            if not isinstance(work,dict) or work.get('remaining')!=candidate.get('x') or candidate.get('y') not in work.get('diversion',[]):
                decision(candidate,'rejected','current_work_mismatch','An independently recorded current work/checkpoint binding is required.');continue
            try:
                view.endpoint_nodes(work['checkpoint'])
                unit=work['work_unit']
                view.endpoint_nodes(unit)
                if not view.endpoint_leaves(work['checkpoint'])<=view.endpoint_leaves(unit) or not view.endpoint_leaves(candidate['x'])<=view.endpoint_leaves(unit):
                    raise ValueError('Checkpoint and remaining work must belong to the declared current work unit.')
            except (KeyError,TypeError,ValueError):decision(candidate,'rejected','checkpoint_invalid','Current work checkpoint is not an existing business element.');continue
        review=candidate.get('review_node')
        if contract['requires_review_node']:
            if (review not in view.nodes or view.nodes[review]['kind']!='task'
                    or view.nodes[review].get('role') not in base.get('roles',{})
                    or view.nodes[review].get('role')==role):
                decision(candidate,'rejected','independent_review_missing','CI requires an existing independent review task; candidate generation alone is insufficient.');continue
        # Effects are derived from real sequences, independently of any cached
        # effects/qualities/supports that a provider may include in the JSON.
        effects={}; claimed_temporal={}
        try:
            for wid,w in witnesses.items():
                effects[wid]=evaluate_concern(base,w['sequence'],concern['ast'])
                if kind=='temporal':
                    claimed_temporal[wid]=temporal_report(base,w['sequence'],candidate)['paper_literal']
        except (KeyError,ValueError,TypeError) as exc:
            decision(candidate,'rejected','concern_invalid',str(exc));continue
        requested=candidate.get('witness_pairs')
        if requested is not None:
            if not isinstance(requested,list):decision(candidate,'rejected','witness_pairs_invalid','witness_pairs must be a list.');continue
            if any(not isinstance(pair,dict) or any(not isinstance(pair.get(field),str) for field in ('preferred','other')) for pair in requested):
                decision(candidate,'rejected','witness_pairs_invalid','Each witness pair requires preferred and other witness ID strings.');continue
            pairs=[(p.get('preferred'),p.get('other')) for p in requested if isinstance(p,dict)]
        else:
            # Exact outside-region task order prevents unrelated decisions from
            # being smuggled into a local choice or optional comparison.
            good=defaultdict(list);other=defaultdict(list)
            for wid,w in witnesses.items():
                key=tuple(t for t in w['sequence'] if t not in region) if kind!='temporal' else tuple(sorted(w['done']))
                if effects[wid] is True:good[key].append(wid)
                elif effects[wid] is False:other[key].append(wid)
            pairs=[(a,b) for key,items in good.items() for a in items for b in other.get(key,[])]
        valid_pairs=[];pair_seen=set();comparable=0
        for aid,bid in pairs:
            if (aid,bid) in pair_seen:continue
            pair_seen.add((aid,bid))
            if aid not in witnesses or bid not in witnesses:continue
            a,b=witnesses[aid],witnesses[bid]
            sa,sb=a['sequence'],b['sequence']
            if kind=='choice':
                if not view.contains(candidate['source'],a['done']) or not view.contains(candidate['target'],b['done']):continue
                if view.contains(candidate['target'],a['done']) or view.contains(candidate['source'],b['done']):continue
            elif kind=='optional_participation':
                if not view.contains(candidate['x'],a['done']) or view.contains(candidate['x'],b['done']):continue
            else:
                if a['done']!=b['done']:continue
                if not all(view.contains(e,w['done']) for e in endpoints for w in (a,b)):continue
                ca,cb=view.time_of(work['checkpoint'],sa),view.time_of(work['checkpoint'],sb)
                if ca is None or cb is None or sa[:ca]!=sb[:cb]:continue
                endpoint_times=[(view.time_of(e,sa),ca) for e in endpoints]+[(view.time_of(e,sb),cb) for e in endpoints]
                if any(t is None or t<=checkpoint for t,checkpoint in endpoint_times):continue
                if any(value is None for w in (a,b) for value in w['checked']['qualities'].values()):continue
                if a['checked']['qualities']!=b['checked']['qualities']:continue
                # A different criterion cannot certify a temporal claim that
                # remains true (or false) in both compared executions.
                if claimed_temporal[aid] is not True or claimed_temporal[bid] is not False:continue
            if kind!='temporal' and [t for t in sa if t not in region]!=[t for t in sb if t not in region]:continue
            if contract['requires_review_node']:
                if review not in a['done']:continue
                activity_time=view.time_of(candidate.get('x',candidate.get('source')),sa)
                review_time=view.time_of(review,sa)
                if activity_time is None or review_time is None or activity_time>=review_time:continue
            comparable+=1
            if effects[aid] is True and effects[bid] is False:
                pair={'preferred':aid,'other':bid,'preferred_effect':True,'other_effect':False}
                if kind=='temporal':pair.update(preferred_formula=True,other_formula=False)
                valid_pairs.append(pair)
        if not valid_pairs:
            status='no_difference' if comparable else 'no_witness'
            decision(candidate,status,'effects_equal_or_unknown' if comparable else 'no_valid_complete_pair',
              'No strict known effect difference in the admissible pairs.' if comparable else 'No valid complete witness pair matches the implementations and current scope.',guards=guard_details);continue
        valid_pairs.sort(key=lambda p:(p['preferred'],p['other']))
        relation_core.update(actor_id=persona['actor_id'],role_id=role,context_id=context['id'])
        if kind=='temporal':relation_core['current_work_id']=candidate['current_work_id']
        rid=_stable('R_',relation_core)
        relation=relations_by_id.setdefault(rid,{'id':rid,**relation_core,'support_ids':[],'pattern_ids':[],'rule_ids':[],'facets':[],'concern_ids':[]})
        accepted_supports=[]
        for facet in matching:
            support_core={'model_hash':model_hash(base),'relation_id':rid,'pattern_id':candidate['pattern_id'],
              'rule_id':candidate['rule_id'],'facet':facet,
              'actor_id':persona['actor_id'],'role_id':role,'context_id':context['id'],'concern_id':candidate['concern_id'],
              'fact_bindings':deepcopy(bindings),'witness_pairs':valid_pairs}
            # Keep stable IDs for existing rule/facet evidence while making the
            # canonical parent and independent branch explicit in its payload.
            legacy_identity={**support_core,'pattern_id':candidate['rule_id']}
            legacy_identity.pop('rule_id')
            sid=_stable('S_',legacy_identity)
            support={'id':sid,**support_core,'candidate_id':candidate.get('id'),'provider':deepcopy(bundle['provider']),
              'pattern_version':catalogue['version'],'evidence_sources':deepcopy(contract['sources']),
              'inference_boundary':contract['inference_boundary'],'guards':deepcopy(guard_details),
              'persona_evidence':deepcopy(persona.get('evidence')),'status':'active_transfer_candidate',
              'witness_count':len(valid_pairs)}
            supports_by_id.setdefault(sid,support)
            if sid not in relation['support_ids']:relation['support_ids'].append(sid)
            for field,value in [('pattern_ids',candidate['pattern_id']),('rule_ids',candidate['rule_id']),
                                ('facets',facet),('concern_ids',candidate['concern_id'])]:
                if value not in relation[field]:relation[field].append(value)
            accepted_supports.append(sid)
        decision(candidate,'accepted','conditions_and_witnesses_verified','Rule facts, scope, complete plans and a strict effect difference are verified.',
          relation_id=rid,support_ids=accepted_supports,witness_count=len(valid_pairs),guards=guard_details)
    result=_result(base,persona,bundle,[relations_by_id[k] for k in sorted(relations_by_id)],[supports_by_id[k] for k in sorted(supports_by_id)],decisions,witness_report)
    # Literal business temporal results are copied only from the independent
    # paper-semantic checker, never the historical fixture's cached flags.
    result['business_temporal_diagnostics']={wid:w['checked']['temporal'] for wid,w in witnesses.items() if w['checked']['temporal']}
    return result


def withdraw_support(result,support_id):
    output=deepcopy(result)
    found=next((s for s in output.get('supports',[]) if s['id']==support_id),None)
    if found is None:raise ValueError('Unknown support ID: '+str(support_id))
    output['supports']=[s for s in output['supports'] if s['id']!=support_id]
    remaining={s['id']:s for s in output['supports']}
    kept=[]
    for relation in output.get('relations',[]):
        relation['support_ids']=[sid for sid in relation['support_ids'] if sid in remaining]
        if not relation['support_ids']:continue
        current=[remaining[sid] for sid in relation['support_ids']]
        relation['pattern_ids']=sorted({s['pattern_id'] for s in current})
        relation['rule_ids']=sorted({s.get('rule_id',s['pattern_id']) for s in current})
        relation['facets']=sorted({s['facet'] for s in current})
        relation['concern_ids']=sorted({s['concern_id'] for s in current})
        kept.append(relation)
    output['relations']=kept
    output['augmented_model']['relations']=deepcopy(kept)
    output['coverage']=_coverage(output['base'],kept)
    output.setdefault('withdrawals',[]).append({'support_id':support_id,'relation_id':found['relation_id'],'reason':'Explicit researcher withdrawal; independent supports retained.'})
    for decision in output.get('decisions',[]):
        if support_id in decision.get('support_ids',[]):
            active=[sid for sid in decision['support_ids'] if sid in remaining]
            decision['active_support_ids']=active
            if not active:decision['status']='withdrawn';decision['reason_code']='support_withdrawn'
    output['base_preserved']=business_projection(output['augmented_model']['base'])==business_projection(output['base'])
    return output


def export_prompt(session):
    """Export an explicit manual bridge, with no claim of automatic model use."""
    model=validate_model(session['model'])
    from .compiler import compile_model
    basis=compile_model(model)
    bundle={'schema_version':'apate.candidates.v1','model_hash':model_hash(model),
      'provider':{'kind':'assistant-import','model_reported':'current-assistant','snapshot':None},
      'actor_id':session.get('persona',{}).get('actor_id'),'role_id':(session.get('persona',{}).get('role_ids') or [None])[0],
      'context_id':session.get('context',{}).get('id'),'candidates':[]}
    instruction=(
      'Act as the candidate provider for this PATPREF research prototype. Return only a JSON candidate bundle matching candidate_template. '
      'Bind an existing pattern, Actor/Role, pre-registered concern, existing business task or complete task group, and evidence-bound facts. '
      'Supply canonical pattern_id and an explicit rule_id from that pattern; each rule has independent conditions. '
      'A shared source rule is scoped to its selected parent facet, never an AND requirement across facets. '
      'Every required_predicate must reference a matching context fact; do not invent facts, nodes, qualities, contributions, weights or Skip tasks. '
      'A missing/false/unknown fact is not permission to add a relation. Do not use the predicted choice as a trigger. '
      'Supply complete witness_pairs when available; the application will independently validate them and recompute effects. '
      'Use formalization_basis (the paper five transformations, normalized HTN and attainment formulae) as the feasibility basis. '
      'Bind personal endpoints only to original model elements; wrapper and dummy nodes are internal translation artifacts. '
      'Use current_work_id for Productiveness; use an existing independent review_node for Creative Imagination. '
      'Keep opposing concerns and supports separate. The tool does not automatically call this conversation or any model API. '
      'Paper Table4 require-after uses literal PDDL3 j>=i; first-attainment order is a separate diagnostic.')
    return {'schema_version':'apate.prompt.v1','instruction':instruction,'candidate_template':bundle,
      'model_hash':model_hash(model),'model':deepcopy(model),'persona':deepcopy(session.get('persona',{})),
      'context':deepcopy(session.get('context',{})),'sources':deepcopy(session.get('sources',{})),
      'concerns':deepcopy(session.get('concerns',{})),'witnesses':deepcopy(session.get('witnesses',[])),
      'formalization_basis':{k:deepcopy(basis[k]) for k in ('compiler','transformation_steps','normalized_model','ir','source_map')},
      'patterns':machine_contracts(),'rules':rule_contracts(),'catalogue_overview':catalogue_overview(),
      'candidate_fields':{'pattern_id':'Canonical facet-pattern ID.',
                          'rule_id':'One rule_id listed by that pattern; bind only its required_predicates.'},
      'provider_status':'manual assistant export/import; no API invocation'}
