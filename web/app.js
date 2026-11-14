'use strict';

const $=id=>document.getElementById(id);
const copy=value=>JSON.parse(JSON.stringify(value));
const WORKSPACE_KEY='apate.contextualization.workspace';
const FACET_DESCRIPTIONS={
  'Sociability':'Enjoys social contact and reciprocal interaction.',
  'Assertiveness':'Expresses opinions and personal boundaries.',
  'Energy Level':'Shows activity, enthusiasm and sustained energy.',
  'Compassion':'Attends to other people\'s difficulties and well-being.',
  'Respectfulness':'Treats others with consideration and respect.',
  'Trust':'Tends to expect good intentions from other people.',
  'Organization':'Prefers order, structure and organized materials.',
  'Productiveness':'Works persistently toward completing tasks.',
  'Responsibility':'Follows through on commitments and obligations.',
  'Anxiety':'Tends to worry or anticipate possible difficulties.',
  'Depression':'Tends to experience low mood and discouragement.',
  'Emotional Volatility':'Tends to experience strong or shifting emotions.',
  'Intellectual Curiosity':'Enjoys understanding ideas and exploring explanations.',
  'Aesthetic Sensitivity':'Attends to beauty, artistic expression and aesthetic experiences.',
  'Creative Imagination':'Enjoys imagining possibilities and generating ideas.'
};
// Generated expression portraits supplement the written facet labels.
const FACET_SYMBOLS={
  'Sociability':0,
  'Assertiveness':1,
  'Energy Level':2,
  'Compassion':3,
  'Respectfulness':4,
  'Trust':5,
  'Organization':6,
  'Productiveness':7,
  'Responsibility':8,
  'Anxiety':9,
  'Depression':10,
  'Emotional Volatility':11,
  'Intellectual Curiosity':12,
  'Aesthetic Sensitivity':13,
  'Creative Imagination':14
};
const AVATAR_COLUMNS=[0,352,665,985,1310,1619],AVATAR_ROWS=[0,330,620,971];
function facetAvatar(slot){
  if(slot===undefined)return '';
  const col=slot%5,row=Math.floor(slot/5),x=AVATAR_COLUMNS[col],y=AVATAR_ROWS[row],width=AVATAR_COLUMNS[col+1]-x,height=AVATAR_ROWS[row+1]-y,scale=28/Math.max(width,height);
  const style=`width:${width*scale}px;height:${height*scale}px;background-size:${1619*scale}px ${971*scale}px;background-position:${-x*scale}px ${-y*scale}px`;
  return `<span class="facet-symbol" aria-hidden="true"><span class="facet-avatar-frame" style="${style}"></span></span>`;
}
const state={workspace:null,bootstrap:null,viewer:null,view:'original',dirty:false,inputVersion:0,modelRequest:0,contextRequest:0,busy:0,selection:null};
const escapeHTML=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

