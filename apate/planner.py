"""Execute fixed original SHOP2 in ABCL; retain raw plans and search limits."""
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json
import math
import re
import shutil
import subprocess
import time

from .compiler import compile_model
from .semantics import validate_plan

ROOT=Path(__file__).resolve().parents[1]
VENDOR_DIR=ROOT/'vendor'
PLAN_LINE=re.compile(r'^APATE_PLAN\|([!A-Za-z0-9_,]*)$',re.MULTILINE)

def _integrity(path,digest):
    return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==digest

def engine_status():
    """Check local prerequisites and exact vendored sources; no process execution."""
    java=shutil.which('java')
    manifest_path=VENDOR_DIR/'manifest.json'
    manifest={}
    errors=[]
    if manifest_path.is_file():
        try:manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        except (OSError,ValueError):errors.append('vendor_manifest_invalid')
    else:errors.append('vendor_manifest_missing')
    if not java:errors.append('java_not_found')
    for component in ('shop2','abcl'):
        entry=manifest.get(component,{})
        if not entry or not _integrity(VENDOR_DIR/entry.get('file','__missing__'),entry.get('sha256')):errors.append(component+'_missing_or_hash_mismatch')
        for dependency in entry.get('dependencies',[]):
            if not _integrity(VENDOR_DIR/dependency['file'],dependency['sha256']):errors.append(component+'_dependency_missing_or_hash_mismatch')
    return {'status':'ready' if not errors else 'unavailable','available':not errors,'engine':'original-SHOP2','runtime':'ABCL 1.9.2 / Java','java':java,'shop2':manifest.get('shop2',{}),'abcl':manifest.get('abcl',{}),'htnplan_p':{'status':'source_not_available','description':'Original HTNPlan-P and authors translator have not been obtained; this adapter executes their genuine public SHOP2 upstream.'},'preference_optimization':False,'errors':errors}

def _lisp_string(value):
    return '"'+str(value).replace('\\','\\\\').replace('"','\\"')+'"'

def _driver(shop_path,domain_path,problem_path,max_plans,dependencies=None):
    additional_loads='\n'.join('    (load '+_lisp_string(path.as_posix())+')' for path in dependencies or [])
    return f'''(handler-case
  (progn
    (load {_lisp_string(shop_path.as_posix())})
{additional_loads}
    (format t "~&APATE_ENGINE|ORIGINAL_SHOP2~%")
    (load {_lisp_string(domain_path.as_posix())})
    (load {_lisp_string(problem_path.as_posix())})
    (defparameter *apate-plan-count* 0)
    (defparameter *apate-limit-hit* nil)
    (defun plan-found-hook (state which plan cost depth)
      (declare (ignore state which cost depth))
      (let ((names (mapcar (lambda (op) (symbol-name (car op))) (shorter-plan plan))))
        (format t "~&APATE_PLAN|~{{~A~^,~}}~%" names)
        (finish-output))
      (incf *apate-plan-count*)
      (when (>= *apate-plan-count* {max_plans})
        (setf *apate-limit-hit* t)
        (throw 'apate-plan-limit t)))
    (catch 'apate-plan-limit
      (find-plans 'apate_problem :which :all :verbose nil :optimize-cost nil))
    (format t "~&APATE_TERMINATION|~A~%" (if *apate-limit-hit* "PLAN_LIMIT" "SEARCH_COMPLETE"))
    (finish-output)
    (ext:quit :status 0))
  (error (condition)
    (format *error-output* "~&APATE_ENGINE_ERROR|~A~%" condition)
    (finish-output *error-output*)
    (ext:quit :status 2)))
'''

def _text(value):
    return value.decode('utf-8',errors='replace') if isinstance(value,bytes) else value or ''

def _bounded_log(value):
    if len(value)<=24000:return value
    return value[:4000]+'\n[PATPREF: middle of log omitted]\n'+value[-20000:]

def _plans(stdout,compilation):
    mapping=compilation['source_map']['operators']
    dummies=set(compilation['dummy_tasks'])
    found=[]
    for line in PLAN_LINE.findall(stdout.replace('\r\n','\n')):
        raw=[name.lower() for name in line.split(',') if name]
        if any(name not in mapping for name in raw):raise ValueError('SHOP2 returned an unmapped operator')
        sequence=[mapping[name] for name in raw]
        found.append({'raw_operators':raw,'normalized_sequence':sequence,'business_sequence':[key for key in sequence if key not in dummies],'removed_dummy_tasks':[key for key in sequence if key in dummies],'source':'original-SHOP2',
                      'normalized_validation':validate_plan(compilation['normalized_model'],sequence)})
    return found

