const C={bg:'#10151C',panel:'#19222D',fg:'#F3F4F6',muted:'#B4BDC7',accent:'#9AADC1',line:'#3A4552'};
function txt(s,name,value,x,y,w,h,size=26,color=C.fg,bold=false){const a=s.shapes.add({geometry:'textbox',name,position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});a.text=value;a.text.insets=0;a.text.style={fontFamily:'Aptos',fontSize:size,color,bold};return a;}
function box(s,name,x,y,w,h,fill=C.panel){return s.shapes.add({geometry:'rect',name,position:{left:x,top:y,width:w,height:h},fill,line:{fill:C.line,width:1}});}
function rule(s,x,y,w){s.shapes.add({geometry:'line',position:{left:x,top:y,width:w,height:0},line:{fill:C.line,width:1}});}
function base(s,n,title,sub){txt(s,'Section label','SOCI  /  GOVERNED AI ANALYTICS',72,37,1030,25,15,C.accent,true);txt(s,'Slide title',title,72,90,1136,72,48,C.fg,true);if(sub)txt(s,'Slide context',sub,74,177,1128,68,25,C.muted);rule(s,72,665,1136);txt(s,'Brand footer','Soci',72,680,150,25,17,C.accent,true);txt(s,'Page',String(n).padStart(2,'0'),1160,680,48,25,17,C.muted);}
function panel(s,i,title,body,x,y,w=344,h=285){box(s,'Feature panel '+i,x,y,w,h);txt(s,'Panel number '+i,String(i).padStart(2,'0'),x+24,y+24,w-48,36,22,C.accent,true);txt(s,'Panel title '+i,title,x+24,y+83,w-48,75,30,C.fg,true);txt(s,'Panel body '+i,body,x+24,y+167,w-48,h-180,24,C.muted);}
function note(s,t){s.speakerNotes.text=t;}
function connect(s,a,b,from='right',to='left'){s.shapes.connect(a,b,{kind:'elbow',fromSide:from,toSide:to,line:{fill:C.accent,width:2},tail:{type:'arrow',width:'med',length:'med'}});}
export async function build({presentation,input}){
 if(input.reset)presentation.slides.delete(presentation.slides.items.map(s=>s.id));
 for(let n=input.start;n<=input.end;n++){
 const s=presentation.slides.add({width:1280,height:720});s.background.fill=C.bg;
 switch(n){
 case 1:
 s.images.add({path:'E:/ai_data_rag/ai_data_v2/askdb/docs/presentations/soci-assets/soci-architectural-hero.png',alt:'Conceptual AI architecture in dark glass and silver',fit:'contain',position:{left:715,top:0,width:565,height:720}});
 txt(s,'Brand','Soci',72,111,630,135,112,C.fg,true);
 txt(s,'Value statement','Your data.\nA clearer conversation.',76,292,640,150,43,C.fg);
 txt(s,'Descriptor','AI analytics grounded in business meaning',76,481,620,85,27,C.accent);
 txt(s,'Presenter placeholder','[Presenter name]\n[Team / organisation]    [Date]',76,625,620,55,17,C.muted);
 note(s,'Conceptual AI architecture image generated for Soci. Replaceable image, not a product interface. Editable presenter fields.');break;
 case 2:
 base(s,n,'What Soci is about','A governed analytics workspace that connects business questions to permitted data.');
 txt(s,'Overview statement','Business language in.\nEvidence behind the answer.',76,268,1060,110,42,C.fg,true);
 [['Ask','Explore data through natural-language questions.'],['Explore','Understand measures, data quality and relationships.'],['Report','Build and share analysis through supported workflows.']].forEach((v,i)=>{const x=76+i*398;rule(s,x,427,340);txt(s,'Capability '+i,v[0],x,451,340,48,31,C.accent,true);txt(s,'Description '+i,v[1],x,515,340,110,25,C.muted);});
 note(s,'Sources: current AskDB Chat, Semantic Atlas, Data Trust, Ontology Browser, Analytics Builder. The supported report workflow is separate from the Agentic project.');break;
 case 3:
 base(s,n,'The business problem','The data exists. Getting a consistent answer still takes effort.');
 panel(s,1,'Business users','A familiar question can require SQL knowledge and analyst support.',72,282);
 panel(s,2,'Analysts','Repeated extracts and clarification cycles consume attention.',468,282);
 panel(s,3,'Decision-makers','Different definitions and filters can produce conflicting results.',864,282);
 txt(s,'Problem implication','The missing link is shared business meaning with a clear path to the evidence.',76,603,1120,42,25,C.accent);
 note(s,'Qualitative business problems adapted from the supplied reference presentation. No measured productivity or financial benefit is claimed.');break;
 case 4:
 base(s,n,'How Soci solves the problem','Each stage keeps the business question connected to scope and evidence.');
 const stages=['Question','Business meaning','Query plan','SQL validation','Read-only data','Explanation'];
 let prev;
 stages.forEach((v,i)=>{const x=72+i*194;const a=box(s,'Stage '+i,x,300,166,150);txt(s,'Stage index '+i,String(i+1).padStart(2,'0'),x+18,319,130,30,20,C.accent,true);txt(s,'Stage title '+i,v,x+18,364,130,72,26,C.fg,true);if(prev)connect(s,prev,a);prev=a;});
 [['Approved definitions','Measures and catalog values guide interpretation.'],['Controlled access','The server enforces permitted regional scope.'],['Visible evidence','Results retain filters, explanation and SQL details.']].forEach((v,i)=>{const x=72+i*398;txt(s,'Control '+i,v[0],x,514,340,44,26,C.accent,true);txt(s,'Control detail '+i,v[1],x,564,340,69,23,C.muted);});
 note(s,'Source: current AskDB Chat services, semantic packs, governed query validation and regional scope enforcement. Conceptual flow includes deterministic and cached paths. SQL validation and read-only credentials reduce risk without guaranteeing every answer is correct.');break;
 case 5:
 base(s,n,'Data Trust','Quality context helps users judge the data behind the result.');
 const qualities=[['Completeness','Expected values and missing fields'],['Timeliness','Freshness of the available data'],['Validity','Values checked against configured rules'],['Consistency','Agreement across related fields'],['Uniqueness','Duplicate records and identifiers'],['Accuracy','Checks against defined reference rules']];
 qualities.forEach((v,i)=>{let x=72+(i%3)*398,y=276+Math.floor(i/3)*157;rule(s,x,y,340);txt(s,'Quality heading '+i,v[0],x,y+20,340,45,29,C.fg,true);txt(s,'Quality detail '+i,v[1],x,y+77,340,62,23,C.muted);});
 txt(s,'Trust distinction','Dataset quality and AI answer correctness require separate checks.',76,610,1120,35,23,C.accent);
 note(s,'Sources: current reliability / Data Trust module and supplied reference. Dimensions depend on configured checks and datasets. No numerical score or claim of automatic accuracy measurement is invented.');break;
 case 6:
 base(s,n,'Semantic Atlas','Business terms, calculations and values share an approved reference.');
 panel(s,1,'Semantic model','Measures, fact grain, date fields and supported joins.',72,277,344,264);
 panel(s,2,'Business glossary','Definitions and aliases connect user language to business meaning.',468,277,344,264);
 panel(s,3,'Entity catalog','Make, model and other approved values support interpretation.',864,277,344,264);
 txt(s,'Formula examples','Revenue = SUM(total_sales)     Units = SUM(order_qty)\nAverage selling price = aggregate revenue / aggregate units',76,576,1120,71,25,C.accent);
 note(s,'Verified source: apps/api/semantic/packs/automotive/semantic_model.yaml and business_glossary.yaml. Orders count distinct order_id, while units sum order_qty. ASP is the aggregate ratio. Fact grain is one order.');break;
 case 7:
 base(s,n,'Ontology Browser','Business relationships make the data model easier to explore.');
 const sales=box(s,'Sales',475,293,330,112);txt(s,'Sales label','Sales',502,324,276,50,34,C.fg,true);
 const vehicle=box(s,'Vehicle',72,293,280,112);txt(s,'Vehicle label','Vehicle',99,324,228,50,31,C.fg,true);
 const dealer=box(s,'Dealer',928,293,280,112);txt(s,'Dealer label','Dealer',955,324,228,50,31,C.fg,true);
 const region=box(s,'Region',475,493,330,112);txt(s,'Region label','Region',502,524,276,50,31,C.fg,true);
 connect(s,sales,vehicle,'left','right');connect(s,sales,dealer);connect(s,sales,region,'bottom','top');connect(s,dealer,region,'bottom','right');
 txt(s,'Vehicle attributes','Make, model and segment',72,437,280,74,23,C.muted);
 txt(s,'Dealer attributes','Dealer identity and location',928,437,280,74,23,C.muted);
 note(s,'Editable conceptual relationship view grounded in the Automotive semantic model. fact_sales connects to dim_carline, dim_dealer and dim_region. Dealer also connects to region. Arrows denote relationships, not transaction direction. The query compiler separately validates joins and cardinality.');break;
 case 8:
 base(s,n,'AI Chat functionality','A conversation supported by business definitions and inspectable results.');
 txt(s,'Example question','“Compare units sold and revenue by model for last quarter.”',76,268,1110,83,33,C.fg,true);
 const chat=[['Understand','Use approved measures and catalog context.'],['Clarify','Resolve material ambiguity before analysis.'],['Follow up','Refine the current question with new filters.'],['Explain','Read results with their period and scope.'],['Inspect','Review query details and SQL when available.'],['Continue','Return to saved history and rate responses.']];
 chat.forEach((v,i)=>{let x=72+(i%3)*398,y=382+Math.floor(i/3)*131;rule(s,x,y,340);txt(s,'Chat heading '+i,v[0],x,y+16,340,40,27,C.accent,true);txt(s,'Chat body '+i,v[1],x,y+62,340,64,23,C.muted);});
 note(s,'Sources: current AskDB shared Chat controller and Classic/New layouts, feedback/history API and docs/SOCI_CHAT_UPDATE.md. Application database migration is required for feedback/history persistence. Documents and agentic specialists are outside this presentation scope. No guarantee of universal natural-language coverage.');break;
 case 9:
 base(s,n,'Key features','A connected set of capabilities around governed analytics.');
 const center=box(s,'Central product',485,365,310,112);txt(s,'Central product name','Soci',519,389,245,65,46,C.fg,true);
 const features=[['Analytics Builder','Scoped reports, charts and exports'],['Semantic Atlas','Approved business definitions'],['Data Trust','Quality checks and freshness'],['Configurable LLM','Provider and model settings'],['Usage visibility','Calls, tokens and cost estimates'],['SQL guardrails','Read-only execution and validation'],['Ontology Browser','Business relationship exploration'],['Regional access','Permission-aware data scope']];
 features.forEach((v,i)=>{let left=i<4,idx=i%4,x=left?72:914,y=254+idx*94,w=294;txt(s,'Feature heading '+i,v[0],x,y,w,35,25,C.accent,true);txt(s,'Feature detail '+i,v[1],x,y+39,w,51,20,C.muted);});
 // Reference-inspired native callout connections, kept behind the text area.
 [293,387,481,575].forEach((y,i)=>{const a=box(s,'Left connection anchor '+i,386,y,2,2,C.accent);const b=box(s,'Right connection anchor '+i,890,y,2,2,C.accent);connect(s,a,center);connect(s,center,b);});
 note(s,'Design follows the central concept and connected feature callouts of user reference slide 12. Sources: current AskDB modules. Capabilities depend on configuration and permissions. Usage estimates are not measured answer quality. Exports require target environment acceptance.');break;
 case 10:
 base(s,n,'Cost comparison','Compare the same scope, usage and operating responsibilities.');
 panel(s,1,'Soci','Model usage\nHosting and PostgreSQL\nSupport and maintenance',72,276,344,300);
 panel(s,2,'Power BI Pro','US$14 per user / month\nPaid yearly\nRegional pricing may vary',468,276,344,300);
 panel(s,3,'Copilot capacity','Eligible paid capacity\nTenant and region requirements\nSeparate entitlement checks',864,276,344,300);
 txt(s,'Cost qualification','A total-cost comparison needs user count, model usage, hosting and licence quotes.\nSoci has no verified total or savings estimate in this presentation.',76,600,1120,53,20,C.muted);
 note(s,'Pricing checked 23 November 2026. Official Microsoft Power BI pricing: https://www.microsoft.com/en-us/microsoft-fabric/features/power-bi/pricing — US$14/user/month paid yearly, before applicable taxes, regional/contract pricing may differ. Pro may already be included in an existing E5 licence. Copilot eligibility: https://learn.microsoft.com/en-us/power-bi/create-reports/copilot-introduction and https://learn.microsoft.com/en-us/fabric/enterprise/fabric-copilot-capacity . Pro price alone does not represent complete Copilot cost. Soci costs depend on approved model gateway, infrastructure and operations. Different cost categories, not an equivalent-feature price quote.');break;
 case 11:
 base(s,n,'Admin portal','Central controls for access, model usage and operational review.');
 panel(s,1,'Access and regions','Manage user roles and permitted regional scope.',72,278,344,278);
 panel(s,2,'Models and quotas','Configure approved providers, model settings and usage limits.',468,278,344,278);
 panel(s,3,'Audit and operations','Review activity, token usage and catalog refresh operations.',864,278,344,278);
 txt(s,'Governance boundary','Credentials stay on the server. Analytics access remains read-only.',76,604,1120,42,25,C.accent);
 note(s,'Sources: current AskDB admin settings, quota, audit and catalog modules. Credentials are server configuration. Role and regional enforcement applies on the server. Administration does not imply arbitrary write access to analytical databases.');break;
 case 12:
 txt(s,'Closing brand','Soci',72,68,450,80,55,C.accent,true);
 txt(s,'Questions title','Questions',72,246,1120,130,90,C.fg,true);
 rule(s,76,434,1128);
 txt(s,'Discussion topics','Business fit                  Data scope                  Pilot priorities',76,474,1120,58,27,C.muted);
 txt(s,'Contact placeholder','[Presenter name]    [Email / contact]',76,622,1120,48,21,C.muted);
 note(s,'Final discussion slide. Contact details are editable placeholders.');break;
 }
 }
 return {slides:presentation.slides.items.length,built:[input.start,input.end]};
}