async function api(path,method='GET',body){
  let response;
  try{response=await fetch(path,{method,headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});}
  catch(_){throw new Error('The local service could not be reached. Try again.');}
  const value=await response.json().catch(()=>({}));
  if(!response.ok){const message=typeof value.error==='string'?value.error:value.error?.message || value.message || 'The request could not be completed.';const error=new Error(message);error.status=response.status;throw error;}
  return value;
}
function notify(message,type='info'){$('notice').textContent=message;$('notice').className='notice '+type;$('notice').hidden=!message;}
function currentResult(){const result=state.dirty?null:state.workspace?.result;return result?.status==='complete'&&result.is_final!==false?result:null;}
function workspacePath(suffix=''){if(!state.workspace?.id)throw new Error('Import a model first.');return '/api/workbench/'+encodeURIComponent(state.workspace.id)+suffix;}
function rememberedWorkspace(){try{const id=localStorage.getItem(WORKSPACE_KEY);return typeof id==='string'&&/^[A-Za-z0-9_-]{1,128}$/.test(id)?id:null;}catch(_){return null;}}
function rememberWorkspace(id){try{if(id)localStorage.setItem(WORKSPACE_KEY,id);else localStorage.removeItem(WORKSPACE_KEY);}catch(_){}}
function taskReferences(diagram=state.workspace?.diagram){
  const tasks=(diagram?.nodes || []).filter(n=>n.kind==='task'&&!n.dependum),supplied=diagram?.task_refs || {};
  const valid=tasks.every(n=>/^t[1-9][0-9]*$/.test(supplied[n.id] || ''))&&new Set(tasks.map(n=>supplied[n.id])).size===tasks.length;
  return valid?Object.fromEntries(tasks.map(n=>[n.id,supplied[n.id]])):Object.fromEntries(tasks.map((n,i)=>[n.id,'t'+(i+1)]));
}
function formatReference(value,diagram=state.workspace?.diagram){
  if(Array.isArray(value))return '{'+value.map(v=>formatReference(v,diagram)).join(', ')+'}';
  if(value&&typeof value==='object')return formatReference(value.tasks || value.goal || value.id || '',diagram);
  const id=String(value??''),ref=taskReferences(diagram)[id],node=(diagram?.nodes || []).find(n=>n.id===id);
  return ref || node?.label || id;
}
function preferenceLabel(preference,diagram=state.workspace?.diagram){
  const x=formatReference(preference.x ?? preference.source,diagram),y=formatReference(preference.y ?? preference.target,diagram);
  if(preference.kind==='choice'||preference.type==='preferred_to')return x+' preferred to '+y;
  return ({sometime:()=> 'Sometime '+x,never:()=> 'Never '+x,precedes:()=>x+' precedes '+y,require_before:()=> 'Require '+x+' before '+y,require_after:()=> 'Require '+x+' after '+y,never_before:()=> 'Never '+x+' before '+y,never_after:()=> 'Never '+x+' after '+y}[preference.formula] || (()=>preference.label || x))();
}
function modelSummary(workspace){const d=workspace.diagram || {};return `${(d.nodes || []).length} elements · ${(d.actors || []).length} actors · ${(d.nodes || []).filter(n=>n.kind==='task'&&!n.dependum).length} tasks`;}
function capturePersona(){
  const original=state.workspace?.persona || {};
  return {actor_id:original.actor_id || 'Persona_'+String(state.workspace?.id || 'local').slice(0,12),name:$('actorName').value.trim(),role_ids:[...document.querySelectorAll('#roleChoices input:checked')].map(i=>i.value),facets:[...document.querySelectorAll('#facetChoices input:checked')].map(i=>i.value),description:$('personaDescription').value.trim()};
}
function setBusy(label,active){
  state.busy=Math.max(0,state.busy+(active?1:-1));
  document.body.classList.toggle('is-busy',state.busy>0);
  $('busyStatus').textContent=state.busy?label:'';
  $('contextualizeLabel').textContent=state.busy&&label.startsWith('Contextualizing')?'Contextualizing…':'Contextualize model';
  renderControls();
}
async function withBusy(label,callback){setBusy(label,true);try{return await callback();}catch(error){notify(error.message || 'The request could not be completed.','error');return null;}finally{setBusy('',false);}}
function renderControls(){
  const has=!!state.workspace,result=currentResult(),busy=state.busy>0;
  $('chooseModelButton').disabled=busy;$('pasteImportButton').disabled=busy;$('loadExampleButton').disabled=busy||!$('referenceSelect').value;
  $('personaFields').disabled=!has;$('contextualizeButton').disabled=!has||busy;
  $('originalButton').disabled=!has;$('contextualizedButton').disabled=!result;
  $('downloadModelButton').disabled=!result||busy;$('downloadSvgButton').disabled=!has;$('downloadPngButton').disabled=!has||busy;
  ['autoLayoutButton','fitButton','zoomOutButton','zoomInButton'].forEach(id=>$(id).disabled=!has);
}
function renderPersona(){
  const p=state.workspace?.persona || {},actors=(state.workspace?.diagram?.actors || []).filter(a=>a.kind==='role'),roles=p.role_ids || [],facets=p.facets || [];
  $('actorName').value=p.name || '';$('personaDescription').value=p.description || '';
  $('roleChoices').innerHTML=actors.length?actors.map(actor=>`<label class="role-choice"><input type="checkbox" value="${escapeHTML(actor.id)}" ${roles.includes(actor.id)||(roles.length===0&&actors.length===1)?'checked':''}><span>${escapeHTML(actor.label || actor.id)}</span></label>`).join(''):'<p class="muted">Import a model with an explicit Role to assign this persona.</p>';
  $('facetChoices').innerHTML=(state.bootstrap?.facets || []).map(facet=>{
    const visual=facetAvatar(FACET_SYMBOLS[facet]);
    return `<label class="facet-choice" title="${escapeHTML(FACET_DESCRIPTIONS[facet] || facet)}"><input type="checkbox" value="${escapeHTML(facet)}" ${facets.includes(facet)?'checked':''}>${visual}<span class="facet-label">${escapeHTML(facet)}</span></label>`;
  }).join('');
}
function renderSummary(){
  const workspace=state.workspace,result=currentResult();
  $('workspaceName').textContent=workspace?.name || 'Your model starts here';
  $('modelMeta').textContent=workspace?modelSummary(workspace):'Import an existing i* model to begin.';$('emptyState').hidden=!!workspace;
  $('viewTitle').textContent=state.view==='contextualized'?'Contextualized model':'Original model';
  $('resultSummary').textContent=state.view==='contextualized'&&result?`${(result.preferences || []).length} preference${(result.preferences || []).length===1?'':'s'}`:'';
  $('resultMessage').textContent=state.dirty?'Persona changed. Contextualize to update the model.':workspace?.result?.message || (workspace?'Add the persona you want to explore.':'The imported model provides the structure for contextualization.');
  for(const [id,view] of [['originalButton','original'],['contextualizedButton','contextualized']]){$(id).classList.toggle('active',state.view===view);$(id).setAttribute('aria-pressed',String(state.view===view));}
  renderControls();
}
function renderModel({fit=false}={}){
  if(!state.viewer||!state.workspace)return;
  const result=currentResult();
  state.viewer.render(state.workspace.diagram,{preferences:state.view==='contextualized'?(result?.preferences || []):[],persona:state.workspace.persona || {},view:state.view});
  if(fit)state.viewer.fit({readable:true});
}
function installWorkspace(workspace,{view,fit=true}={}){
  if(!workspace||typeof workspace.id!=='string'||!workspace.diagram||!Array.isArray(workspace.diagram.nodes)||!Array.isArray(workspace.diagram.actors)||!Array.isArray(workspace.diagram.links))throw new Error('The service returned an incomplete model.');
  state.workspace=copy(workspace);state.inputVersion++;state.dirty=false;state.selection=null;state.view=currentResult()?(view || 'contextualized'):'original';
  rememberWorkspace(workspace.id);renderPersona();renderSummary();renderSelection();renderModel({fit});
}
function personaChanged(){
  if(!state.workspace)return;
  state.inputVersion++;state.dirty=true;state.view='original';state.selection=null;renderSummary();renderSelection();renderModel();
}
async function importDocument(documentText,filename=''){
  if(typeof documentText!=='string'||!documentText.trim())throw new Error('Choose a model file or paste its contents.');
  const request=++state.modelRequest;state.contextRequest++;
  const workspace=await api('/api/workbench/import','POST',{document:documentText,filename});
  if(request!==state.modelRequest)return {stale:true};
  installWorkspace(workspace,{view:'original'});notify('Model imported. Add your persona to contextualize it.','success');return workspace;
}
async function loadExample(exampleId){
  if(!exampleId)throw new Error('Choose an example first.');
  const request=++state.modelRequest;state.contextRequest++;
  const workspace=await api('/api/workbench/example','POST',{example_id:exampleId});
  if(request!==state.modelRequest)return {stale:true};
  installWorkspace(workspace);notify('Example loaded. You can customize its persona.','success');return workspace;
}
async function contextualizeModel(){
  if(!state.workspace)throw new Error('Import a model first.');
  const persona=capturePersona();
  if(!persona.name)throw new Error('Enter a persona name.');
  const version=state.inputVersion,id=state.workspace.id,request=++state.contextRequest;
  const workspace=await api(workspacePath('/contextualize'),'POST',{persona,revision:state.workspace.revision});
  if(state.workspace?.id!==id||state.inputVersion!==version||request!==state.contextRequest)return {stale:true};
  installWorkspace(workspace,{view:'contextualized',fit:false});notify('');return workspace;
}
function setView(view){if(!state.workspace||view==='contextualized'&&!currentResult())return;state.view=view;state.selection=null;renderSummary();renderSelection();renderModel();}
function selectElement(selected){
  const id=typeof selected==='string'?selected:selected?.id || selected?.get?.('id');
  const preference=selected?.preference || (currentResult()?.preferences || []).find(p=>p.id===id);
  const node=(state.workspace?.diagram?.nodes || []).find(n=>n.id===id),actor=(state.workspace?.diagram?.actors || []).find(n=>n.id===id);
  if(preference)state.selection={title:preferenceLabel(preference),text:preference.explanation || preference.rationale || (preference.kind==='choice'?'A preference over existing alternatives. The underlying business constraints remain in force.':'A temporal or participation preference over existing model elements.')};
  else if(node){const ref=taskReferences()[node.id],owner=(state.workspace.diagram.actors || []).find(a=>a.id===node.owner),description=[['softgoal','quality','hard_preference'].includes(node.kind)?'Quality':String(node.kind || 'Element').replace(/^./,c=>c.toUpperCase()),owner?.label,node.optional?'Optional':''].filter(Boolean).join(' · '),preferences=Array.isArray(selected?.preferences)?selected.preferences:[];state.selection={title:(ref?ref+' · ':'')+(node.label || node.id),text:[description,APATEIStarViewer.elementMeaning?.(node.kind),...preferences.map(p=>preferenceLabel(p))].filter(Boolean).join('\n')};}
  else if(actor){const ownedCount=state.workspace.diagram.nodes.filter(n=>n.owner===actor.id).length;state.selection={title:actor.label || actor.id,text:[String(actor.kind || 'Actor').replace(/^./,c=>c.toUpperCase()),APATEIStarViewer.elementMeaning?.(actor.kind),ownedCount?'Owns '+ownedCount+' model elements.':'The input model defines no internal goals, tasks, resources or qualities for this '+(actor.kind || 'actor')+'.'].filter(Boolean).join('\n')};}
  else if(selected?.link){const link=selected.link;state.selection={title:String(link.kind)+' relation',text:[APATEIStarViewer.linkMeaning?.(link.kind),'From: '+formatReference(link.source),'To: '+formatReference(link.target),'Source ID: '+link.id].filter(Boolean).join('\n')};}
  else if(selected?.assignment)state.selection={title:selected.assignment.actor+' plays '+selected.assignment.label,text:'The concrete persona plays this selected role. The other model roles retain their own scope.'};
  else if(selected?.kind==='persona')state.selection={title:selected.label,text:[APATEIStarViewer.elementMeaning?.('agent'),'Plays: '+(selected.persona.role_ids || []).map(id=>state.workspace.diagram.actors.find(a=>a.id===id)?.label || id).join(', ')].filter(Boolean).join('\n')};
  else state.selection=null;
  if(state.selection)state.selection.curveEditable=Boolean(selected?.curveEditable);
  renderSelection();
}
function renderSelection(){$('selectionDetail').hidden=!state.selection;$('selectionTitle').textContent=state.selection?.title || '';$('selectionText').textContent=state.selection?.text || '';$('resetCurveButton').hidden=!state.selection?.curveEditable;}
function download(filename,value,mime='application/json'){
  const url=URL.createObjectURL(new Blob([typeof value==='string'?value:JSON.stringify(value,null,2)],{type:mime})),link=document.createElement('a');link.href=url;link.download=filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),2000);
}
async function exportModel(){
  if(!currentResult())throw new Error('Contextualize the current persona before downloading its model.');
  const id=state.workspace.id,version=state.inputVersion,value=await api(workspacePath('/export'));
  if(state.workspace?.id!==id||version!==state.inputVersion||state.dirty)return {stale:true};
  download('PATPREF-contextualized-model.json',value);return value;
}
function exportSvg(){if(!state.workspace||!state.viewer)return;download('PATPREF-'+state.view+'-model.svg',state.viewer.exportSVG(),'image/svg+xml');}
async function exportPng(){if(!state.workspace||!state.viewer)return;const blob=await state.viewer.exportPNG();const url=URL.createObjectURL(blob),anchor=document.createElement('a');try{anchor.href=url;anchor.download='PATPREF-'+state.view+'-model.png';anchor.click();}finally{URL.revokeObjectURL(url);}}
async function bootstrap(){
  try{
    state.bootstrap=await api('/api/workbench/bootstrap');
    $('referenceSelect').innerHTML='<option value="">Choose an example</option>'+(state.bootstrap.examples || []).map(ex=>`<option value="${escapeHTML(ex.id)}">${escapeHTML(ex.label || ex.id)}</option>`).join('');
    const renderer=state.bootstrap.renderer || {};$('rendererAttribution').textContent=(renderer.name || 'piStar')+' · '+(renderer.standard || 'iStar 2.0');
    state.viewer=new APATEIStarViewer($('modelCanvas'),{onSelect:selectElement});
    const remembered=rememberedWorkspace();
    if(remembered){try{installWorkspace(await api('/api/workbench/'+encodeURIComponent(remembered)));return;}catch(error){if(error.status===404)rememberWorkspace(null);else throw error;}}
    renderPersona();renderSummary();renderSelection();
  }catch(error){notify(error.message || 'The workspace could not be loaded.','error');}
}
function bindEvents(){
  $('chooseModelButton').addEventListener('click',()=>$('modelInput').click());
  $('modelInput').addEventListener('change',event=>{const file=event.target.files?.[0];if(!file)return;void withBusy('Importing model…',async()=>{try{return await importDocument(await file.text(),file.name);}finally{event.target.value='';}});});
  $('pasteImportButton').addEventListener('click',()=>void withBusy('Importing model…',()=>{const text=$('pasteModel').value;return importDocument(text,text.trimStart().startsWith('<')?'pasted-model.xml':'pasted-model.json');}));
  $('referenceSelect').addEventListener('change',renderControls);$('loadExampleButton').addEventListener('click',()=>void withBusy('Loading model…',()=>loadExample($('referenceSelect').value)));
  $('personaForm').addEventListener('submit',event=>{event.preventDefault();void withBusy('Contextualizing model…',contextualizeModel);});
  ['actorName','personaDescription'].forEach(id=>$(id).addEventListener('input',personaChanged));['roleChoices','facetChoices'].forEach(id=>$(id).addEventListener('change',personaChanged));
  $('originalButton').addEventListener('click',()=>setView('original'));$('contextualizedButton').addEventListener('click',()=>setView('contextualized'));
  $('autoLayoutButton').addEventListener('click',()=>{state.selection=null;renderSelection();state.viewer?.autoLayout?.();$('resultMessage').textContent='Components and curves arranged.';});$('fitButton').addEventListener('click',()=>state.viewer?.fit());$('zoomOutButton').addEventListener('click',()=>state.viewer?.zoomBy(1/1.2));$('zoomInButton').addEventListener('click',()=>state.viewer?.zoomBy(1.2));
  $('downloadModelButton').addEventListener('click',()=>void withBusy('Preparing model…',exportModel));$('downloadSvgButton').addEventListener('click',()=>{try{exportSvg();}catch(error){notify(error.message,'error');}});
  $('downloadPngButton').addEventListener('click',()=>void withBusy('Preparing PNG…',exportPng));
  $('clearSelectionButton').addEventListener('click',()=>{state.selection=null;state.viewer?.clearFocus?.();renderSelection();});
  $('resetCurveButton').addEventListener('click',()=>state.viewer?.resetSelectedCurve?.());
}

bindEvents();bootstrap();
