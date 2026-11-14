"""Liaskos et al. (2011), Fig. 2 and §4.2, compiled for original SHOP2.

This is PATPREF's independently implemented translation layer. It is not the
unobtained authors' translation script or their HTNPlan-P extension.
"""
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
import math

BUSINESS={"goal","task"}
QUALITY={"softgoal","hard_preference"}
COMPILER_VERSION="apate.paper2011.compiler.v2"

def symbol(key):
    """Injective, ASCII Lisp/PDDL identifier; labels are never executable text."""
    return "n_"+str(key).encode("utf-8").hex()

def _ast(op,*args):
    if op in {"and","or"}:
        if not args:return ["const",op=="and"]
        if len(args)==1:return args[0]
    return [op,*args]

def _lisp(formula):
    op,*args=formula
    if op=="atom":return "("+args[0]+")"
    if op=="const":return "(eval "+("t" if args[0] else "nil")+")"
    return "("+op+" "+" ".join(_lisp(a) for a in args)+")"

def _pddl(formula):
    op,*args=formula
    if op=="atom":return "("+args[0]+")"
    if op=="const":return "(and)" if args[0] else "(or)"
    if op=="at_end":return "(at end "+_pddl(args[0])+")"
    return "("+op+" "+" ".join(_pddl(a) for a in args)+")"

def _preconditions(formula):
    return "()" if formula==["const",True] else "("+_lisp(formula)+")"

def _temporal(formula,x,y=None):
    if formula=="sometime":return ["sometime",x]
    if formula=="never":return ["always",["not",x]]
    if formula=="precedes":return ["sometime-before",["and",x,y],["and",x,["not",y]]]
    if formula=="require_before":return ["sometime-before",y,x]
    if formula=="require_after":return ["sometime-after",y,x]
    if formula=="never_before":return _temporal("precedes",y,x)
    if formula=="never_after":return _temporal("precedes",x,y)
    raise ValueError("Unsupported paper temporal template: "+str(formula))

