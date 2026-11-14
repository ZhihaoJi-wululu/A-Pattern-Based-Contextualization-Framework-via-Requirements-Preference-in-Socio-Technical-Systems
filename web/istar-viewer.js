/* PATPREF's diagram adapter for the unmodified piStar iStar 2.0 JointJS shapes.
 * Upstream source and license: web/vendor/pistar/manifest.json and LICENSE.
 * Personal preferences are an PATPREF overlay; imported graph identities stay fixed.
 */
(function (root) {
  'use strict';
  const COLORS={ink:'#20352b',line:'#3f5147',fill:'#e7f0df',actor:'#f7faf3',accent:'#a92e49'};
  function validChoicePreference(p,diagram){
    if(!p||p.kind!=='choice'||p.type!=='preferred_to'||typeof p.source!=='string'||typeof p.target!=='string'||p.source===p.target)return false;
    const nodes=new Map((diagram.nodes||[]).map(n=>[n.id,n]));
    if(!['goal','task'].includes(nodes.get(p.source)?.kind)||!['goal','task'].includes(nodes.get(p.target)?.kind))return false;
    const parents=id=>new Set((diagram.links||[]).filter(e=>e.kind==='or'&&e.source===id&&nodes.get(e.target)?.kind==='goal').map(e=>e.target));
    const a=parents(p.source),b=parents(p.target);return [...a].some(id=>b.has(id));
  }
  function projectedPreferences(diagram,preferences,view){
    const original=(diagram.temporal_preferences||[]).map(p=>({...p,origin:'original'}));
    return [...original,...(view==='contextualized'?(preferences||[]).filter(p=>validChoicePreference(p,diagram)):[])];
  }
  const SYMBOL={radius:70,cx:86,cy:86};
  const PERSONA_RADIUS=76, PLAY_GAP=230, SCOPE_GAP=2;
  const PERSONA_ROUTE_ID=Symbol('persona route obstacle');
  const PLAY_LABEL='play';
  const QUALITY_MEANING='An attribute used to evaluate alternatives, such as organized materials or privacy. Its target may be precise or approximate. Older inputs may call it a softgoal.';
  const ELEMENT_MEANINGS={actor:'An entity with goals and intentions.',role:'An abstract responsibility or function played by an agent.',agent:'A concrete individual or system that can play roles.',goal:'A desired state or outcome with clear achievement criteria.',task:'An activity or way of achieving an outcome.',resource:'Information or a physical object that is needed or provided.',quality:QUALITY_MEANING,softgoal:QUALITY_MEANING,hard_preference:'An imported quality criterion. '+QUALITY_MEANING};
  const LINK_MEANINGS={and:'All mandatory children are required. AND does not specify execution order.',or:'At least one alternative is sufficient; more than one may be selected when the input permits it.',make:'Sufficient positive evidence for satisfying the target Quality (++).',break:'Sufficient negative evidence against satisfying the target Quality (--).',help:'Weak positive evidence for satisfying the target Quality (+).',hurt:'Weak negative evidence against satisfying the target Quality (-).',pre:'At the target start, the source must already have been attained.',npr:'At the target start, the source must not yet have been attained.',dependency:'A depender relies on a dependee for the declared goal, task, resource or quality.',neededBy:'The resource is needed by the target task.',qualification:'The Quality describes a desired attribute of this goal, task or resource.'};
  const lines=(value,width=24,max=4)=>{
    const all=String(value || '').split(/\n/).flatMap(p=>{
      const words=p.split(/\s+/).filter(Boolean).flatMap(word=>word.length>width?(word.match(new RegExp('.{1,'+width+'}','gu')) || []):[word]);
      const rows=[];let row='';for(const word of words){if(row && (row+' '+word).length>width){rows.push(row);row=word;}else row+=(row?' ':'')+word;}if(row)rows.push(row);return rows;
    });
    if(all.length>max)return [...all.slice(0,max-1),all[max-1].slice(0,width-1)+'…'].join('\n');
    return all.join('\n');
  };
  const finite=v=>typeof v==='number' && Number.isFinite(v);
  function layoutDiagram(diagram){
    const nodes=diagram.nodes || [],actors=diagram.actors || [],links=diagram.links || [],positions=new Map(),bounds=new Map(),local=new Map(),byId=new Map(nodes.map(n=>[n.id,n]));
    const W=224,GAP=64,TOP=260,quality=n=>['quality','softgoal','hard_preference'].includes(n.kind),business=n=>['goal','task'].includes(n.kind)&&!n.dependum,height=n=>quality(n)?108:n.kind==='task'?108:80;
    const workAll=nodes.filter(business),workIds=new Set(workAll.map(n=>n.id)),globalParents=new Map(workAll.map(n=>[n.id,new Set()])),globalChildren=new Map(workAll.map(n=>[n.id,new Set()]));
    for(const e of links)if(['and','or'].includes(e.kind)&&workIds.has(e.source)&&workIds.has(e.target)&&e.source!==e.target){
      const pending=[e.target],seen=new Set();let cycle=false;
      while(pending.length){const id=pending.pop();if(id===e.source){cycle=true;break;}if(seen.has(id))continue;seen.add(id);pending.push(...globalParents.get(id));}
      if(!cycle){globalParents.get(e.source).add(e.target);globalChildren.get(e.target).add(e.source);}
    }
    const remaining=new Map([...globalParents].map(([id,p])=>[id,p.size])),depths=new Map(),queue=workAll.filter(n=>!remaining.get(n.id)).map(n=>n.id);
    for(const id of queue)depths.set(id,0);
    for(let i=0;i<queue.length;i++)for(const child of globalChildren.get(queue[i])){depths.set(child,Math.max(depths.get(child)||0,depths.get(queue[i])+1));remaining.set(child,remaining.get(child)-1);if(!remaining.get(child))queue.push(child);}
    for(const n of workAll)if(!depths.has(n.id))depths.set(n.id,0);
    for(const actor of actors){
      const members=nodes.filter(n=>n.owner===actor.id),work=members.filter(business),ids=new Set(work.map(n=>n.id)),parents=new Map(),children=new Map();
      for(const e of links){if(!['and','or'].includes(e.kind)||!ids.has(e.source)||!ids.has(e.target)||parents.has(e.source)||e.source===e.target)continue;let cursor=e.target,cycle=false;for(let guard=0;cursor&&guard<=work.length;guard++){if(cursor===e.source){cycle=true;break;}cursor=parents.get(cursor);}if(!cycle)parents.set(e.source,e.target);}
      for(const n of work){const parent=parents.get(n.id);if(parent){if(!children.has(parent))children.set(parent,[]);children.get(parent).push(n.id);}}
      const subtree=id=>[id,...(children.get(id)||[]).flatMap(subtree)],concerns=id=>new Set(links.filter(e=>['make','break','help','hurt'].includes(e.kind)&&subtree(id).includes(e.source)).map(e=>e.target));
      for(const [parent,siblings] of children){const sets=siblings.map(concerns),groups=[],seen=new Set();for(let i=0;i<siblings.length;i++){if(seen.has(i))continue;const component=[i];seen.add(i);for(let j=0;j<component.length;j++)for(let k=0;k<siblings.length;k++)if(!seen.has(k)&&[...sets[component[j]]].some(q=>sets[k].has(q))){seen.add(k);component.push(k);}groups.push(component.sort((a,b)=>a-b));}children.set(parent,groups.flatMap(group=>group.map(index=>siblings[index])));}
      const compose=id=>{
        const n=byId.get(id),h=height(n),childIds=children.get(id)||[],blocks=childIds.map(compose);
        if(!blocks.length)return {width:W,height:h,items:[{id,x:0,y:0,width:W,height:h,depth:depths.get(id)||0,band:'hierarchy',group:id}]};
        const wrapped=blocks.length>4,rows=[];
        if(wrapped){const branches=blocks.filter(b=>b.items.length>1),leaves=blocks.filter(b=>b.items.length===1);const columns=Math.min(4,Math.max(2,Math.ceil(Math.sqrt(branches.length*2)))),components=[];for(const b of branches){const id=b.items[0].id,set=concerns(id),prior=components.find(group=>group.some(value=>[...concerns(value.items[0].id)].some(q=>set.has(q))));if(prior)prior.push(b);else components.push([b]);}for(const component of components){if(component.length>columns){for(let i=0;i<component.length;i+=columns)rows.push(component.slice(i,i+columns));continue;}let row=rows.find(row=>row.length+component.length<=columns);if(!row)rows.push(row=[]);row.push(...component);}if(leaves.length){const leafRow={width:leaves.reduce((v,b)=>v+b.width,0)+GAP*(leaves.length-1),height:Math.max(...leaves.map(b=>b.height)),items:[],leafBlock:true};let x=0;for(const b of leaves){leafRow.items.push(...b.items.map(p=>({...p,x:p.x+x})));x+=b.width+GAP;}rows.push([leafRow]);}}
        else rows.push(blocks);
        const widths=rows.map(row=>row.reduce((v,b)=>v+b.width,0)+GAP*(row.length-1)),width=Math.max(W,...widths),items=[{id,x:(width-W)/2,y:0,width:W,height:h,depth:depths.get(id)||0,band:'hierarchy',group:id}];let y=h+(wrapped?220:130);
        for(let r=0;r<rows.length;r++){let x=wrapped&&rows[r].length>1?0:(width-widths[r])/2;const headHeight=Math.max(...rows[r].map(b=>b.items[0].height));for(const b of rows[r]){const centreOffset=(headHeight-b.items[0].height)/2;items.push(...b.items.map(p=>({...p,x:p.x+x,y:p.y+y+centreOffset,group:wrapped?id+':'+r:p.group})));x+=b.width+GAP;}y+=Math.max(...rows[r].map(b=>b.height))+(wrapped?(rows[r+1]?.every(b=>b.leafBlock)?180:320):0);}
        return {width,height:Math.max(...items.map(p=>p.y+p.height)),items};
      };
      const rootDepth=Math.min(...work.filter(n=>!parents.has(n.id)).map(n=>depths.get(n.id)||0)),items=[];let next=0;for(const n of work.filter(n=>!parents.has(n.id))){const b=compose(n.id);items.push(...b.items.map(p=>({...p,x:p.x+next,y:p.y+TOP+(Number.isFinite(rootDepth)?rootDepth:0)*210})));next+=b.width+GAP;}
      const get=id=>items.find(p=>p.id===id),related=n=>links.filter(e=>['make','break','help','hurt'].includes(e.kind)&&e.target===n.id).map(e=>get(e.source)).filter(Boolean),qualityRows=new Map();
      for(const n of members.filter(quality)){
        const sources=related(n),groups=new Map();for(const p of sources){const y=items.filter(q=>q.group===p.group&&q.band==='hierarchy').reduce((v,q)=>Math.min(v,q.y),p.y);groups.set(y,(groups.get(y)||0)+1);}
        const groupTop=[...groups].sort((a,b)=>b[1]-a[1]||a[0]-b[0])[0]?.[0],y=groupTop===undefined?TOP:groupTop-160,wanted=sources.length?sources.reduce((v,p)=>v+p.x+p.width/2,0)/sources.length:W/2;
        if(!qualityRows.has(y))qualityRows.set(y,[]);qualityRows.get(y).push({n,wanted});
      }
      for(const [y,row] of qualityRows){row.sort((a,b)=>a.wanted-b.wanted);const used=[],slots=items.filter(p=>p.band==='hierarchy'&&!(children.get(p.id)||[]).length&&p.y>=y+160&&p.y<y+500).map(p=>p.x+p.width/2);for(const {n,wanted} of row){const candidates=[...slots].sort((a,b)=>Math.abs(a-wanted)-Math.abs(b-wanted)||a-b),centre=candidates.find(c=>used.every(value=>Math.abs(c-value)>=W+36));let x=centre===undefined?Math.max(0,wanted-W/2,...used.map(c=>c+W/2+36)):centre-W/2;while(items.some(p=>x<p.x+p.width+24&&x+W>p.x-24&&y<p.y+p.height+24&&y+108>p.y-24))x+=W+36;items.push({id:n.id,x,y,width:W,height:108,depth:null,band:'quality',group:null});used.push(x+W/2);}}
      let resourceX=0,resourceY=Math.max(TOP,...items.map(p=>p.y+p.height))+220;for(const n of members.filter(n=>n.kind==='resource')){items.push({id:n.id,x:resourceX,y:resourceY,width:W,height:80,depth:null,band:'resource',group:null});resourceX+=W+GAP;}
      if(!items.length){local.set(actor.id,{rx:160,ry:160,cx:0,cy:TOP+200,items:[]});continue;}
      const minX=Math.min(...items.map(p=>p.x)),maxX=Math.max(...items.map(p=>p.x+p.width)),minY=Math.min(...items.map(p=>p.y)),maxY=Math.max(...items.map(p=>p.y+p.height)),cx=(minX+maxX)/2,cy=(minY+maxY)/2;
      let rx=(maxX-minX)/2+150,ry=(maxY-minY)/2+150;
      const factor=Math.max(1,...items.flatMap(p=>[Math.hypot((p.x-cx)/rx,(p.y-cy)/ry),Math.hypot((p.x+p.width-cx)/rx,(p.y-cy)/ry),Math.hypot((p.x-cx)/rx,(p.y+p.height-cy)/ry),Math.hypot((p.x+p.width-cx)/rx,(p.y+p.height-cy)/ry)]));rx*=factor+.05;ry*=factor+.05;
      local.set(actor.id,{rx,ry,cx,cy,items});
    }
    const dependums=nodes.filter(n=>n.dependum),ordered=[...actors].sort((a,b)=>local.get(b.id).rx-local.get(a.id).rx);let nextActorX=240,bankX=null;
    for(const [i,actor] of ordered.entries()){const item=local.get(actor.id),{rx,ry,cx,cy}=item,x=nextActorX,b={x,y:cy-ry,width:rx*2,height:ry*2,rx,ry,radius:rx,symbolCx:rx,symbolCy:-SYMBOL.radius-SCOPE_GAP};bounds.set(actor.id,b);for(const p of item.items)positions.set(p.id,{...p,x:x+rx+p.x-cx});if(i===0&&dependums.length)bankX=x+b.width+88;nextActorX=x+b.width+(i===0&&dependums.length?400:160);}
    let outsideY=Math.min(TOP,...[...bounds.values()].map(b=>b.y+b.symbolCy-PERSONA_RADIUS))-200;for(const n of nodes.filter(n=>!n.owner&&!n.dependum)){const connected=[...(globalChildren.get(n.id)||[])].map(id=>positions.get(id)).filter(Boolean),x=connected.length?connected.reduce((v,p)=>v+p.x+p.width/2,0)/connected.length-W/2:nextActorX;positions.set(n.id,{id:n.id,x,y:outsideY,width:W,height:height(n),depth:depths.get(n.id)??null,band:business(n)?'hierarchy':quality(n)?'quality':'resource',group:n.id});outsideY-=height(n)+100;}
    const connectedY=id=>{const p=positions.get(id);return p?p.y+p.height/2:null;};let lastBottom=-Infinity;
    for(const entry of dependums.map(n=>({n,ys:links.filter(e=>e.source===n.id||e.target===n.id).map(e=>connectedY(e.source===n.id?e.target:e.source)).filter(finite)})).map(({n,ys})=>({n,wanted:ys.length?ys.reduce((a,b)=>a+b,0)/ys.length:TOP+500})).sort((a,b)=>a.wanted-b.wanted||nodes.indexOf(a.n)-nodes.indexOf(b.n))){const n=entry.n,h=height(n),y=Math.max(entry.wanted-h/2,lastBottom+80);positions.set(n.id,{id:n.id,x:bankX||nextActorX,y,width:W,height:h,depth:null,band:'dependum',group:null});lastBottom=y+h;}
    for(const n of nodes)if(!positions.has(n.id))positions.set(n.id,{id:n.id,x:nextActorX,y:outsideY,width:W,height:height(n),depth:null,band:quality(n)?'quality':'resource',group:null});
    const boxes=[...bounds.values(),...positions.values()];
    const headerTops=[...bounds.values()].map(b=>b.y+b.symbolCy-PERSONA_RADIUS);
    const dy=Math.max(0,180-Math.min(...boxes.map(p=>p.y)),32-Math.min(...headerTops));
    if(dy)for(const p of boxes)p.y+=dy;
    return {positions,bounds,globalDepths:depths,compactBranches:true,width:Math.max(900,...boxes.map(p=>p.x+p.width+160)),height:Math.max(600,...boxes.map(p=>p.y+p.height+220))};
  }
  const scopeClasses={};
  function circularScopeClass(name){
    if(!scopeClasses[name]){const Base=joint.shapes.istar[name];scopeClasses[name]=Base.extend({markup:Base.prototype.markup.replace(/<rect class="boundary"\s*\/>/,'<ellipse class="boundary"/>')});}
    return scopeClasses[name];
  }
  let referenceTaskClass;
  function taskWithReferenceClass(){
    if(!referenceTaskClass){const Base=joint.shapes.istar.Task;referenceTaskClass=Base.extend({markup:Base.prototype.markup+'<g class="task-reference"><circle class="task-reference-circle"/><text class="task-reference-text"/></g>'});}
    return referenceTaskClass;
  }
  function taskReferenceBadge(reference,width=224){
    const text=String(reference),radius=Math.max(16,Math.min(20,text.length*2+10));
    return {text,cx:width*15/130,cy:0,radius,fontSize:Math.min(14,(radius*2-8)/(text.length*.62))};
  }
  const supportsSourceLink=kind=>!['isa','participatesin','participatein'].includes(String(kind).replace(/[^a-z]/gi,'').toLowerCase().replace(/^source/,'').replace(/^istar/,'').replace(/link$/,''));
  function sourceLinkVisible(edge,diagram){
    if(!supportsSourceLink(edge.kind))return false;
    if(edge.kind==='plays')return diagram.actors.some(a=>a.id===edge.source&&a.kind==='agent')&&diagram.actors.some(a=>a.id===edge.target&&a.kind==='role');
    const localKinds=['and','or','make','break','help','hurt','neededBy','qualification'];
    if(![...localKinds,'dependency','pre','npr'].includes(edge.kind))return false;
    if(!localKinds.includes(edge.kind))return true;
    const owner=id=>diagram.nodes.find(n=>n.id===id)?.owner,targetOwner=owner(edge.target);
    if(!['and','or'].includes(edge.kind)&&(!targetOwner||owner(edge.source)!==targetOwner))return false;
    if(['and','or'].includes(edge.kind)){
      const group=diagram.links.filter(e=>e.kind===edge.kind&&e.target===edge.target);
      const work=id=>['goal','task'].includes(diagram.nodes.find(n=>n.id===id)?.kind);
      if(!work(edge.target)||group.some(e=>!work(e.source)))return false;
    }
    return true;
  }
  function endpointIds(value){if(typeof value==='string')return [value];if(Array.isArray(value))return value;if(value?.tasks)return value.tasks;if(value?.goal)return [value.goal];if(value?.id)return [value.id];return [];}
  function reference(value,diagram){const ids=endpointIds(value),names=ids.map(id=>diagram.task_refs?.[id] || diagram.nodes.find(n=>n.id===id)?.label || id);return names.length===1?names[0]:'{'+names.join(', ')+'}';}
  function preferenceLabel(p,diagram){
    if(p.kind==='choice' || p.type==='preferred_to')return reference(p.source,diagram)+' preferred_to '+reference(p.target,diagram);
    const x=reference(p.x,diagram),y=reference(p.y,diagram);
    return {sometime:`sometime ${x}`,never:`never ${x}`,precedes:`${x} precedes ${y}`,require_before:`require ${x} before ${y}`,require_after:`require ${x} after ${y}`,never_before:`never ${x} before ${y}`,never_after:`never ${x} after ${y}`}[p.formula] || p.label || p.id;
  }
  const preferenceCaption=(p,diagram)=>p.kind==='choice'||p.type==='preferred_to'?'preferred_to':p.formula?.replaceAll('_',' ') || preferenceLabel(p,diagram);
  function symbolAttributes(label,{radius=SYMBOL.radius,cx=SYMBOL.cx,cy=SYMBOL.cy,kind='actor'}={}){
    const scale=radius/40,text=lines(label,kind==='agent'?16:14,4),baseline=cy-(text.split('\n').length-1)*9+6;
    return {'.element':{fill:'#fff',stroke:COLORS.ink,'stroke-width':2,r:radius,cx,cy,transform:'translate(0,0)'},
      '.content':{text,'font-size':18,'font-family':'Arial, sans-serif','font-weight':'600',fill:COLORS.ink,ref:null,'ref-x':null,'ref-y':null,'ref-dy':null,x:cx,y:baseline,'text-anchor':'middle','x-alignment':null,'y-alignment':null,transform:'translate(0,0)'},
      '.actorDecorator':{display:kind==='actor'?'none':null,transform:`translate(${cx-20*scale},${cy-20*scale}) scale(${scale})`}};
  }
  function labelLink(edge,text,color,{distance=.55,offset=0,emphasis=false}={}){
    // Native piStar connection text is replaced by one horizontal, boxed label.
    edge.attr({label:{display:'none'},'label-background':{display:'none'}});
    const fontSize=emphasis?22:17,paddingX=emphasis?10:6,paddingY=emphasis?6:5;
    edge.set('labelGeometry',{fontSize,paddingX,paddingY});
    edge.labels([{position:{distance,offset,angle:0,args:{keepGradient:false,ensureLegibility:true}},attrs:{text:{text,fill:color,'font-size':fontSize,'font-family':'Arial, sans-serif','font-weight':emphasis?'700':'600'},rect:{fill:emphasis?'#fff6f8':'#fff',stroke:emphasis?color:'#c3cdc4','stroke-width':emphasis?1.4:.7,rx:emphasis?8:4,ry:emphasis?8:4,refX:-paddingX,refY:-paddingY,refWidth:paddingX*2,refHeight:paddingY*2}}}]);
  }
  function addLineHalo(edge,width=6){
    const source=edge.get('markup') || edge.markup;
    if(!Array.isArray(source))return;
    const markup=source.map(item=>({...item})),index=markup.findIndex(item=>item.selector==='line');
    if(index<0)return;markup.splice(index,0,{tagName:'path',selector:'apate-halo'});edge.set('markup',markup);
    edge.attr({'apate-halo':{connection:true,fill:'none',stroke:'#ffffff','stroke-width':width,'stroke-linecap':'round','stroke-linejoin':'round','pointer-events':'none'}});
  }
  function curveVertices(a,b,kind){
    if(!a||!b)return [];
    const dx=b.x-a.x,dy=b.y-a.y,length=Math.hypot(dx,dy);
    if(length<1)return [{x:a.x+140,y:Math.max(24,a.y-110)},{x:Math.max(24,a.x-140),y:Math.max(24,a.y-110)}];
    const bend=Math.min(120,Math.max(kind==='preference'?72:38,length*.13)),side=Math.abs(dx)>Math.abs(dy)?(dx>=0?1:-1):(dy>=0?-1:1);
    return [{x:Math.max(24,(a.x+b.x)/2-dy/length*bend*side),y:Math.max(24,(a.y+b.y)/2+dx/length*bend*side)}];
  }
  function routeLink(edge,kind,a,b){
    edge.router('normal');edge.connector('smooth');edge.vertices(curveVertices(a,b,kind));
  }
  function routingStorageKey(signature){
    let hash=2166136261,second=5381;for(let i=0;i<signature.length;i++){hash=Math.imul(hash^signature.charCodeAt(i),16777619);second=Math.imul(second,33)^signature.charCodeAt(i);}
    return 'apate.curves.v6.'+(hash>>>0).toString(16)+'.'+(second>>>0).toString(16)+'.'+signature.length;
  }
  const validVertices=value=>Array.isArray(value)&&value.length>0&&value.length<=8&&value.every(p=>p&&finite(p.x)&&finite(p.y)&&p.x>=0&&p.y>=0&&p.x<1e6&&p.y<1e6);
  let curveToolClass;
  function curveToolsClass(){
    if(!curveToolClass)curveToolClass=joint.linkTools.Vertices.extend({
      // Keep the bend point and complete the native drag batch in JointJS 3.4.4.
      onHandleChanged(handle,event){this.blur();this.relatedView.model.stopBatch('vertex-move',{ui:true,tool:this.cid});const [normalized]=this.paper.getPointerArgs(event);this.relatedView.checkMouseleave(normalized);},
      snapVertex(point,index){
        const {prev,next}=this.getNeighborPoints(index),dx=next.x-prev.x,dy=next.y-prev.y,length=Math.hypot(dx,dy);
        if(length>1){const offset=((point.x-prev.x)*-dy+(point.y-prev.y)*dx)/length;if(Math.abs(offset)<18){const old=this.relatedView.model.vertices()[index],oldOffset=old?((old.x-prev.x)*-dy+(old.y-prev.y)*dx)/length:1,shift=(offset<0?-18:offset>0?18:oldOffset<0?-18:18)-offset;point.x+=-dy/length*shift;point.y+=dx/length*shift;}}
        const bounds=this.options.bounds;point.x=Math.max(24,Math.min(bounds.width-24,point.x));point.y=Math.max(24,Math.min(bounds.height-24,point.y));
      }
    });
    return curveToolClass;
  }
  class IStarViewer {
    constructor(container,options={}){
      this.container=container;this.options=options;this.scale=1;this.signature='';this.curveRoutes=new Map();this.defaultRoutes=new Map();
      joint.connectors.apateFlow=(source,target,vertices,args={})=>{const path=root.APATEIStarRouting.flowPath([source,...vertices,target],args);return args.raw?joint.g.Path.parse(path):path;};
      this.graph=new joint.dia.Graph({}, {cellNamespace:joint.shapes});
      this.paper=new joint.dia.Paper({el:container,model:this.graph,width:1000,height:700,gridSize:1,drawGrid:false,defaultConnectionPoint:{name:'boundary'},interactive:view=>view.model.isLink()?{vertexMove:true,vertexRemove:false,vertexAdd:false,arrowheadMove:false,linkMove:false,labelMove:false,useLinkTools:false}:false,async:false,cellViewNamespace:joint.shapes,background:{color:'#ffffff'}});
      this.graph.on('change:vertices',(edge,vertices,opts)=>{if(opts?.ui&&edge.get('curveKey')){this.curveRoutes.set(edge.get('curveKey'),vertices.map(p=>({x:p.x,y:p.y})));this.saveCurves();const el=this.paper.findViewByModel(edge)?.el;if(el)el.dataset.curveVertices=JSON.stringify(vertices);}});
      this.paper.on('element:pointerclick',(view)=>{const id=view.model.get('sourceId'),node=this.diagram.nodes.find(n=>n.id===id) || this.diagram.actors.find(n=>n.id===id);this.focusCell(view.model.id);if(node)this.options.onSelect?.({...node,task_ref:this.diagram.task_refs?.[id],preferences:this.preferences.filter(p=>[...endpointIds(p.source),...endpointIds(p.target),...endpointIds(p.x),...endpointIds(p.y)].includes(id))});else if(view.model.id==='concrete-persona')this.options.onSelect?.({id,kind:'persona',label:this.persona.name,persona:this.persona});});
      this.paper.on('link:pointerclick',view=>{this.focusCell(view.model.id);this.showCurveTools(view);const p=view.model.get('apatePreference'),link=this.diagram.links.find(e=>e.id===view.model.get('sourceId')),assignment=view.model.get('roleAssignment');if(p)this.options.onSelect?.({id:p.id,kind:'preference',label:preferenceLabel(p,this.diagram),preference:p,curveEditable:true});else if(link)this.options.onSelect?.({id:link.id,kind:'link',link,curveEditable:true});else if(assignment)this.options.onSelect?.({kind:'role_assignment',assignment,curveEditable:true});});
      this.container.classList.add('istar-paper');
    }
    render(diagram,{preferences=[],persona={},view='original'}={}){
      if(!diagram?.nodes || !diagram?.actors)throw new Error('The imported i* diagram is incomplete.');
      this.renderOptions={preferences,persona,view};this.diagram=diagram;this.persona=persona;this.preferences=projectedPreferences(diagram,preferences,view);
      const signature=JSON.stringify(diagram),changed=signature!==this.signature;this.signature=signature;
      this.clearCurveTools();
      if(changed){this.layout=layoutDiagram(diagram);this.loadCurves();}
      this.defaultRoutes=new Map();
      this.graph.clear();this.cells=new Map();
      const {positions,bounds}=this.layout;
      for(const [i,a] of diagram.actors.entries()){
        const b=bounds.get(a.id),ownedCount=diagram.nodes.filter(n=>n.owner===a.id).length,Class=circularScopeClass({role:'Role',agent:'Agent'}[a.kind] || 'Actor');
        const cell=new Class({id:'actor-'+i,type:'istar.'+({role:'Role',agent:'Agent'}[a.kind] || 'Actor'),position:{x:b.x,y:b.y},size:{width:b.width,height:b.height},sourceId:a.id});
        cell.attr({'.boundary':{display:ownedCount?null:'none',width:null,height:null,rx:null,ry:null,cx:b.rx,cy:b.ry,r:null,rx:b.rx,ry:b.ry,fill:COLORS.actor,stroke:'#718268','stroke-width':1.6,'stroke-dasharray':'9 5'},...symbolAttributes(a.label,{kind:a.kind,cx:b.symbolCx,cy:b.symbolCy})});
        this.graph.addCell(cell);this.cells.set(a.id,cell);
      }
      for(const [i,n] of diagram.nodes.entries()){
        const p=positions.get(n.id),kind={task:'Task',quality:'Quality',softgoal:'Quality',hard_preference:'Quality',resource:'Resource'}[n.kind] || 'Goal',alias=diagram.task_refs?.[n.id],Class=kind==='Task'&&alias?taskWithReferenceClass():joint.shapes.istar[kind];
        const text=lines(n.label,21,4),fontSize=kind==='Goal'&&text.split('\n').length>3?17:20;
        const cell=new Class({id:'node-'+i,type:'istar.'+kind,position:{x:p.x,y:p.y},size:{width:p.width,height:p.height},sourceId:n.id});
        const isQuality=kind==='Quality',fill=isQuality?'#fff':n.kind==='resource'?'#eef3f6':COLORS.fill;
        cell.attr({'.element':{fill,stroke:COLORS.line,'stroke-width':1.7,...(kind==='Goal'?{rx:20,ry:12}:{})},'.content':{text,'font-size':fontSize,fill:COLORS.ink,'font-family':'Arial, sans-serif','font-weight':isQuality?'600':'400',ref:'.element','ref-x':0.5,'ref-y':0.5,'ref-dy':null,'y-alignment':'middle','text-anchor':'middle'}});
        if(kind==='Task'&&alias){const badge=taskReferenceBadge(alias,p.width);cell.attr({'.task-reference-circle':{cx:badge.cx,cy:badge.cy,r:badge.radius,fill:'#fff',stroke:'#6c568e','stroke-width':1.8},'.task-reference-text':{text:badge.text,x:badge.cx,y:badge.cy+badge.fontSize*.35,fill:'#6c568e','font-size':badge.fontSize,'font-family':'Arial, sans-serif','font-weight':'600','text-anchor':'middle',ref:null,'ref-x':null,'ref-y':null,'ref-dy':null,'x-alignment':null,'y-alignment':null,transform:'translate(0,0)','pointer-events':'none'}});}
        this.graph.addCell(cell);this.cells.set(n.id,cell);
        if(n.owner && this.cells.has(n.owner))this.cells.get(n.owner).embed(cell);
        if(n.optional){const optional=new joint.shapes.basic.Circle({id:'optional-'+i,position:{x:kind==='Task'?p.x+p.width-32:p.x+22,y:p.y-5},size:{width:10,height:10},attrs:{circle:{fill:'#fff',stroke:'#77866e','stroke-width':1.2}}});optional.set({apateDecoration:true,optionalFor:n.id});this.graph.addCell(optional);}
      }
      const classes={and:'AndRefinementLink',or:'OrRefinementLink',make:'ContributionLink',break:'ContributionLink',help:'ContributionLink',hurt:'ContributionLink',dependency:'DependencyLink',neededBy:'NeededByLink',qualification:'QualificationLink',plays:'DefaultContainerLink'};
      for(const [i,e] of (diagram.links || []).entries()){
        if(!sourceLinkVisible(e,diagram))continue;
        if(!this.cells.has(e.source)||!this.cells.has(e.target))continue;
        const Class=joint.shapes.istar[classes[e.kind]] || joint.shapes.istar.DefaultNodeLink;
        const edge=new Class({id:'edge-'+i,sourceId:e.id});
        edge.source({id:this.cells.get(e.source).id,selector:'.element'});edge.target({id:this.cells.get(e.target).id,selector:'.element'});routeLink(edge,e.kind,this.center(e.source),this.center(e.target));
        const label=e.kind==='plays'?PLAY_LABEL:({and:'AND',or:'OR',make:'++',break:'--',help:'+',hurt:'-',pre:'pre',npr:'npr',dependency:'D',neededBy:'needed by',qualification:'qualifies'}[e.kind] || e.label || e.source_value || e.kind);
        const color=COLORS.line;
        edge.attr({line:{stroke:color,'stroke-width':1.9,'stroke-dasharray':e.kind==='qualification'?'2 5':['make','break','help','hurt'].includes(e.kind)?'9 6':null}});
        addLineHalo(edge);
        if(!classes[e.kind] && !['pre','npr'].includes(e.kind)){edge.set('type','apate.SourceLink');edge.attr({line:{'stroke-dasharray':'4 4',targetMarker:{d:''}}});}
        if(e.kind!=='dependency'){
          const refinement=e.kind==='and'||e.kind==='or';
          labelLink(edge,label,color,refinement?{distance:.55}:{distance:.46+(i%3)*.1,offset:(i%2?1:-1)*9});
        }
        edge.set('sourceKind',e.kind);this.applyCurve(edge,JSON.stringify(['source',e.id]));this.graph.addCell(edge);edge.toBack();
      }
      if(this.preferences.length || (persona.name && persona.role_ids?.length)){
        for(const [i,p] of this.preferences.entries()){
          const prefColor=p.origin==='original'?'#79668d':COLORS.accent;
          if(['sometime','never'].includes(p.formula)){
            for(const id of endpointIds(p.x)){const cell=this.cells.get(id);if(cell)cell.attr('.element/stroke',prefColor).attr('.element/stroke-width',2.3);}
            continue;
          }
          const source=p.kind==='choice'||p.type==='preferred_to'?p.source:p.x,target=p.kind==='choice'||p.type==='preferred_to'?p.target:p.y;
          const a=this.endpoint(source),b=this.endpoint(target);if(!a||!b)continue;
          const edge=new joint.shapes.istar.DefaultNodeLink({id:'preference-'+i,type:'apate.Preference',apatePreference:p});
          edge.source(a);edge.target(b);routeLink(edge,'preference',this.endpointCenter(source),this.endpointCenter(target));
          const start=this.endpointCenter(source),end=this.endpointCenter(target),sourceNode=diagram.nodes.find(n=>n.id===endpointIds(source)[0]),targetNode=diagram.nodes.find(n=>n.id===endpointIds(target)[0]);
          if(p.kind==='choice'&&sourceNode?.owner&&sourceNode.owner===targetNode?.owner&&Math.abs(start.x-end.x)>350&&Math.abs(start.y-end.y)>80){
            const rowBottom=Math.max(...diagram.nodes.filter(n=>n.owner===sourceNode.owner).map(n=>{const box=positions.get(n.id);return box.y+box.height;}))+75,side=start.x>end.x?1:-1;
            edge.vertices([{x:start.x+side*150,y:rowBottom},{x:end.x-side*150,y:rowBottom}]);
          }
          edge.attr({line:{stroke:prefColor,'stroke-width':4.2,'stroke-dasharray':null,'stroke-linecap':'round',targetMarker:{d:'M 15 -8 L 0 0 L 15 8',fill:'none',stroke:prefColor,'stroke-width':2.8}}});
          addLineHalo(edge,8.2);
          labelLink(edge,preferenceCaption(p,diagram),prefColor,{distance:.5+(i%2)*.1,offset:-18,emphasis:true});
          this.applyCurve(edge,JSON.stringify(['preference',p.id,p.kind || p.type,p.formula,endpointIds(source),endpointIds(target)]));this.graph.addCell(edge);
        }
        const roles=(persona.role_ids || []).filter(id=>diagram.actors.some(a=>a.id===id&&a.kind==='role'));
        if(roles.length && persona.name){
          const roleCenter=this.center(roles[0]);
          const personaPosition={x:roleCenter.x-PLAY_GAP-SYMBOL.cx,y:roleCenter.y-SYMBOL.cy};
          const actor=new joint.shapes.istar.Agent({id:'concrete-persona',type:'istar.Agent',position:personaPosition,size:{width:180,height:180},sourceId:persona.actor_id});
          actor.attr({'.boundary':{display:'none'},...symbolAttributes(persona.name,{kind:'agent',radius:PERSONA_RADIUS})});this.graph.addCell(actor);
          for(const [i,id] of roles.entries()){
            const targetActor=diagram.actors.find(a=>a.id===id),assignment={actor:persona.name,role:id,label:targetActor?.label || id,kind:'plays'};
            const edge=new joint.shapes.istar.DefaultContainerLink({id:'persona-role-'+i,type:'apate.Plays',source:{id:actor.id,selector:'.element'},target:{id:this.cells.get(id).id,selector:'.element'},roleAssignment:assignment});routeLink(edge,'plays',{x:personaPosition.x+SYMBOL.cx,y:personaPosition.y+SYMBOL.cy},this.center(id));edge.attr({line:{stroke:'#315f88','stroke-width':2.3,'stroke-dasharray':null}});labelLink(edge,PLAY_LABEL,'#315f88',{distance:.5,offset:12});this.applyCurve(edge,JSON.stringify(['plays',persona.actor_id || persona.name,id]));this.graph.addCell(edge);edge.toBack();
          }
        }
      }
      // Owner backgrounds sit behind all relationships and intentional elements.
      for(const a of [...diagram.actors].reverse())this.cells.get(a.id).toBack();
      this.arrangeCurves();
      this.setScale(this.scale);
      if(changed)this.scrollToOrigin();
      for(const n of diagram.nodes){const element=this.paper.findViewByModel(this.cells.get(n.id))?.el;if(element){element.dataset.nodeId=n.id;element.dataset.ownerId=n.owner || '';const layoutNode=positions.get(n.id);element.dataset.layoutBand=layoutNode.band || '';if(layoutNode.depth!==null)element.dataset.hierarchyDepth=String(layoutNode.depth);if(diagram.task_refs?.[n.id])element.dataset.taskRef=diagram.task_refs[n.id];const linked=this.preferences.filter(p=>[...endpointIds(p.x),...endpointIds(p.y),...endpointIds(p.source),...endpointIds(p.target)].includes(n.id));element.dataset.preferenceIds=JSON.stringify(linked.map(p=>p.id));const title=document.createElementNS('http://www.w3.org/2000/svg','title');title.textContent=[diagram.task_refs?.[n.id],n.label,'Source: '+n.id,...linked.map(p=>preferenceLabel(p,diagram))].filter(Boolean).join(' · ');element.appendChild(title);}}
      for(const n of diagram.nodes){const el=this.paper.findViewByModel(this.cells.get(n.id))?.el,badge=el?.querySelector('.task-reference');if(badge){badge.dataset.taskBadge=diagram.task_refs[n.id];badge.dataset.taskId=n.id;}}
      for(const cell of this.graph.getElements())if(cell.get('optionalFor')){const el=this.paper.findViewByModel(cell)?.el;if(el)el.dataset.optionalFor=cell.get('optionalFor');}
      for(const a of diagram.actors){const el=this.paper.findViewByModel(this.cells.get(a.id))?.el,b=bounds.get(a.id);if(el){const ownedCount=diagram.nodes.filter(n=>n.owner===a.id).length;el.dataset.scopeId=a.id;el.dataset.symbolKind=a.kind;el.dataset.ownedCount=String(ownedCount);el.dataset.scopeState=ownedCount?'expanded':'actor-only';el.setAttribute('aria-label',(a.kind || 'Actor')+': '+a.label);for(const key of ['x','y','width','height'])el.dataset['scope'+key[0].toUpperCase()+key.slice(1)]=b[key];const title=document.createElementNS('http://www.w3.org/2000/svg','title');title.textContent=a.label+' · '+(ELEMENT_MEANINGS[a.kind] || ELEMENT_MEANINGS.actor);el.appendChild(title);}}
      const personaElement=this.graph.getCell('concrete-persona');if(personaElement){const el=this.paper.findViewByModel(personaElement)?.el;if(el){el.dataset.personaId=persona.actor_id || '';el.dataset.symbolKind='agent';}}
      for(const cell of this.graph.getLinks()){const el=this.paper.findViewByModel(cell)?.el;if(el){el.dataset.curveKey=cell.get('curveKey');el.dataset.curveVertices=JSON.stringify(cell.vertices());if(cell.get('sourceKind'))el.dataset.linkKind=cell.get('sourceKind');if(cell.get('sourceId'))el.dataset.sourceLinkId=cell.get('sourceId');if(cell.get('apatePreference'))el.dataset.preferenceId=cell.get('apatePreference').id;if(cell.get('roleAssignment')){el.dataset.assignmentRole=cell.get('roleAssignment').role;el.dataset.linkKind=cell.get('roleAssignment').kind;}const title=document.createElementNS('http://www.w3.org/2000/svg','title');title.textContent=cell.get('apatePreference')?preferenceLabel(cell.get('apatePreference'),diagram):cell.get('roleAssignment')?persona.name+' '+cell.get('roleAssignment').kind+' '+cell.get('roleAssignment').label:(LINK_MEANINGS[cell.get('sourceKind')] || cell.get('sourceKind') || 'Source relation');el.appendChild(title);}}
    }
    arrangeCurves(){
      const routing=root.APATEIStarRouting;if(!routing)return;
      const boxes=[...this.layout.positions].map(([id,b])=>({id,...b}));
      for(const [id,b] of this.layout.bounds)boxes.push({id,x:b.x+b.symbolCx-SYMBOL.radius,y:b.y+b.symbolCy-SYMBOL.radius,width:SYMBOL.radius*2,height:SYMBOL.radius*2});
      const persona=this.graph.getCell('concrete-persona');
      if(persona){
        const p=persona.position(),x=p.x+SYMBOL.cx-PERSONA_RADIUS,y=p.y+SYMBOL.cy-PERSONA_RADIUS;
        boxes.push({id:PERSONA_ROUTE_ID,x,y,width:PERSONA_RADIUS*2,height:PERSONA_RADIUS*2});
      }
      const occupied=[],labels=[],routed=[],stats={nodeIntersections:0,links:0};
      const end=value=>{if(value.id){const cell=this.graph.getCell(value.id),id=cell?.get('sourceId');if(persona&&cell===persona){const p=persona.position();return {point:{x:p.x+SYMBOL.cx,y:p.y+SYMBOL.cy},ids:[PERSONA_ROUTE_ID]};}if(id&&this.center(id)){const p=this.layout.positions.get(id),anchor=value.anchor,center=this.center(id);if(p&&anchor){const side=anchor.name,dx=anchor.args?.dx || 0,dy=anchor.args?.dy || 0;return {point:{x:(side==='left'?p.x:side==='right'?p.x+p.width:center.x)+dx,y:(side==='top'?p.y:side==='bottom'?p.y+p.height:center.y)+dy},ids:[id]};}return {point:center,ids:[id]};}if(cell){const p=cell.position();return {point:{x:p.x+SYMBOL.cx,y:p.y+SYMBOL.cy},ids:[id || value.id]};}}return {point:{x:value.x,y:value.y},ids:[]};};
      const kinds=new Map(),allEdges=this.graph.getLinks(),preferenceClearance=allEdges.filter(e=>e.get('apatePreference')).map(e=>{const a=this.layout.positions.get(this.graph.getCell(e.source().id)?.get('sourceId')),b=this.layout.positions.get(this.graph.getCell(e.target().id)?.get('sourceId'));if(!a||!b||Math.abs(a.y-b.y)>4)return null;return {id:'preference-clearance-'+e.id,x:Math.min(a.x+a.width/2,b.x+b.width/2)-16,y:Math.max(a.y+a.height,b.y+b.height)+4,width:Math.abs(a.x+a.width/2-b.x-b.width/2)+32,height:120};}).filter(Boolean),contribution=e=>['make','break','help','hurt'].includes(e.get('sourceKind'));
      const identity=value=>this.graph.getCell(value.id)?.get('sourceId'),ownerOf=id=>this.diagram.nodes.find(n=>n.id===id)?.owner;
      const businessBoxes=[...this.layout.positions.values()].filter(p=>p.band==='hierarchy'),topY=Math.min(...businessBoxes.map(p=>p.y)),taskBottom=Math.max(...businessBoxes.map(p=>p.y+p.height));
      const hint=edge=>{
        const sourceId=identity(edge.source()),targetId=identity(edge.target()),source=this.layout.positions.get(sourceId),target=this.layout.positions.get(targetId),kind=edge.get('apatePreference')?'preference':edge.get('sourceKind');if(!source||!target)return {};
        const channel=contribution(edge)?'contribution':kind,index=kinds.get(channel)||0;kinds.set(channel,index+1);
        const anchor=(which,name,dx=0)=>{const value=which==='source'?edge.source():edge.target(),next={...value,anchor:{name,args:{dx}}};if(which==='source')edge.source(next);else edge.target(next);};
        const owner=ownerOf(sourceId),targetOwner=ownerOf(targetId),owned=this.diagram.nodes.filter(n=>n.owner===owner).map(n=>this.layout.positions.get(n.id)),bottom=Math.max(source.y+source.height,...owned.map(p=>p.y+p.height));let guides,guideConnector='apateFlow';
        if(['and','or'].includes(kind)){
          const siblings=allEdges.filter(e=>e.get('sourceKind')===kind&&e.target().id===edge.target().id).sort((a,b)=>end(a.source()).point.x-end(b.source()).point.x),slot=siblings.indexOf(edge),dx=((slot+.5)/siblings.length-.5)*target.width*.78;
          anchor('source','top');anchor('target','bottom',dx);const a=end(edge.source()).point,b=end(edge.target()).point;
          if(kind==='and'&&a.y-b.y>420&&owner===targetOwner){
            const descendants=new Set([sourceId]);for(let pass=0;pass<this.diagram.nodes.length;pass++)for(const e of this.diagram.links)if(['and','or'].includes(e.kind)&&descendants.has(e.target))descendants.add(e.source);
            const branch=[...descendants].map(id=>this.layout.positions.get(id)).filter(Boolean),left=Math.min(...branch.map(p=>p.x))-36,right=Math.max(...branch.map(p=>p.x+p.width))+36,sameColumn=siblings.filter(e=>Math.abs(this.layout.positions.get(identity(e.source())).x-source.x)<30).sort((a,b)=>end(a.source()).point.y-end(b.source()).point.y),columnSlot=sameColumn.indexOf(edge),gutter=left+20-columnSlot*17,lane=b.y+24+slot*2.5;
            const isTerminal=branch.length===1,outer=isTerminal?(a.x<b.x?Math.min(...owned.map(p=>p.x))-76-slot*10:Math.max(...owned.map(p=>p.x+p.width))+76+slot*10):gutter;
            guides=[{x:outer,y:a.y-32},{x:outer,y:lane},{x:b.x,y:lane}];
          }else guides=[{x:(a.x+b.x)/2+(Math.abs(a.x-b.x)<10?24:0),y:(a.y+b.y)/2+(Math.abs(a.x-b.x)<10?0:22)}];
        }else if(kind==='preference'&&Math.abs(source.y-target.y)<4){
          anchor('source','bottom');anchor('target','bottom');guides=[{x:(source.x+target.x+source.width)/2,y:Math.max(source.y+source.height,target.y+target.height)+106}];guideConnector='smooth';
        }else if(kind==='pre'){
          const siblings=allEdges.filter(e=>e.get('sourceKind')==='pre'&&e.target().id===edge.target().id&&ownerOf(identity(e.source()))===owner).sort((a,b)=>end(a.source()).point.x-end(b.source()).point.x||end(a.source()).point.y-end(b.source()).point.y);
          if(owner===targetOwner&&siblings.length>3){
            const slot=siblings.indexOf(edge),sameColumn=siblings.filter(e=>Math.abs(this.layout.positions.get(identity(e.source())).x-source.x)<30).sort((a,b)=>end(a.source()).point.y-end(b.source()).point.y),columnSlot=sameColumn.indexOf(edge),descendants=this.diagram.links.filter(e=>['and','or'].includes(e.kind)&&e.target===sourceId).map(e=>this.layout.positions.get(e.source)).filter(Boolean),gutter=Math.max(source.x+source.width,...descendants.map(p=>p.x+p.width))+18+columnSlot*16;
            anchor('source','right');anchor('target','bottom',(.5-(slot+.5)/siblings.length)*target.width*.72);const a=end(edge.source()).point,b=end(edge.target()).point,lane=bottom+180+(siblings.length-slot)*28;
            guides=[{x:gutter,y:a.y},{x:gutter,y:lane},{x:b.x,y:lane}];this.layout.height=Math.max(this.layout.height,lane+130);
          }else{
            const a=this.center(sourceId),b=this.center(targetId),horizontal=Math.abs(a.x-b.x)>Math.abs(a.y-b.y)*.8;
            anchor('source',horizontal?(a.x<b.x?'right':'left'):(a.y<b.y?'bottom':'top'));anchor('target',horizontal?(a.x<b.x?'left':'right'):(a.y<b.y?'top':'bottom'));
          }
        }else if(kind==='npr'){
          const siblings=allEdges.filter(e=>e.get('sourceKind')==='npr'&&e.source().id===edge.source().id).sort((a,b)=>end(a.target()).point.x-end(b.target()).point.x),slot=siblings.indexOf(edge),ownerLeft=Math.min(...owned.filter(p=>p.band==='hierarchy').map(p=>p.x)),bank=ownerLeft-120-slot*46;
          anchor('source','left');anchor('target','left');const a=end(edge.source()).point,b=end(edge.target()).point;guides=[{x:bank,y:a.y+slot*32},{x:bank,y:b.y}];
        }else if(contribution(edge)){
          const outgoing=allEdges.filter(e=>contribution(e)&&e.source().id===edge.source().id).sort((a,b)=>end(a.target()).point.x-end(b.target()).point.x),slot=outgoing.indexOf(edge),incoming=allEdges.filter(e=>contribution(e)&&e.target().id===edge.target().id).sort((a,b)=>end(a.source()).point.x-end(b.source()).point.x),targetSlot=incoming.indexOf(edge),parent=this.diagram.links.find(e=>['and','or'].includes(e.kind)&&e.source===sourceId),parentBox=this.layout.positions.get(parent?.target),side=parentBox&&source.x+source.width/2<parentBox.x+parentBox.width/2?-1:1;
          anchor('source',side<0?'left':'right');anchor('target','bottom',((targetSlot+.5)/incoming.length-.5)*target.width*.72);const a=end(edge.source()).point,b=end(edge.target()).point,gutter=a.x+side*(54+slot*26);
          guides=[{x:gutter,y:a.y},{x:gutter,y:b.y+42+slot*18},{x:b.x,y:b.y+42+slot*18}];
        }else if(kind==='dependency'){
          const a=this.center(sourceId),b=this.center(targetId);anchor('source',a.x<b.x?'right':'left');anchor('target',a.x<b.x?'left':'right');
        }
        if(guides)guides=guides.filter((p,i)=>!i||Math.hypot(p.x-guides[i-1].x,p.y-guides[i-1].y)>.01);return guides?.length?{guides,guideConnector}:{};
      };
      const renderedPoints=edge=>{
        const view=this.paper?.findViewByModel(edge);if(!view?.getPointAtRatio)return null;
        const count=Math.max(40,Math.min(240,Math.ceil((view.getConnectionLength?.() || 1200)/10))),points=[];
        for(let i=0;i<=count;i++){const p=view.getPointAtRatio(i/count);if(p&&finite(p.x)&&finite(p.y))points.push({x:p.x,y:p.y});}
        return points.length>1?points:null;
      };
      const rank=e=>e.get('apatePreference')?1:e.get('sourceKind')==='dependency'?5:['pre','npr'].includes(e.get('sourceKind'))?4:['make','break','help','hurt'].includes(e.get('sourceKind'))?2:0;
      for(const edge of allEdges.sort((a,b)=>rank(a)-rank(b))){
        const guide=hint(edge);
        const a=end(edge.source()),b=end(edge.target());if(!finite(a.point.x)||!finite(b.point.x))continue;
        const key=edge.get('curveKey'),endpoints=[...a.ids,...b.ids],saved=this.curveRoutes.get(key),routeBoxes=edge.get('apatePreference')?boxes:[...boxes,...preferenceClearance],obstacles=routeBoxes.filter(box=>!endpoints.includes(box.id)),input={from:a.point,to:b.point,boxes:routeBoxes,bounds:this.layout,occupied,endpoints,...guide};
        let automatic=routing.route(input);
        edge.connector(automatic.connector || 'smooth',{strength:automatic.flowStrength || .36});edge.vertices(validVertices(saved)?saved.map(p=>({...p})):automatic.vertices);
        let points=renderedPoints(edge) || (validVertices(saved)?(automatic.connector==='apateFlow'?routing.sampleFlow([a.point,...saved,b.point],{strength:automatic.flowStrength || .36}):routing.sample([a.point,...saved,b.point])):automatic.points);
        // Shape-boundary attachment changes the actual spline relative to its
        // center-based prediction. Check that final geometry before labeling.
        if(!validVertices(saved)&&(routing.intersections(points,obstacles)||points.some(p=>p.x<8||p.y<8||p.x>this.layout.width-8||p.y>this.layout.height-8))){
          automatic=routing.route({...input,forceCorridor:true});edge.connector(automatic.connector || 'smooth',{strength:automatic.flowStrength || .36});edge.vertices(automatic.vertices);points=renderedPoints(edge) || automatic.points;
        }
        this.defaultRoutes.set(key,automatic.vertices.map(p=>({...p})));
        occupied.push({points,endpoints,spans:routing.straightSpans(points)});stats.links++;stats.nodeIntersections+=routing.intersections(points,boxes.filter(box=>!endpoints.includes(box.id)));
        routed.push({edge,points});
      }
      // Reserve clear space for the contextualized requirements first. Source
      // labels then avoid the full padded preference backplates.
      for(const {edge,points} of routed.sort((a,b)=>Number(!!b.edge.get('apatePreference'))-Number(!!a.edge.get('apatePreference')))){
        const captions=edge.labels();if(captions.length){const text=captions[0].attrs?.text?.text || '',placed=routing.label({points,text,boxes,labels,bounds:this.layout,...edge.get('labelGeometry')});edge.labels([{...captions[0],position:{distance:placed.distance,offset:placed.offset,angle:0,args:{keepGradient:false,ensureLegibility:true}}}]);labels.push(placed.box);}
      }
      this.routingStats=stats;this.container.dataset.autoLayout=JSON.stringify(stats);
    }
    autoLayout(){
      if(!this.diagram)return;this.clearFocus();this.curveRoutes.clear();this.saveCurves();this.signature='';this.render(this.diagram,this.renderOptions);this.fit({readable:true});
    }
    loadCurves(){this.curveRoutes=new Map();try{const saved=JSON.parse(root.localStorage?.getItem(routingStorageKey(this.signature)) || '[]');if(Array.isArray(saved))for(const entry of saved)if(Array.isArray(entry)&&typeof entry[0]==='string'&&validVertices(entry[1]))this.curveRoutes.set(entry[0],entry[1]);}catch(_){}}
    saveCurves(){try{root.localStorage?.setItem(routingStorageKey(this.signature),JSON.stringify([...this.curveRoutes]));}catch(_){}}
    applyCurve(edge,key){edge.set('curveKey',key);this.defaultRoutes.set(key,edge.vertices().map(p=>({...p})));const saved=this.curveRoutes.get(key);if(validVertices(saved))edge.vertices(saved.map(p=>({...p})));}
    clearCurveTools(){if(this.curveView)this.curveView.removeTools();this.curveView=null;}
    showCurveTools(view){
      this.clearCurveTools();this.curveView=view;
      const Tool=curveToolsClass(),tool=new Tool({vertexAdding:false,redundancyRemoval:false,snapRadius:0,bounds:this.layout}),tools=new joint.dia.ToolsView({tools:[tool]});view.addTools(tools);tools.el.classList.add('apate-curve-tools');
      for(const [index,handle] of [...tools.el.querySelectorAll('.joint-marker-vertex')].entries()){
        handle.setAttribute('tabindex','0');handle.setAttribute('role','button');handle.setAttribute('aria-label','Curve control point');handle.dataset.curveHandle=String(index);
        handle.addEventListener('keydown',event=>{const delta={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[event.key];if(!delta)return;event.preventDefault();event.stopPropagation();const point={...view.model.vertices()[index]},step=event.shiftKey?24:8;point.x+=delta[0]*step;point.y+=delta[1]*step;tool.snapVertex(point,index);view.model.vertex(index,point,{ui:true});});
      }
    }
    resetSelectedCurve(){const view=this.curveView;if(!view)return;const key=view.model.get('curveKey'),points=this.defaultRoutes.get(key);if(!points)return;this.curveRoutes.delete(key);this.saveCurves();view.model.vertices(points.map(p=>({...p})));view.el.dataset.curveVertices=JSON.stringify(points);this.showCurveTools(view);}
    clearFocus(){this.clearCurveTools();for(const cell of this.graph.getCells()){const el=this.paper.findViewByModel(cell)?.el;el?.classList.remove('apate-muted','apate-related','apate-selected');}}
    focusCell(id){
      this.clearFocus();const selected=this.graph.getCell(id);if(!selected)return;
      const nodeIds=new Set(selected.isLink()?[]:[id]),sourceId=selected.get('sourceId');
      if(this.diagram.actors.some(a=>a.id===sourceId))for(const node of this.diagram.nodes.filter(n=>n.owner===sourceId))nodeIds.add(this.cells.get(node.id).id);
      const links=this.graph.getLinks().filter(link=>link.id===id || nodeIds.has(link.source().id) || nodeIds.has(link.target().id) || (link.get('apatePreference') && [...endpointIds(link.get('apatePreference').source),...endpointIds(link.get('apatePreference').target),...endpointIds(link.get('apatePreference').x),...endpointIds(link.get('apatePreference').y)].includes(sourceId)));
      for(const link of links){nodeIds.add(link.source().id);nodeIds.add(link.target().id);}
      for(const cell of this.graph.getCells()){const el=this.paper.findViewByModel(cell)?.el;if(!el)continue;const isScope=this.layout.bounds.has(cell.get('sourceId')),related=cell.isLink()?links.includes(cell):nodeIds.has(cell.id);if(!isScope && !cell.get('apateDecoration'))el.classList.add(related?'apate-related':'apate-muted');if(cell.id===id)el.classList.add('apate-selected');}
    }
    center(id){const node=this.layout.positions.get(id);if(node)return {x:node.x+node.width/2,y:node.y+node.height/2};const actor=this.layout.bounds.get(id);return actor?{x:actor.x+actor.symbolCx,y:actor.y+actor.symbolCy}:null;}
    endpointCenter(value){const points=endpointIds(value).map(id=>this.center(id)).filter(Boolean);return points.length?{x:points.reduce((a,p)=>a+p.x,0)/points.length,y:points.reduce((a,p)=>a+p.y,0)/points.length}:null;}
    endpoint(value){const ids=endpointIds(value).filter(id=>this.cells.has(id));return ids.length===1?{id:this.cells.get(ids[0]).id,selector:'.element'}:this.endpointCenter(value);}
    setScale(scale){this.scale=Math.max(0.04,Math.min(2.5,scale));if(this.layout){this.paper.scale(this.scale);this.paper.setDimensions(this.layout.width*this.scale,this.layout.height*this.scale);}this.container.dataset.zoom=String(Math.round(this.scale*100));}
    scrollToOrigin(){this.container.parentElement.scrollLeft=0;this.container.parentElement.scrollTop=0;}
    scrollToContent(){
      const actors=this.diagram.actors;
      const active=(this.persona?.role_ids || []).find(id=>this.layout.bounds.has(id)) ||
        [...actors].sort((a,b)=>this.diagram.nodes.filter(n=>n.owner===b.id).length-
          this.diagram.nodes.filter(n=>n.owner===a.id).length)[0]?.id;
      const header=this.center(active);
      if(!header){this.scrollToOrigin();return;}
      const frame=this.container.parentElement;
      const hasPersona=this.persona?.name&&(this.persona.role_ids || []).includes(active);
      const left=header.x-(hasPersona?PLAY_GAP+PERSONA_RADIUS:SYMBOL.radius)-24;
      frame.scrollLeft=Math.max(0,left*this.scale);
      frame.scrollTop=Math.max(0,(header.y-PERSONA_RADIUS-24)*this.scale);
    }
    fit({readable=false}={}){
      if(!this.layout)return;
      const frame=this.container.parentElement;
      const width=(frame.clientWidth-40)/this.layout.width;
      const height=(frame.clientHeight-40)/this.layout.height;
      const fullScale=Math.min(1.1,width,height);
      const minimum=readable?.62:.04;
      this.setScale(Math.max(minimum,fullScale));
      if(readable&&fullScale<minimum)this.scrollToContent();else this.scrollToOrigin();
    }
    reset(){this.setScale(1);}
    zoomBy(factor){this.setScale(this.scale*factor);}
    exportSVG(){
      const svg=this.paper.svg.cloneNode(true);svg.setAttribute('xmlns','http://www.w3.org/2000/svg');
      svg.querySelectorAll('.joint-tools,.apate-curve-tools,.c-connection-wrap,[joint-selector="connection-wrap"]').forEach(el=>el.remove());
      svg.querySelectorAll('.apate-muted,.apate-related,.apate-selected').forEach(el=>el.classList.remove('apate-muted','apate-related','apate-selected'));
      svg.setAttribute('width',this.layout.width*this.scale);svg.setAttribute('height',this.layout.height*this.scale);svg.setAttribute('viewBox',`0 0 ${this.layout.width*this.scale} ${this.layout.height*this.scale}`);
      const style=document.createElementNS('http://www.w3.org/2000/svg','style');style.textContent='text{font-family:Arial,sans-serif}.connection{fill:none}.joint-highlight-stroke{display:none}';svg.prepend(style);
      const metadata=document.createElementNS('http://www.w3.org/2000/svg','metadata');
      metadata.textContent=JSON.stringify({schema:'apate.diagram-export.v1',view:this.renderOptions?.view||'original',diagram:this.diagram,persona:this.persona,preferences:this.preferences,layout:{positions:[...this.layout.positions],bounds:[...this.layout.bounds]}});svg.prepend(metadata);
      for(const [sourceId,cell] of this.cells){const element=svg.querySelector(`[model-id="${cell.id}"]`);if(!element)continue;element.setAttribute('data-source-id',sourceId);const original=[...(this.diagram.nodes||[]),...(this.diagram.actors||[])].find(n=>n.id===sourceId);if(original){const title=document.createElementNS('http://www.w3.org/2000/svg','title');title.textContent=JSON.stringify(original);element.prepend(title);}}
      return new XMLSerializer().serializeToString(svg);
    }
    async exportPNG({scale=1}={}){
      if(!this.layout||!Number.isFinite(scale)||scale<=0)throw new Error('A positive PNG export scale and a model are required.');
      const width=Math.ceil(this.layout.width*scale),height=Math.ceil(this.layout.height*scale);
      if(width>16384||height>16384||width*height>32000000)throw new Error('This model exceeds the PNG canvas limit. Export SVG for the full diagram.');
      const url=URL.createObjectURL(new Blob([this.exportSVG()],{type:'image/svg+xml;charset=utf-8'}));
      try{
        const image=await new Promise((resolve,reject)=>{const value=new Image();value.onload=()=>resolve(value);value.onerror=()=>reject(new Error('The SVG could not be rendered as PNG.'));value.src=url;});
        const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
        const context=canvas.getContext('2d');if(!context)throw new Error('PNG export is unavailable in this browser.');
        context.fillStyle='#ffffff';context.fillRect(0,0,width,height);context.drawImage(image,0,0,width,height);
        return await new Promise((resolve,reject)=>canvas.toBlob(value=>value?resolve(value):reject(new Error('PNG encoding failed.')),'image/png'));
      }finally{URL.revokeObjectURL(url);}
    }
    destroy(){this.paper.remove();this.graph.clear();}
  }
  IStarViewer.layoutDiagram=layoutDiagram;IStarViewer.curveVertices=curveVertices;IStarViewer.routingStorageKey=routingStorageKey;IStarViewer.preferenceLabel=preferenceLabel;IStarViewer.preferenceCaption=preferenceCaption;IStarViewer.symbolAttributes=symbolAttributes;IStarViewer.taskReferenceBadge=taskReferenceBadge;IStarViewer.supportsSourceLink=supportsSourceLink;IStarViewer.sourceLinkVisible=sourceLinkVisible;IStarViewer.validChoicePreference=validChoicePreference;IStarViewer.projectedPreferences=projectedPreferences;IStarViewer.elementMeaning=kind=>ELEMENT_MEANINGS[kind] || 'An imported model element.';IStarViewer.linkMeaning=kind=>LINK_MEANINGS[kind] || 'An imported relation whose source type is retained.';
  root.APATEIStarViewer=IStarViewer;
})(typeof window==='undefined'?globalThis:window);
