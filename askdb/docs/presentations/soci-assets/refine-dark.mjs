const B='#AFC7EC',P='#C5B9E5',FG='#F3F4F6',M='#B4BDC7';
function text(s,name,v,x,y,w,h,size=24,color=FG,bold=false){const a=s.shapes.add({geometry:'textbox',name,position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});a.text=v;a.text.insets=0;a.text.style={fontFamily:'Aptos',fontSize:size,color,bold};return a;}
function style(sh,size,color,bold=true){sh.text.style={fontFamily:'Aptos',fontSize:size,color,bold};}
function block(s,n,title,detail,x,y,w,h,accent=B){const a=s.shapes.add({geometry:'rect',name:n,position:{left:x,top:y,width:w,height:h},fill:'#19222D',line:{fill:'#48576B',width:1}});text(s,n+' title',title,x+18,y+14,w-36,36,25,accent,true);text(s,n+' detail',detail,x+18,y+56,w-36,h-60,20,M);return a;}
function link(s,a,b,from='right',to='left'){s.shapes.connect(a,b,{kind:'elbow',fromSide:from,toSide:to,line:{fill:'#8E9EB3',width:2},tail:{type:'arrow',width:'med',length:'med'}});}
export async function refine({presentation}){
 const original=[...presentation.slides.items];
 for(const [i,s] of original.entries())for(const sh of s.shapes.items){const n=sh.toSnapshot().name||'';
 if(n==='Slide title'){style(sh,44,B);}
 if(/^(Panel title|Feature heading|Chat heading|Column heading|Quality heading)/.test(n))style(sh,/^Panel title/.test(n)?28:25,/ [1357]$/.test(n)?P:B);
 if(/^(Panel number|Section label|Brand footer|Stage index)/.test(n))style(sh,/^Panel number/.test(n)?22:15,P);
 if(/^(Capability|Control |Central product name|Formula examples|Value statement|Descriptor|Closing brand)/.test(n))style(sh,n==='Central product name'?42:n==='Formula examples'?24:n==='Value statement'?38:n==='Closing brand'?48:27,/[1357]$/.test(n)?P:B,n!=='Formula examples'&&n!=='Descriptor');
 if(n==='Brand')style(sh,100,FG);
 if(n==='Value statement')style(sh,38,FG,false);
 if(n==='Overview statement')style(sh,37,FG);
 if(n==='Questions title')style(sh,76,FG);
 if(n==='Example question')style(sh,29,FG);
 if(n==='Panel title 3'&&i===10)sh.text='Audit and operations';
 }
 const arch=presentation.slides.insert({after:original[3],width:1280,height:720}).slide;arch.background.fill='#10151C';
 text(arch,'Section label','SOCI  /  GOVERNED AI ANALYTICS',72,37,1100,25,15,P,true);
 text(arch,'Slide title','Soci architecture',72,90,1136,65,44,B,true);
 text(arch,'Slide context','The API coordinates meaning, model assistance and controlled data access.',74,177,1130,60,25,M);
 const ui=block(arch,'Web client','Soci web app','Next.js / React\nChat and analytics',72,377,265,125,B);
 const api=block(arch,'Application API','FastAPI backend','Authentication, RBAC\nPlanning and SQL validation',465,377,350,125,P);
 const llm=block(arch,'Model gateway','Approved LLM endpoint','Interpretation and narration',465,251,350,95,B);
 const sql=block(arch,'Analytics database','Analytics PostgreSQL','Read-only queries\nPermitted regional scope',943,377,265,125,B);
 const sem=block(arch,'Business context','Semantic context','YAML packs, glossary and catalog',465,550,350,95,P);
 const app=block(arch,'Application database','Application PostgreSQL','Users, history, ratings and audit',943,550,265,95,P);
 link(arch,ui,api);link(arch,api,sql);link(arch,api,llm,'top','bottom');link(arch,sem,api,'top','bottom');link(arch,api,app,'bottom','left');
 text(arch,'Client connection','HTTPS',361,419,88,30,17,M);
 text(arch,'Query connection','SQL',851,419,80,30,17,M);
 arch.speakerNotes.text='Current AskDB conceptual architecture, not the separate Agentic implementation. Sources: apps/api/app/main.py, services/chat/service.py, automotive semantic pack and docs/SOCI_CHAT_UPDATE.md. FastAPI backend enforces identity and regional scope; analytics PostgreSQL uses read-only access. Application PostgreSQL stores users, query history and ratings, subject to application migration. Approved model endpoint supports interpretation and narration where configured. Diagram shows logical components and primary request/dependency direction, not deployment topology. No browser credentials for database or model provider. Documents/RAG remain outside the demo architecture.';
 // Add concrete context to the closing slide without changing its role.
 const end=original[11];text(end,'Discussion context','Which questions matter most?\nWhich data and access rules should the pilot include?',76,548,1120,65,24,M);
 for(const [i,s] of presentation.slides.items.entries()){
 const pg=s.shapes.items.find(x=>x.toSnapshot().name==='Page');if(pg)pg.text=String(i+1).padStart(2,'0');
 }
 text(arch,'Brand footer','Soci',72,680,150,25,17,P,true);text(arch,'Page','05',1160,680,48,25,17,M);
 await presentation.render();return {slides:presentation.slides.items.length};
}

