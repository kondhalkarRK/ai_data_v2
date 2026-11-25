const C={bg:'#0C1623',fg:'#F5F2EB',muted:'#A9B9C6',teal:'#84C8C1',blue:'#9CB5DD',line:'#334957',surface:'#152737',amber:'#D6B98A'};
const ROOT='E:/ai_data_rag/ai_data_v2/askdb/';
const ASSET=ROOT+'docs/presentations/soci-assets/';
function text(s,name,value,x,y,w,h,size=27,color=C.fg,bold=false){
 const sh=s.shapes.add({geometry:'textbox',name,position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 sh.text=value;sh.text.insets=0;sh.text.style={fontFamily:'Aptos',fontSize:size,color,bold};return sh;
}
function rule(s,x,y,w,color=C.line){s.shapes.add({geometry:'line',name:'Alignment rule',position:{left:x,top:y,width:w,height:0},fill:'none',line:{fill:color,width:1}});}
function box(s,name,x,y,w,h,fill=C.surface){return s.shapes.add({geometry:'rect',name,position:{left:x,top:y,width:w,height:h},fill,line:{fill:C.line,width:1}});}
function foot(s,n,caption=''){rule(s,72,665,1136);text(s,'Product footer','Scio',72,680,80,22,16,C.teal,true);text(s,'Page number',String(n).padStart(2,'0'),1170,678,38,24,17,C.muted);if(caption)text(s,'Evidence caption',caption,175,678,960,24,15,C.muted);}
function heading(s,n,title,subtitle='',caption=''){text(s,'Slide title',title,72,57,1136,70,48,C.fg,true);if(subtitle)text(s,'Slide explanation',subtitle,74,139,1132,68,26,C.muted);foot(s,n,caption);}
function note(s,value){s.speakerNotes.text=value;}
function image(s,file,x,y,w,h,crop){return s.images.add({path:ASSET+file,alt:file.startsWith('reference')?'Reference product interface; illustrative historical data':'Scio interface with synthetic test data',fit:'contain',position:{left:x,top:y,width:w,height:h},...(crop?{crop}:{})});}
function table(s,values,x,y,w,h,widths,size=23){
 const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,columnWidths:widths,values});
 t.borders.assign({style:'solid',fill:C.line,width:1});
 for(let r=0;r<values.length;r++)for(let c=0;c<values[0].length;c++){const cell=t.getCell(r,c);cell.fill=r===0?'#203E4D':C.bg;cell.text.style={fontFamily:'Aptos',fontSize:size,color:r===0?C.teal:C.fg,bold:r===0};}
 return t;
}
function flow(s,items,y=310){
 const width=(1136-(items.length-1)*30)/items.length;
 items.forEach((item,i)=>{const x=72+i*(width+30);box(s,'Workflow '+i,x,y,width,132);text(s,'Step number '+i,String(i+1).padStart(2,'0'),x+18,y+15,width-36,25,17,C.teal,true);text(s,'Step label '+i,item,x+18,y+53,width-36,70,25,C.fg,true);if(i<items.length-1)text(s,'Flow direction '+i,'→',x+width+4,y+48,26,40,25,C.teal);});
}
function columns(s,items,y=260){const w=340;items.forEach((it,i)=>{const x=72+i*398;text(s,'Column number '+i,String(i+1).padStart(2,'0'),x,y,w,60,53,C.teal);rule(s,x,y+83,w);text(s,'Column heading '+i,it[0],x,y+112,w,70,30,C.fg,true);text(s,'Column content '+i,it[1],x,y+203,w,145,25,C.muted);});}