def compile_model(model,paper_profile=None,contextualized_relations=None):
    """Return paper-normalized IR, actual SHOP2 source and PDDL3 preferences."""
    from .schema import validate_model, model_hash
    original=deepcopy(validate_model(model))
    normalized=deepcopy(original)
    nodes=normalized["nodes"]
    warnings=[]
    dummies=[]
    wrappers={}
    refs=normalized.get("refinements",[])
    additions=[]
    for ref in refs:
        if nodes[ref["parent"]]["kind"]!="goal" or ref["kind"]!="AND":continue
        children=[]
        for key in ref["children"]:
            n=nodes[key]
            if n.get("optional") and n["kind"] in BUSINESS:
                wrapper="__opt_"+key;dummy="__skip_"+key
                if wrapper in nodes or dummy in nodes:raise ValueError("Reserved compiler ID collision")
                nodes[wrapper]={"id":wrapper,"label":"Internal optional wrapper","kind":"goal","role":n.get("role"),"optional":False,"internal":True,"original":key}
                nodes[dummy]={"id":dummy,"label":"Internal skip operator","kind":"task","role":n.get("role"),"optional":False,"internal":True,"dummy":True,"original":key}
                n["optional"]=False
                additions.append({"parent":wrapper,"kind":"OR","children":[key,dummy]})
                wrappers[key]=wrapper;dummies.append(dummy);children.append(wrapper)
            else:children.append(key)
        ref["children"]=children
    refs.extend(additions)
    byparent={r["parent"]:r for r in refs}
    source_map={"nodes":{},"operators":{},"optional_wrappers":wrappers,"dummy_to_original":{d:nodes[d]["original"] for d in dummies}}
    for key,n in nodes.items():
        s=symbol(key)
        source_map["nodes"][key]={"symbol":s,"kind":n["kind"],"predicate":"v_"+s if n["kind"]=="task" else None,"operator":"!do_"+s if n["kind"]=="task" else None,"htn_task":"achieve_"+s if n["kind"]=="goal" else None,"original":n.get("original",key),"internal":bool(n.get("internal"))}
        if n["kind"]=="task":source_map["operators"]["!do_"+s]=key

    @lru_cache(None)
    def attainment(key):
        n=nodes[key]
        if n["kind"]=="task":return ["atom","v_"+symbol(key)]
        if n["kind"]!="goal":raise ValueError("Attainment endpoint is not a business node: "+key)
        ref=byparent.get(key)
        if not ref:raise ValueError("Business goal requires a decomposition: "+key)
        return _ast(ref["kind"].lower(),*(attainment(c) for c in ref["children"]))

    def hard_guard(key):
        terms=[]
        for edge in normalized.get("hard_constraints",[]):
            if edge["target"]==key:
                source=attainment(edge["source"])
                terms.append(source if edge["type"]=="pre" else ["not",source])
        return _ast("and",*terms)

    operators=[];methods=[]
    for key,n in nodes.items():
        if n["kind"]=="task":
            operators.append({"node":key,"name":"!do_"+symbol(key),"precondition":hard_guard(key),"add":["v_"+symbol(key)],"delete":[],"dummy":key in dummies})
        elif n["kind"]=="goal":
            ref=byparent.get(key)
            if not ref:raise ValueError("Business goal requires a decomposition: "+key)
            groups=[ref["children"]] if ref["kind"]=="AND" else [[c] for c in ref["children"]]
            for index,group in enumerate(groups):
                methods.append({"id":"method_"+symbol(key)+"_"+str(index),"goal":key,"task":"achieve_"+symbol(key),"precondition":hard_guard(key),"ordering":"unordered" if ref["kind"]=="AND" else "ordered","subtasks":[source_map["nodes"][c]["operator"] if nodes[c]["kind"]=="task" else source_map["nodes"][c]["htn_task"] for c in group],"children":group})

    @lru_cache(None)
    def quality(key):
        if nodes[key]["kind"] not in QUALITY:raise ValueError("Quality endpoint is not a preference: "+key)
        positive=[attainment(c["source"]) for c in normalized.get("contributions",[]) if c["target"]==key and c["type"]=="makes"]
        ref=byparent.get(key)
        if ref:
            children=[c for c in ref["children"] if not nodes[c].get("optional")] if ref["kind"]=="AND" else ref["children"]
            if not children and ref["kind"]=="AND":warnings.append("Quality AND "+key+" has only optional children; its empty conjunction is true under §4.2.3.")
            positive.append(_ast(ref["kind"].lower(),*(quality(c) for c in children)))
        vetoes=[["not",attainment(c["source"])] for c in normalized.get("contributions",[]) if c["target"]==key and c["type"]=="breaks"]
        return _ast("and",_ast("or",*positive),*vetoes)

    preferences=[]
    for key,n in nodes.items():
        if n["kind"] in QUALITY:preferences.append({"id":key,"name":"pref_"+symbol(key),"label":n.get('label',key),"kind":"quality","origin":"base","formula":["at_end",quality(key)]})
    for pref in original.get("temporal_preferences",[]):
        formula=pref["formula"];x=attainment(pref["x"])
        y=attainment(pref["y"]) if pref.get("y") else None
        preferences.append({"id":pref["id"],"name":"pref_temporal_"+symbol(pref["id"]),"label":pref.get('label',pref['id']),"kind":"temporal","origin":"base","template":formula,"formula":_temporal(formula,x,y)})

    # Personal preferences reuse the paper's attainment/formula layer. They do
    # not add mandatory tasks, guards, or wrappers to the original business tree.
    relations=deepcopy(contextualized_relations or [])
    if not isinstance(relations,list) or len(relations)>500:raise ValueError('contextualized_relations must be a list of at most 500 relations')
    def endpoint(value):
        keys=[value] if isinstance(value,str) else value if isinstance(value,list) else value.get('tasks',[value.get('goal')]) if isinstance(value,dict) else []
        if not keys or any(not isinstance(k,str) or k not in nodes or nodes[k]['kind'] not in BUSINESS for k in keys):raise ValueError('Personal preference requires existing business endpoints')
        return _ast('and',*(attainment(k) for k in keys))
    preference_ids={p['id'] for p in preferences}
    for r in relations:
        if not isinstance(r,dict) or not isinstance(r.get('id'),str):raise ValueError('Personal relation requires a string id')
        pid='apate:'+r['id']
        if pid in preference_ids:raise ValueError('Duplicate preference id: '+pid)
        preference_ids.add(pid)
        kind=r.get('kind')
        if kind=='choice':
            left,right=endpoint(r.get('source')),endpoint(r.get('target'))
            # A local comparison is inactive when neither alternative occurs.
            # Participation is a separately weighted preference.
            formula=['at_end',_ast('or',['not',_ast('or',left,right)],_ast('and',left,['not',right]))]
            label=str(r.get('source'))+' preferred_to '+str(r.get('target'))
        elif kind in {'optional_participation','temporal'}:
            template=r.get('formula')
            if kind=='optional_participation' and template not in {'sometime','never'}:raise ValueError('Participation uses sometime or never')
            if template not in {'sometime','never'} and r.get('y') is None:raise ValueError('Binary temporal preference requires y')
            formula=_temporal(template,endpoint(r.get('x')),endpoint(r['y']) if r.get('y') is not None else None)
            label=template+' '+str(r.get('x'))+(' / '+str(r['y']) if r.get('y') is not None else '')
        else:raise ValueError('Unsupported personal preference kind: '+str(kind))
        preferences.append({'id':pid,'name':'pref_apate_'+symbol(r['id']),'kind':kind,'label':r.get('label',label),'origin':'contextualization','formula':formula,'relation_id':r['id'],'support_ids':deepcopy(r.get('support_ids',[])),'pattern_ids':deepcopy(r.get('pattern_ids',[])),'rule_ids':deepcopy(r.get('rule_ids',[])),'translation':'PATPREF guarded local choice over paper attainment' if kind=='choice' else 'Table4 temporal template'})
    source_map['preferences']={p['id']:{k:deepcopy(p[k]) for k in ('name','origin','kind','relation_id','support_ids','pattern_ids','rule_ids','translation') if k in p} for p in preferences}
    pddl="; Liaskos et al. (2011), §4.2.3 and Table 4; literal PDDL3 templates.\n(:constraints\n  (and\n"+"\n".join("    (preference "+p["name"]+" "+_pddl(p["formula"])+")" for p in preferences)+"\n  )\n)\n"
    metric=None
    if paper_profile is not None:
        if not isinstance(paper_profile,dict) or not isinstance(paper_profile.get("weights"),dict):raise ValueError("paper_profile requires an explicit weights object")
        pref_byid={p["id"]:p for p in preferences}
        terms=[];total=0.0
        for key,weight in paper_profile["weights"].items():
            if key not in pref_byid:raise ValueError("Unknown paper-profile preference: "+key)
            if weight is None or isinstance(weight,str) and not weight.strip():weight=0
            if isinstance(weight,bool) or not isinstance(weight,(int,float)) or not math.isfinite(weight) or not 0<=weight<=1:raise ValueError("Paper-profile weight must be a finite number in [0,1]")
            total+=weight
            terms.append("(* "+format(weight,".15g")+" (is-violated "+pref_byid[key]["name"]+"))")
        penalty="(+ "+" ".join(terms)+")" if terms else "0"
        metric="(:metric maximize (- "+format(total,".15g")+" "+penalty+"))"
        pddl+="; Explicit independent paper profile; never inferred from persona.\n"+metric+"\n"
    else:warnings.append("No numeric metric emitted: PATPREF persona does not supply paper-profile weights.")

    domain=["; PATPREF translation of Liaskos et al. (2011); original SHOP2 execution.","(defdomain apate_domain ("]
    for op in operators:
        domain.append("  (:operator ("+op["name"]+") "+_preconditions(op["precondition"])+" () (("+op["add"][0]+")))")
    for method in methods:
        tasks=" ".join("("+s+")" for s in method["subtasks"])
        network="(:unordered "+tasks+")" if method["ordering"]=="unordered" else "("+tasks+")"
        domain.append("  (:method ("+method["task"]+") "+_preconditions(method["precondition"])+" "+network+")")
    domain.append("))")
    root_info=source_map["nodes"][original["root"]]
    root_task=root_info["operator"] if nodes[original["root"]]["kind"]=="task" else root_info["htn_task"]
    problem="(defproblem apate_problem apate_domain () (("+root_task+")))\n"
    ir={"compiler":COMPILER_VERSION,"model_hash":model_hash(original),"operators":operators,"methods":methods,"attainment":{k:attainment(k) for k,n in nodes.items() if n["kind"] in BUSINESS},"qualities":{k:quality(k) for k,n in nodes.items() if n["kind"] in QUALITY},"preferences":preferences,"metric":metric,"initial_state":[],"root_task":root_task,"paper_trace":{"optional":"Fig.2(A)/§4.2.1","operators_attainment":"Fig.2(B)/§4.2.2","methods":"Fig.2(C,D)/§4.2.2","quality":"Fig.2(E)/§4.2.3","temporal":"Table4","metric":"§4.2.4"}}
    steps=[
      {'id':'S1','title':'Eliminate optional subgoals','paper_reference':'§4.2.1 · Fig.2(A) · PDF p8','description':'Replace optional children with an OR wrapper(original, dummy). Original pre/npr endpoints remain connected to original; an operator is also generated for dummy, which is removed when displaying the business plan.','counts':{'optional':len(wrappers),'wrappers':len(wrappers),'dummy_operators':len(dummies)},'items':[{'original':key,'wrapper':wrapper,'OR_children':[key,'__skip_'+key],'dummy_operator':source_map['nodes']['__skip_'+key]['operator']} for key,wrapper in wrappers.items()]},
      {'id':'S2','title':'Convert mandatory decomposition','paper_reference':'§4.2.2 · Fig.2(B–D) · PDF p8–9','description':'Task → performance predicate/operator; goal → HTN task and attainment. AND → unordered method; OR → one method per child. Task guards go on the operator; goal guards go on the method.','counts':{'operators':len(operators),'methods':len(methods),'hard_constraints':len(original.get('hard_constraints',[]))},'items':{'operators':operators,'methods':methods,'attainment':ir['attainment']}},
      {'id':'S3','title':'Convert preferences and temporal relations','paper_reference':'§4.2.3 · Fig.2(E) · Table4 · PDF p9–10','description':'Quality and task choice use at-end formulas; participation and temporal relations use the seven templates. Validated PATPREF additions and existing preferences share the same formula layer.','counts':{'base_preferences':sum(p.get('origin')=='base' for p in preferences),'contextualized_preferences':len(relations),'total':len(preferences)},'items':[{**p,'pddl':_pddl(p['formula'])} for p in preferences]},
      {'id':'S4','title':'Construct a manually weighted metric','paper_reference':'§4.2.4 · PDF p10','description':'Researcher-provided weights in [0,1]. f=Σw−Σ(w×is-violated)=the sum of weights for satisfied preferences; empty items count as 0 and are not inferred from the persona.','counts':{'explicit_weights':len((paper_profile or {}).get('weights',{}))},'items':{'weights':deepcopy((paper_profile or {}).get('weights',{})),'metric':metric}},
      {'id':'S5','title':'Define planning problem','paper_reference':'§4.2.5 · PDF p10','description':'Initial state I={}; high-level task G=[a_root]. Original SHOP2 generates feasible plans, then the same preference formula and manual metric evaluate execution branches and ordering.','counts':{'initial_predicates':0,'root_tasks':1},'items':{'initial_state':[],'root':original['root'],'root_task':root_task,'shop2_problem':problem}}
    ]
    return {"source_model":original,"normalized_model":normalized,"ir":ir,"shop2_domain":"\n".join(domain)+"\n","shop2_problem":problem,"pddl_preferences":pddl,"source_map":source_map,"dummy_tasks":dummies,"warnings":list(dict.fromkeys(warnings)),"paper_profile":deepcopy(paper_profile),"contextualized_relations":relations,"transformation_steps":steps,"compiler":COMPILER_VERSION}
