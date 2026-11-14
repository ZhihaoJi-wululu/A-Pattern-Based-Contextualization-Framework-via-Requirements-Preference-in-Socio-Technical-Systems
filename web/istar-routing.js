/* Presentation-only curve routing. Model identities and relations stay fixed. */
(function(root){
  'use strict';
  const point=(x,y)=>({x,y});
  const distance=(a,b)=>Math.hypot(a.x-b.x,a.y-b.y);
  const expand=(r,p=12)=>({x:r.x-p,y:r.y-p,width:r.width+2*p,height:r.height+2*p});
  const overlaps=(a,b)=>a.x<b.x+b.width&&a.x+a.width>b.x&&a.y<b.y+b.height&&a.y+a.height>b.y;
  function hits(a,b,r){
    let lo=0,hi=1;
    for(const axis of ['x','y']){
      const p=a[axis],q=b[axis],min=r[axis],max=min+(axis==='x'?r.width:r.height),d=q-p;
      if(Math.abs(d)<1e-8){if(p<min||p>max)return false;continue;}
      let t0=(min-p)/d,t1=(max-p)/d;if(t0>t1)[t0,t1]=[t1,t0];lo=Math.max(lo,t0);hi=Math.min(hi,t1);if(lo>hi)return false;
    }
    return true;
  }
  function controls(values){
    const n=values.length-1;if(n===1)return [(2*values[0]+values[1])/3];
    const out=[],tmp=[],rhs=Array.from({length:n},(_,i)=>i===0?values[0]+2*values[1]:i===n-1?(8*values[i]+values[i+1])/2:4*values[i]+2*values[i+1]);
    let diagonal=2;out[0]=rhs[0]/diagonal;
    for(let i=1;i<n;i++){tmp[i]=1/diagonal;diagonal=(i<n-1?4:3.5)-tmp[i];out[i]=(rhs[i]-out[i-1])/diagonal;}
    for(let i=n-2;i>=0;i--)out[i]-=tmp[i+1]*out[i+1];return out;
  }
  function sample(points){
    const cx=controls(points.map(p=>p.x)),cy=controls(points.map(p=>p.y)),out=[points[0]],n=points.length-1;
    for(let i=0;i<n;i++){
      const a=points[i],d=points[i+1],b=point(cx[i],cy[i]),c=i<n-1?point(2*d.x-cx[i+1],2*d.y-cy[i+1]):point((d.x+cx[i])/2,(d.y+cy[i])/2);
      const count=Math.max(12,Math.min(64,Math.ceil((distance(a,b)+distance(b,c)+distance(c,d))/24)));
      for(let j=1;j<=count;j++){const t=j/count,u=1-t;out.push(point(u*u*u*a.x+3*u*u*t*b.x+3*u*t*t*c.x+t*t*t*d.x,u*u*u*a.y+3*u*u*t*b.y+3*u*t*t*c.y+t*t*t*d.y));}
    }
    return out;
  }
  function sampleRounded(points,radius=12){
    // Match JointJS's rounded connector, including its rounded tangent points.
    points=points.filter((p,i)=>!i||distance(p,points[i-1])>.001);
    if(points.length<2)return points;
    const out=[points[0]];
    for(let i=1;i<points.length-1;i++){
      const a=points[i-1],corner=points[i],d=points[i+1],before=Math.min(radius,distance(a,corner)/2),after=Math.min(radius,distance(corner,d)/2);
      const p=point(Math.round(corner.x+(a.x-corner.x)*before/distance(a,corner)),Math.round(corner.y+(a.y-corner.y)*before/distance(a,corner))),q=point(Math.round(corner.x+(d.x-corner.x)*after/distance(corner,d)),Math.round(corner.y+(d.y-corner.y)*after/distance(corner,d)));
      out.push(p);const b=point(p.x/3+corner.x*2/3,p.y/3+corner.y*2/3),c=point(q.x/3+corner.x*2/3,q.y/3+corner.y*2/3);
      for(let j=1;j<=12;j++){const t=j/12,u=1-t;out.push(point(u*u*u*p.x+3*u*u*t*b.x+3*u*t*t*c.x+t*t*t*q.x,u*u*u*p.y+3*u*u*t*b.y+3*u*t*t*c.y+t*t*t*q.y));}
    }
    out.push(points[points.length-1]);return out;
  }
  function flowSegments(points,{strength=.36}={}){
    points=points.filter((p,i)=>!i||distance(p,points[i-1])>.001);
    if(points.length<2)return [];
    const tangents=points.map((p,i)=>{
      if(!i||i===points.length-1){const a=i?points[i-1]:p,b=i?p:points[1],length=distance(a,b),handle=Math.min(160,length*.3);return point((b.x-a.x)/length*handle,(b.y-a.y)/length*handle);}
      const a=points[i-1],b=points[i+1],before=distance(a,p),after=distance(p,b),x=(p.x-a.x)/before+(b.x-p.x)/after,y=(p.y-a.y)/before+(b.y-p.y)/after,length=Math.max(.001,Math.hypot(x,y)),handle=Math.min(110,before*strength,after*strength);
      return point(x/length*handle,y/length*handle);
    });
    return points.slice(1).map((p,i)=>({a:points[i],b:point(points[i].x+tangents[i].x,points[i].y+tangents[i].y),c:point(p.x-tangents[i+1].x,p.y-tangents[i+1].y),d:p}));
  }
  function flowPath(points,options){
    const segments=flowSegments(points,options);if(!segments.length)return '';
    return 'M '+segments[0].a.x+' '+segments[0].a.y+' '+segments.map(s=>'C '+s.b.x+' '+s.b.y+' '+s.c.x+' '+s.c.y+' '+s.d.x+' '+s.d.y).join(' ');
  }
  function sampleFlow(points,options){
    const segments=flowSegments(points,options);if(!segments.length)return points.slice(0,1);const out=[segments[0].a];
    for(const {a,b,c,d} of segments){const count=Math.max(16,Math.min(100,Math.ceil((distance(a,b)+distance(b,c)+distance(c,d))/16)));for(let i=1;i<=count;i++){const t=i/count,u=1-t;out.push(point(u*u*u*a.x+3*u*u*t*b.x+3*u*t*t*c.x+t*t*t*d.x,u*u*u*a.y+3*u*u*t*b.y+3*u*t*t*c.y+t*t*t*d.y));}}
    return out;
  }
  function clearFlow(points,obstacles,bounds,sourceBox,targetBox){
    for(const strength of [.36,.24,.16,.10,.06,.035,.015]){
      const samples=sampleFlow(points,{strength}),nodeHits=intersections(samples,obstacles),outside=samples.some(p=>p.x<8||p.y<8||p.x>bounds.width-8||p.y>bounds.height-8),reentry=reenters(samples,sourceBox)||reenters([...samples].reverse(),targetBox);
      if(!nodeHits&&!outside&&!reentry)return {points:samples,flowStrength:strength};
    }
    return null;
  }
  function corridorRoute(from,to,boxes,bounds,endpoints){
    // A rectilinear visibility grid supplies a bounded route when a free spline
    // cannot get through a dense model. The graph itself remains unchanged.
    const blocked=boxes.map(b=>({...expand(b),id:b.id})),inside=(p,b)=>p.x>=b.x&&p.x<=b.x+b.width&&p.y>=b.y&&p.y<=b.y+b.height;
    const ports=(p,id)=>{
      const box=boxes.find(b=>b.id===id),values=box?[point(box.x-28,p.y),point(box.x+box.width+28,p.y),point(p.x,box.y-28),point(p.x,box.y+box.height+28)]:[p];
      return values.filter(q=>q.x>=28&&q.y>=28&&q.x<=bounds.width-28&&q.y<=bounds.height-28&&!blocked.some(b=>b.id!==id&&hits(p,q,b)));
    };
    const starts=ports(from,endpoints[0]),goals=ports(to,endpoints[endpoints.length-1]);if(!starts.length||!goals.length)return null;
    const axisValues=(axis,size)=>[...new Set([28,size-28,...boxes.flatMap(b=>[b[axis]-28,b[axis]+b[axis==='x'?'width':'height']+28]),...starts.map(p=>p[axis]),...goals.map(p=>p[axis])])].filter(v=>v>=28&&v<=size-28).sort((a,b)=>a-b);
    const xs=axisValues('x',bounds.width),ys=axisValues('y',bounds.height),nx=xs.length,grid=p=>ys.indexOf(p.y)*nx+xs.indexOf(p.x),at=id=>point(xs[id%nx],ys[Math.floor(id/nx)]),goalsByGrid=new Map(goals.map(p=>[grid(p),p])),free=new Map(),segments=new Map();
    const valid=id=>{if(!free.has(id))free.set(id,!blocked.some(b=>inside(at(id),b)));return free.get(id);};
    const clear=(a,b)=>{const key=a<b?a+':'+b:b+':'+a;if(!segments.has(key))segments.set(key,!blocked.some(box=>hits(at(a),at(b),box)));return segments.get(key);};
    const queue=[],costs=new Map(),previous=new Map(),heuristic=p=>Math.abs(p.x-to.x)+Math.abs(p.y-to.y);
    const push=item=>{let i=queue.length;queue.push(item);while(i){const parent=(i-1)>>1;if(queue[parent].score<=item.score)break;queue[i]=queue[parent];i=parent;}queue[i]=item;};
    const pop=()=>{const first=queue[0],last=queue.pop();if(queue.length){let i=0;while(i*2+1<queue.length){let child=i*2+1;if(child+1<queue.length&&queue[child+1].score<queue[child].score)child++;if(queue[child].score>=last.score)break;queue[i]=queue[child];i=child;}queue[i]=last;}return first;};
    for(const p of starts){const id=grid(p);if(!valid(id))continue;const axis=Math.abs(p.x-from.x)>Math.abs(p.y-from.y)?0:1,state=id*2+axis,cost=distance(from,p);costs.set(state,cost);previous.set(state,null);push({state,cost,score:cost+heuristic(p)});}
    let winner=null,best=Infinity;
    while(queue.length){
      const current=pop();if(current.cost!==costs.get(current.state))continue;if(current.score>=best)break;
      const id=Math.floor(current.state/2),axis=current.state%2,p=at(id),x=id%nx,y=Math.floor(id/nx),goal=goalsByGrid.get(id);
      if(goal){const endAxis=Math.abs(to.x-p.x)>Math.abs(to.y-p.y)?0:1,total=current.cost+distance(p,to)+(axis!==endAxis?36:0);if(total<best){winner=current.state;best=total;}}
      for(const [next,nextAxis] of [[x>0?id-1:-1,0],[x<nx-1?id+1:-1,0],[y>0?id-nx:-1,1],[y<ys.length-1?id+nx:-1,1]]){
        if(next<0||!valid(next)||!clear(id,next))continue;const q=at(next),state=next*2+nextAxis,cost=current.cost+distance(p,q)+(axis!==nextAxis?36:0);
        if(cost>=(costs.get(state)??Infinity))continue;costs.set(state,cost);previous.set(state,current.state);push({state,cost,score:cost+heuristic(q)});
      }
    }
    if(winner===null)return null;const path=[];for(let state=winner;state!==null;state=previous.get(state))path.push(at(Math.floor(state/2)));path.reverse();
    const compact=[];for(const p of [from,...path,to]){if(compact.length&&distance(p,compact[compact.length-1])<.001)continue;while(compact.length>1){const a=compact[compact.length-2],b=compact[compact.length-1];if(Math.abs((b.x-a.x)*(p.y-b.y)-(b.y-a.y)*(p.x-b.x))>.01)break;compact.pop();}compact.push(p);}
    const vertices=compact.slice(1,-1);return vertices.length>0&&vertices.length<=8?vertices:null;
  }
  function intersections(points,boxes){return boxes.filter(box=>points.slice(1).some((p,i)=>hits(points[i],p,box))).length;}
  function crossing(a,b,c,d){
    const side=(p,q,r)=>(q.x-p.x)*(r.y-p.y)-(q.y-p.y)*(r.x-p.x);
    return side(a,b,c)*side(a,b,d)<-1e-6&&side(c,d,a)*side(c,d,b)<-1e-6;
  }
  function straightSpans(points){
    const spans=[];if(points.length<2)return spans;let start=0,dx=points[1].x-points[0].x,dy=points[1].y-points[0].y,len=Math.max(.001,Math.hypot(dx,dy));
    const append=end=>{if(distance(points[start],points[end])>24)spans.push({a:points[start],b:points[end]});};
    for(let i=2;i<points.length;i++){const p=points[i],a=points[start],perpendicular=Math.abs((p.x-a.x)*dy-(p.y-a.y)*dx)/len;if(perpendicular>1){append(i-1);start=i-1;dx=p.x-points[start].x;dy=p.y-points[start].y;len=Math.max(.001,Math.hypot(dx,dy));}}
    append(points.length-1);return spans;
  }
  function sharedSpanLength(points,occupied=[]){
    let total=0;const spans=straightSpans(points);
    for(const {a,b} of spans){const length=distance(a,b),ux=(b.x-a.x)/length,uy=(b.y-a.y)/length;
      for(const other of occupied)for(const {a:c,b:d} of other.spans || straightSpans(other.points)){
        const otherLength=distance(c,d);if(Math.abs(ux*(d.x-c.x)/otherLength+uy*(d.y-c.y)/otherLength)<.99985)continue;
        if(Math.abs((c.x-a.x)*uy-(c.y-a.y)*ux)>2||Math.abs((d.x-a.x)*uy-(d.y-a.y)*ux)>2)continue;
        const first=(c.x-a.x)*ux+(c.y-a.y)*uy,last=(d.x-a.x)*ux+(d.y-a.y)*uy,overlap=Math.min(length,Math.max(first,last))-Math.max(0,Math.min(first,last));if(overlap>24)total+=overlap;
      }
    }
    return total;
  }
  function reenters(points,box){
    if(!box)return false;let left=false;
    for(const p of points){const inside=p.x>=box.x&&p.x<=box.x+box.width&&p.y>=box.y&&p.y<=box.y+box.height;if(!inside)left=true;else if(left)return true;}return false;
  }
  function route({from,to,boxes=[],bounds,occupied=[],endpoints=[],forceCorridor=false,guides,guideConnector='apateFlow'}){
    if(distance(from,to)<1){const vertices=[point(Math.min(bounds.width-28,from.x+140),Math.max(28,from.y-110)),point(Math.max(28,from.x-140),Math.max(28,from.y-110))];return {vertices,points:sample([from,...vertices,to]),score:0,nodeHits:0,endpoints};}
    const obstacles=boxes.filter(b=>!endpoints.includes(b.id)).map(b=>expand(b)),mid=point((from.x+to.x)/2,(from.y+to.y)/2),dx=to.x-from.x,dy=to.y-from.y,len=Math.max(1,distance(from,to)),candidates=[],keys=new Set();
    if(guides?.length&&!forceCorridor){
      const sourceBox=boxes.find(b=>b.id===endpoints[0]),targetBox=boxes.find(b=>b.id===endpoints[endpoints.length-1]),flow=guideConnector==='apateFlow'?clearFlow([from,...guides,to],obstacles,bounds,sourceBox,targetBox):null,points=guideConnector==='apateFlow'?(flow?.points || []):sample([from,...guides,to]),nodeHits=points.length?intersections(points,obstacles):1,outside=points.some(p=>p.x<8||p.y<8||p.x>bounds.width-8||p.y>bounds.height-8);
      if(!nodeHits&&!outside&&!reenters(points,sourceBox)&&!reenters([...points].reverse(),targetBox)&&!sharedSpanLength(points,occupied))return {vertices:guides,points,score:0,nodeHits,endpoints,connector:guideConnector,flowStrength:flow?.flowStrength,invalid:false,guided:true};
    }
    const add=vertices=>{vertices=vertices.map(p=>point(Math.max(28,Math.min(bounds.width-28,p.x)),Math.max(28,Math.min(bounds.height-28,p.y))));const key=JSON.stringify(vertices);if(!keys.has(key)){keys.add(key);candidates.push(vertices);}};
    for(const bend of [30,-30,65,-65,110,-110,180,-180,260,-260,360,-360])add([point(mid.x-dy/len*bend,mid.y+dx/len*bend)]);
    const closest=(values,center)=>[...new Set(values.map(Math.round))].sort((a,b)=>Math.abs(a-center)-Math.abs(b-center)||a-b).slice(0,8);
    const ys=[...closest(boxes.flatMap(b=>[b.y-30,b.y+b.height+30]),mid.y),28,bounds.height-28],xs=[...closest(boxes.flatMap(b=>[b.x-30,b.x+b.width+30]),mid.x),28,bounds.width-28];
    if(Math.abs(dx)>20)for(const y of ys){const inset=Math.sign(dx)*Math.min(60,Math.abs(dx)*.3);add([point(from.x,y),point(to.x,y)]);add([point(from.x+inset,y),point(mid.x,y),point(to.x-inset,y)]);}
    if(Math.abs(dy)>20)for(const x of xs){const inset=Math.sign(dy)*Math.min(60,Math.abs(dy)*.3);add([point(x,from.y),point(x,to.y)]);add([point(x,from.y+inset),point(x,mid.y),point(x,to.y-inset)]);}
    let best;
    for(const vertices of candidates){
      const flow=clearFlow([from,...vertices,to],obstacles,bounds,boxes.find(b=>b.id===endpoints[0]),boxes.find(b=>b.id===endpoints[endpoints.length-1])),points=flow?.points || sampleFlow([from,...vertices,to]),nodeHits=intersections(points,obstacles),length=points.slice(1).reduce((s,p,i)=>s+distance(points[i],p),0);
      let crossings=0;const sparse=points.filter((_,i)=>i%4===0||i===points.length-1);
      for(const other of occupied){if(other.endpoints.some(id=>endpoints.includes(id)))continue;const prior=other.points.filter((_,i)=>i%4===0||i===other.points.length-1);for(let i=1;i<sparse.length;i++)for(let j=1;j<prior.length;j++)if(crossing(sparse[i-1],sparse[i],prior[j-1],prior[j]))crossings++;}
      const axis=Math.abs(dy)>Math.abs(dx)?'y':'x',direction=Math.sign(to[axis]-from[axis]),backtrack=points.slice(1).reduce((s,p,i)=>s+Math.max(0,-direction*(p[axis]-points[i][axis])),0);
      const sourceBox=boxes.find(b=>b.id===endpoints[0]),targetBox=boxes.find(b=>b.id===endpoints[endpoints.length-1]),reentry=reenters(points,sourceBox)||reenters([...points].reverse(),targetBox);
      const shared=sharedSpanLength(points,occupied),outside=points.some(p=>p.x<8||p.y<8||p.x>bounds.width-8||p.y>bounds.height-8),score=nodeHits*100000+(outside||reentry?100000:0)+shared*14+crossings*35+length*.035+vertices.length*12+backtrack*2;
      if(!best||score<best.score)best={vertices,points,score,nodeHits,endpoints,invalid:outside||reentry,connector:'apateFlow',flowStrength:flow?.flowStrength || .36};
    }
    if(best.nodeHits||best.invalid||forceCorridor){
      const vertices=corridorRoute(from,to,boxes,bounds,endpoints);
      if(vertices){const flow=clearFlow([from,...vertices,to],obstacles,bounds,boxes.find(b=>b.id===endpoints[0]),boxes.find(b=>b.id===endpoints[endpoints.length-1]));if(flow)return {vertices,...flow,score:0,nodeHits:0,endpoints,connector:'apateFlow',invalid:false};}
    }
    return best;
  }
  function label({points,text,boxes=[],labels=[],fontSize=17,paddingX=6,paddingY=5,bounds}){
    const width=Math.max(30,String(text).length*fontSize*.6+paddingX*2),height=fontSize+paddingY*2,lengths=[0];
    for(let i=1;i<points.length;i++)lengths.push(lengths[i-1]+distance(points[i-1],points[i]));
    let best;
    for(const fraction of [.5,.35,.65,.23,.77,.12,.88,.07,.93])for(const offset of [-18,18,-32,32,-52,52,-74,74,-104,104]){
      const position=fraction*lengths[lengths.length-1],index=Math.max(1,lengths.findIndex(v=>v>=position)),a=points[index-1],b=points[index],len=Math.max(1,distance(a,b)),t=(position-lengths[index-1])/len,p=point(a.x+(b.x-a.x)*t,a.y+(b.y-a.y)*t),x=p.x-(b.y-a.y)/len*offset,y=p.y+(b.x-a.x)/len*offset,box={x:x-width/2,y:y-height/2,width,height};
      const outside=bounds&&(box.x<8||box.y<8||box.x+box.width>bounds.width-8||box.y+box.height>bounds.height-8);
      const score=boxes.filter(r=>overlaps(expand(r,6),box)).length*10000+labels.filter(r=>overlaps(expand(r,4),box)).length*1000+(outside?100000:0)+Math.abs(fraction-.5)*20+Math.abs(offset)*.05;
      if(!best||score<best.score)best={distance:fraction,offset,box,score};
    }
    return best;
  }
  root.APATEIStarRouting={route,label,sample,sampleRounded,flowSegments,flowPath,sampleFlow,intersections,straightSpans,sharedSpanLength};
})(typeof window!=='undefined'?window:globalThis);