export async function build({presentation,input}){
 if(input.reset)presentation.slides.delete(presentation.slides.items.map(s=>s.id));
 for(let n=input.start;n<=input.end;n++){
  const s=presentation.slides.add({width:1280,height:720});s.background.fill=C.bg;
  switch(n){
   case 1:
    image(s,'soci-architectural-hero.png',715,0,565,720);
    text(s,'Scio cover title','Scio',72,115,620,130,110,C.fg,true);
    text(s,'Cover tagline','Ask your data anything,\nin plain English.',76,292,650,150,44,C.fg);
    text(s,'Cover descriptor','Governed AI analytics\nfor business decisions',76,475,610,86,27,C.teal);
    text(s,'Editable presenter details','[Presenter name]  ·  [Team / organisation]\n[Presentation date]',76,625,625,50,17,C.muted);
    note(s,'Cover: conceptual architectural image generated for Scio. The right-hand image is intentionally replaceable, not a product screenshot. Product tagline: apps/web/lib/brand.ts. Presenter/team/date remain editable. Dark editorial system, restrained teal and navy.');break;
   case 2:
    text(s,'Problem title','A simple question.\nA fragmented path to an answer.',72,72,1136,140,55,C.fg,true);
    text(s,'Running business question','“How do units sold and revenue compare\nacross two vehicle models?”',76,248,1080,105,35,C.teal);
    flow(s,['Business request','Analyst translation','Extract and reconcile','Business answer'],410);
    text(s,'Friction labels','Unclear scope                    Repeated work                    Competing definitions',76,582,1130,45,23,C.muted);foot(s,n);
    note(s,'Qualitative problem framing adapted from the user-provided Dummy_PPT.pptx and Dummy_2.pptx. These are business challenges to validate with stakeholders, not measured claims about an organisation. The running question requires an explicit period and approved model names.');break;
   case 3:
    heading(s,n,'The operational impact','The friction is shared across the business.');
    columns(s,[['Business users','Questions depend on specialist availability and clear interpretation.'],['Analysts','Repeated requests recreate extracts, filters and explanations.'],['Leadership','Different definitions make comparisons harder to defend.']],245);
    note(s,'Stakeholder hypotheses from reference decks. No turnaround-time, productivity or revenue-improvement statistics are claimed. Speaker: connect each difficulty to a real audience example during discussion.');break;
   case 4:
    heading(s,n,'Scio brings the question closer to the data','A business interface supported by meaning, scope and evidence.');
    text(s,'Product explanation','Ask in familiar\nbusiness language.',72,240,400,110,38,C.fg,true);
    text(s,'Product detail','Use approved definitions.\nQuery permitted data.\nInspect the result.',76,389,370,150,28,C.muted);
    image(s,'soci-chat-empty.png',495,224,715,365,{left:0.175,top:0.15,right:0.02,bottom:0.16});
    text(s,'Value statement','For business users, analysts and decision-makers.',76,600,1100,42,27,C.teal);
    note(s,'Current Scio Chat screenshot captured during UI tests; Anita is a synthetic authenticated profile, not a hardcoded product greeting. Source: apps/web/components/chat/chat-workspace-view.tsx, hooks/use-chat-ask.ts, lib/chat-greeting.ts; docs/SOCI_CHAT_UPDATE.md. The screenshot demonstrates layout, not live warehouse/model accuracy.');break;
   case 5:
    heading(s,n,'How a question becomes an answer','The result keeps its business meaning and permitted scope.');
    text(s,'Semantic input','Approved measures · glossary · catalog values · dates and grouping',76,238,1120,48,25,C.teal);
    flow(s,['Question and scope','Semantic context','Plan and validate','Read-only execution','Results and explanation'],323);
    text(s,'Workflow controls','Clarify material ambiguity. Enforce regional access. Reuse supported cached answers.',76,522,1120,90,26,C.muted);
    note(s,'Sources: apps/api/app/services/chat/service.py and associated planning/context modules; app/services/security/region_scope.py. This is the governed AskDB workflow, not the separate Agentic implementation. Supported deterministic and cache paths do not necessarily call an LLM. Model output is not the numerical evidence.');break;
   case 6:
    heading(s,n,'Semantic Atlas','A shared definition before a shared answer.');
    text(s,'Definition narrative','What does\n“sales” mean here?',74,241,430,112,42,C.fg,true);
    text(s,'Semantic purpose','The glossary connects business terms\nto approved measures and mappings.',76,396,430,110,26,C.muted);
    table(s,[['Business measure','Approved calculation'],['Revenue','SUM(total_sales)'],['Units sold','SUM(order_qty)'],['Orders','COUNT(DISTINCT order_id)'],['Average selling price','Revenue / units sold']],560,240,648,310,[285,363],24);
    text(s,'Semantic takeaway','One order can contain multiple units. Units and orders are different measures.',76,586,1124,60,25,C.teal);
    note(s,'Verified sources: apps/api/semantic/packs/automotive/business_glossary.yaml and semantic_model.yaml. Revenue uses total_sales, not price_per_unit; units uses order_qty; fact grain is one sales order. ASP is the approved aggregate ratio, not an average of per-row prices. This is an editable business-definition table, not a fabricated screenshot.');break;
   case 7:
    heading(s,n,'Ontology Browser','See how the business concepts connect.','Reference interface excerpt • historical illustrative content');
    image(s,'reference-9-image20.png',72,225,725,409,{left:0.37,top:0.15,right:0.22,bottom:0.12});
    text(s,'Ontology path','Vehicle → Sales\nDealer → Region',850,263,340,126,35,C.teal,true);
    text(s,'Ontology benefit','Explore entities and relationships\nbefore interpreting an analysis.',850,427,340,115,25,C.fg);
    text(s,'Ontology boundary','A visual relationship does not\nby itself prove a valid SQL join.',850,560,340,69,21,C.muted);
    note(s,'Image source: user-provided Dummy_2.pptx slide 9; historical interface screenshot, intentionally cropped to the graph without changing its content. Current Automotive semantic_model.yaml supplies approved relationships and cardinality. Ontology is an exploration view; the governed compiler validates actual query joins.');break;
   case 8:
    heading(s,n,'Data Trust','Understand the data behind the business answer.','Reference interface excerpt • figures are historical illustration');
    image(s,'reference-7-image18.png',72,234,735,364,{left:0.14,top:0.075,right:0.01,bottom:0.18});
    const trust=[['Freshness','Is the reporting period current?'],['Completeness','Are expected values present?'],['Rule results','Which checks need attention?']];
    trust.forEach((it,i)=>{let y=240+i*126;text(s,'Trust label '+i,it[0],850,y,350,42,28,C.teal,true);text(s,'Trust meaning '+i,it[1],850,y+50,350,67,24,C.fg);});
    text(s,'Trust boundary','Dataset quality is not a guarantee that an AI answer is correct.',76,609,1130,42,24,C.amber);
    note(s,'Reference image: Dummy_2.pptx slide 7; values are not current Scio production measurements. Capability sources: current reliability UI/services and configured quality rules. Explain freshness, completeness and rule outcomes; do not use the depicted score as model confidence. Current screenshot replacement is possible without altering the editable slide text.');break;
   case 9:
    heading(s,n,'AI Chat','Ask, refine and inspect the answer.','Current Scio interface excerpt • synthetic test values');
    image(s,'soci-chat-answer.png',72,225,720,405,{left:0.185,top:0.13,right:0.32,bottom:0.18});
    [['Ask in business terms','Make the measure and period clear.'],['Read the result','Tables, charts and explanation.'],['Inspect and respond','SQL, feedback and saved history.']].forEach((it,i)=>{let y=238+i*129;text(s,'Chat sequence '+i,String(i+1).padStart(2,'0'),844,y,52,48,34,C.teal,true);text(s,'Chat heading '+i,it[0],912,y,295,58,27,C.fg,true);text(s,'Chat detail '+i,it[1],912,y+62,295,58,23,C.muted);});
    note(s,'Sources: current Chat UI/SSE contracts and docs/SOCI_CHAT_UPDATE.md. Screenshot captured in browser acceptance with fixture data; not a live LLM/warehouse answer. History/feedback require the application migration. Greeting uses authenticated fullName first token with a neutral fallback. Clarification and SQL inspection remain part of the existing Chat workflow.');break;
   case 10:
    heading(s,n,'Executive Intelligence','Read performance in context.','Reference dashboard excerpt • not current business performance');
    image(s,'reference-5-image16.png',72,229,755,365,{left:0.14,top:0.065,right:0.38,bottom:0.545});
    text(s,'Dashboard callout 1','A trend',870,250,330,48,32,C.teal,true);text(s,'Dashboard copy 1','See how a measure changes\nthrough the selected period.',870,306,330,90,25,C.fg);
    text(s,'Dashboard callout 2','A comparison',870,439,330,48,32,C.teal,true);text(s,'Dashboard copy 2','Explore regions, models and\nother supported breakdowns.',870,495,330,90,25,C.fg);
    text(s,'Dashboard scope','Interpret KPIs with the active period, filters and permitted regional scope.',76,611,1120,40,24,C.muted);
    note(s,'Reference screenshot: Dummy_2.pptx slide 5, cropped to the trend region. Do not read the displayed historical figures as current or verified business results. Source capabilities: current executive/KPI modules. A period can be partial; UI freshness and period labels matter.');break;
   case 11:
    heading(s,n,'Analytics Builder','Turn an objective into a scoped report.');
    text(s,'Report example','Sales performance\nfor a defined period',76,243,465,125,40,C.fg,true);
    text(s,'Report scope','Choose measures, dates and filters\nthrough the supported workflow.',76,410,465,110,27,C.muted);
    table(s,[['Report element','Business purpose'],['KPI values','Summarise the chosen measures'],['Charts','Explore trends and breakdowns'],['Briefing','Explain verified evidence'],['Exports','Share a captured report view']],600,240,608,320,[200,408],24);
    text(s,'Report exports','PDF · report images · configured Outlook draft workflow',76,595,1130,44,25,C.teal);
    note(s,'Sources: current components/analytics-builder/askbi and app/services/analytics/bi. Availability depends on industry and feature flags. Chat Generate report opens Builder; this is not the Agentic report agent. Report/export behavior should be accepted in the target browser/Outlook environment. Do not promise a fixed KPI/chart count for every natural-language request.');break;
   case 12:
    heading(s,n,'Admin Center','Keep AI usage visible and operational controls explicit.','Reference interface excerpt • historical illustrative counters');
    image(s,'reference-10-image21.png',72,219,1136,232,{left:0.14,top:0.06,right:0.02,bottom:0.61});
    [['Access','Users, roles and regional grants.'],['Model and usage','Approved models, quotas and recorded usage.'],['Operations','Catalog refresh and audit visibility.']].forEach((it,i)=>{const x=76+i*398;text(s,'Admin responsibility '+i,it[0],x,492,340,48,29,C.teal,true);text(s,'Admin description '+i,it[1],x,550,340,84,25,C.fg);});
    note(s,'Reference screenshot: Dummy_2.pptx slide 10. Crop excludes the email/user breakdown and keeps the operational controls and historical counters. No current usage or latency measurement is claimed. Current sources: Admin Center, governance/auth services and catalog operations. Credentials remain server-side and must never be shown on slides.');break;
   case 13:
    heading(s,n,'Security and governance','Authorised access is a server-side responsibility.');
    table(s,[['Example role','North','West','South / East'],['Administrator','Allowed','Allowed','Allowed'],['North user','Allowed','Blocked','Blocked'],['West user','Blocked','Allowed','Blocked']],72,258,704,270,[245,125,125,209],23);
    text(s,'Control heading','Identity → scope\n→ permitted query',838,258,370,125,34,C.teal,true);
    text(s,'Control detail','Enforce regional access in\nthe API and data-access path.\nKeep analytics read-only.',838,430,365,142,26,C.fg);
    text(s,'Control boundary','Regional examples are illustrative; actual grants come from the authenticated profile.',76,600,1132,53,23,C.muted);
    note(s,'Sources: app/api/deps.py, authentication services and app/services/security/region_scope.py. Matrix is an explanatory example, not a dump of actual accounts. Server-issued identity and SQL scope enforcement are distinct from hiding UI rows. No claim of SSO, enterprise certification, universal row/column policies or automatic writeback.');break;
   case 14:
    heading(s,n,'Current architecture','Experience, meaning and numerical execution remain distinct.');
    const layers=[['Experience','Next.js / React','Chat · dashboards · Builder · administration'],['Application services','FastAPI','Authentication · planning · validation · APIs'],['Business meaning','Semantic configuration','Glossary · measures · mappings · approved relationships'],['Data and model services','PostgreSQL + approved gateway','Read-only analytics · application state · model access']];
    layers.forEach((it,i)=>{const y=222+i*96;box(s,'Architecture layer '+i,72,y,1136,78,i%2===0?'#152737':C.bg);text(s,'Layer role '+i,it[0],90,y+12,230,58,23,C.teal,true);text(s,'Layer technology '+i,it[1],340,y+12,305,58,22,C.fg,true);text(s,'Layer responsibility '+i,it[2],663,y+12,524,58,22,C.muted);});
    text(s,'Architecture distinction','Application storage and read-only analytical databases use separate responsibilities.',76,617,1132,38,22,C.muted);
    note(s,'Verified current stack: apps/web/package.json, apps/api/pyproject.toml, DB/service modules and semantic pack files. Optional document retrieval is configuration dependent and not required for structured SQL answers. Do not use older reference-deck Streamlit/DuckDB/LangChain architecture as the current implementation. No dependency on the separate Agentic project.');break;
   case 15:
    heading(s,n,'Key capabilities','Each capability supports a specific piece of business work.');
    table(s,[['Business need','Scio capability','Evidence to inspect'],['Ask a business question','AI Chat','Answer, scope and SQL'],['Agree what a metric means','Semantic Atlas','Definition and calculation'],['Explore relationships','Ontology Browser','Entities and links'],['Review data reliability','Data Trust','Freshness and rule outcomes'],['Create a scoped report','Analytics Builder','KPIs, charts and briefing'],['Control and operate AI','Admin Center','Access, usage and audit']],72,231,1136,378,[350,295,491],23);
    note(s,'Capability synthesis of earlier slides. Source modules are cited in their respective notes. Avoid expanding the list into unimplemented auto-remediation, arbitrary database connectors or Agentic capabilities. Semantic meaning, relationship exploration, data quality and answer correctness are separate responsibilities.');break;
   case 16:
    heading(s,n,'Cost comparison','Compare the complete operating scenario.');
    table(s,[['Cost component','Scio','Power BI / Copilot scenario'],['Access / licensing','Confirm commercial terms','Pro: US$14/user/month*'],['AI / model services','Approved gateway usage','Eligible capacity / entitlements'],['Infrastructure and operations','Application, DB and support','Capacity, integration and support'],['Total cost','Workload and quotes required','Entitlements and scope required']],72,240,1136,300,[300,390,446],23);
    text(s,'Cost footnote','*US advertised Pro price, billed yearly. Existing E5, region/tax and Copilot requirements affect incremental cost.',76,575,1125,65,21,C.muted);
    note(s,'Official pricing checked 23 November 2026: https://www.microsoft.com/en-us/microsoft-fabric/features/power-bi/pricing . Pro advertised at US$14/user/month paid yearly and included in Microsoft 365 E5 / Office 365 E5. Actual price and taxes vary. Copilot requirements: https://learn.microsoft.com/en-us/power-bi/create-reports/copilot-introduction and https://learn.microsoft.com/en-us/fabric/enterprise/fabric-copilot-capacity . Eligible paid capacity and tenant/region configuration matter; a Pro price is not a complete Copilot TCO. Scio model rates, hosting, support and commercial terms need approved quotes. No savings percentage is asserted. See appendix for an explicitly hypothetical inference calculation.');break;
   case 17:
    heading(s,n,'Demonstration journey','Keep one business question visible throughout the demo.');
    flow(s,['Ask a comparison','Refine the scope','Inspect SQL / evidence','Explore a report'],290);
    text(s,'Demo question','“Compare units sold and revenue for [model A] and [model B] in [period].”',76,231,1120,45,25,C.teal);
    text(s,'Demo discipline','Use actual catalog values and a verified data period. Rehearse the full sequence before presenting.',76,482,1100,100,28,C.fg);
    text(s,'Editable demo link','[Insert approved Scio demo link]',76,603,1100,39,23,C.muted);
    note(s,'This is a rehearsal sequence, not a claim that the example has passed a live-provider test. Substitute real permitted catalog values and available dates. Verify the follow-up, SQL disclosure, region behavior and report navigation before a live audience. No extra model usage merely to inspect existing SQL or rate a saved response.');break;
   case 18:
    text(s,'Discussion heading','Questions?',72,170,750,130,94,C.fg,true);
    text(s,'Discussion supporting line','Where could Scio help\nyour team make a better decision?',78,350,620,112,34,C.teal);
    [['Business fit','Which question should a pilot address?'],['Governance scope','Which data and permissions apply?'],['Pilot success','What evidence would show value?']].forEach((it,i)=>{let y=187+i*139;text(s,'Discussion topic '+i,it[0],832,y,360,46,27,C.fg,true);text(s,'Discussion prompt '+i,it[1],832,y+57,360,73,25,C.muted);});
    text(s,'Contact placeholder','[Contact details / approved demo link]',78,611,1100,35,21,C.muted);foot(s,n);
    note(s,'Main-deck close. Invite discussion of scope and success criteria rather than promising unsupported business outcomes. Presenter/contact placeholder remains editable. The following three slides are appendix material.');break;
   case 19:
    heading(s,n,'Architecture responsibilities','Appendix · Ownership boundaries matter as much as components.');
    table(s,[['Component','Responsibility','Boundary'],['Browser','Present and interact','No provider credentials'],['API services','Authenticate, plan and validate','Server-owned permissions'],['Semantic configuration','Define measures and mappings','Approved business formulas'],['Analytics database','Compute numerical results','Read-only scoped execution'],['Application database','Auth, history, feedback and usage','Owned durable application state'],['Approved model gateway','Language / narrative assistance','No authority to invent results']],72,226,1136,391,[260,440,436],22);
    note(s,'Technical appendix based on source manifests and current AskDB service/DB layering. Optional RAG storage is excluded from the primary structured-data dependency path. Application DB persistence is distinct from query result calculation. No credentials, URLs with secrets or internal network locations appear.');break;
   case 20:
    heading(s,n,'Cost assumptions and calculation','Appendix · Hypothetical inference arithmetic, not a gateway quote.');
    table(s,[['Scenario input','Assumed value'],['Monthly questions / model-backed share','20,000 questions / 60%'],['Model-backed questions','12,000'],['Average input / output per call','1,500 / 300 tokens'],['Illustrative input / output rates','US$1 / US$4 per million tokens'],['Inference subtotal','18M × $1/M + 3.6M × $4/M = $32.40']],72,226,1136,323,[570,566],24);
    text(s,'Cost exclusions','Add reports, retries, hosting, database, monitoring, engineering and support.\nThis subtotal is not Scio total cost and is not compared with BI licence spend.',76,581,1120,68,23,C.amber);
    note(s,'Every workload and unit-rate figure on this slide is a stated hypothetical assumption. Arithmetic: 20,000×0.60=12,000 calls; 12,000×1,500=18,000,000 input tokens; 12,000×300=3,600,000 output tokens; 18×1+3.6×4=32.4 USD. Not an approved Capgemini endpoint quote, measured app usage or ROI result. Excludes additional report/narration/correction calls and all platform/operational costs. Use approved real inputs before business approval.');break;
   case 21:
    heading(s,n,'Demo questions and acceptance','Appendix · Separate a sample prompt from a verified demo outcome.');
    table(s,[['Question or action','What to verify'],['Revenue by model in [period]','Measure, grouping, dates and SQL'],['Units sold by permitted region in [period]','Units calculation and regional scope'],['Compare [model A] and [model B] in [period]','Both operands, measure and missing data'],['What is ASP?','Approved aggregate definition'],['Open a report in Analytics Builder','Consistent scope and report behavior'],['Rate a response; reopen history','Saved identity and feedback; no new analysis']],72,226,1136,369,[670,466],23);
    text(s,'Acceptance status','Live-provider and warehouse outcomes must be rehearsed in the target environment.',76,618,1128,35,21,C.muted);
    note(s,'Question bank uses approved Automotive measures and configurable catalog entity placeholders. Current source indicates relevant capabilities, not universal question accuracy. Check actual model names, dates, regional grants and feature flags. UI/history/feedback were tested with synthetic fixtures; actual provider/warehouse and Outlook acceptance must be reported separately.');break;
  }
 }
 return {slideCount:presentation.slides.items.length,range:[input.start,input.end]};
}