def run_planner(compilation,max_plans=3,timeout=15,run_dir=None):
    """Execute only newly canonicalized compiler output, never caller-supplied Lisp.

    Finding max_plans stops the upstream search using its documented plan hook.
    Reaching that bound cannot prove exhaustion or optimality. The parent process
    owns wall-clock timeout, including JVM startup, and captures partial results.
    """
    start=time.monotonic()
    engine=engine_status()
    base={'status':'unavailable','plans':[],'engine':engine,'elapsed':0.0,'stdout':'','stderr':'','search_complete':False,'preference_optimized':False}
    if not engine['available']:
        base['stderr']='; '.join(engine['errors']);return base
    if isinstance(max_plans,bool) or not isinstance(max_plans,int) or not 1<=max_plans<=50:raise ValueError('max_plans must be an integer from 1 to 50')
    if isinstance(timeout,bool) or not isinstance(timeout,(int,float)) or not math.isfinite(timeout) or not 0<timeout<=120:raise ValueError('timeout must be greater than zero and at most 120 seconds')
    try:
        if not isinstance(compilation,dict) or 'source_model' not in compilation:raise ValueError('A compile_model result with source_model is required')
        canonical=compile_model(compilation['source_model'],compilation.get('paper_profile'),compilation.get('contextualized_relations'))
        for key in ('shop2_domain','shop2_problem','source_map','dummy_tasks','ir','pddl_preferences'):
            if canonical[key]!=compilation.get(key):raise ValueError('Compilation was modified after canonical generation: '+key)
    except (TypeError,ValueError,KeyError) as exc:
        base.update(status='invalid_compilation',stderr=str(exc),elapsed=round(time.monotonic()-start,4));return base
    if run_dir is not None:
        directory=Path(run_dir).resolve();directory.mkdir(parents=True,exist_ok=True)
        # The server supplies its own session directory. No path is taken from
        # compilation contents, and generated file names remain fixed.
        manager=None
    else:
        manager=TemporaryDirectory(prefix='apate_shop2_');directory=Path(manager.name)
    try:
        domain_path=directory/'domain.lisp';problem_path=directory/'problem.lisp';driver_path=directory/'run.lisp'
        domain_path.write_text(canonical['shop2_domain'],encoding='utf-8')
        problem_path.write_text(canonical['shop2_problem'],encoding='utf-8')
        shop_path=(VENDOR_DIR/engine['shop2']['file']).resolve()
        jar_path=(VENDOR_DIR/engine['abcl']['file']).resolve()
        dependencies=[(VENDOR_DIR/d['file']).resolve() for d in engine['shop2'].get('dependencies',[])]
        driver_path.write_text(_driver(shop_path,domain_path,problem_path,max_plans,dependencies),encoding='utf-8')
        command=[engine['java'],'--add-opens=java.base/java.lang=ALL-UNNAMED','-Xmx512m','-jar',str(jar_path),'--noinform','--noinit','--nosystem','--batch','--load',str(driver_path)]
        try:
            completed=subprocess.run(command,cwd=directory,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout,stdin=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            stdout,stderr=completed.stdout,completed.stderr
            timed_out=False;returncode=completed.returncode
        except subprocess.TimeoutExpired as exc:
            stdout,stderr=_text(exc.stdout),_text(exc.stderr)
            timed_out=True;returncode=None
        plans=_plans(stdout,canonical)
        complete='APATE_TERMINATION|SEARCH_COMPLETE' in stdout and returncode==0 and not timed_out
        termination='time_limit' if timed_out else 'search_complete' if complete else 'plan_limit' if 'APATE_TERMINATION|PLAN_LIMIT' in stdout else 'engine_error'
        status='timeout' if timed_out else 'ok' if returncode==0 and plans else 'no_plan' if complete and not plans else 'error'
        base.update(status=status,plans=plans,stdout=_bounded_log(stdout),stderr=_bounded_log(stderr),search_complete=complete,termination=termination,returncode=returncode,elapsed=round(time.monotonic()-start,4),max_plans=max_plans,timeout=timeout)
        if run_dir is not None:
            (directory/'execution.json').write_text(json.dumps(base,ensure_ascii=False,indent=2),encoding='utf-8')
        return base
    except (OSError,ValueError) as exc:
        base.update(status='error',stderr=str(exc),elapsed=round(time.monotonic()-start,4));return base
    finally:
        if manager is not None:manager.cleanup()
