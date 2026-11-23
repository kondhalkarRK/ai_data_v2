const INK='#1C2940',BODY='#4D5B70',BLUE='#345E98',PURPLE='#705696';
export async function theme({presentation,input}){
 for(let i=input.start;i<=input.end;i++){
 const s=presentation.slides.items[i];s.background.fill='#FFFFFF';
 for(const a of s.shapes.items){const p=a.toSnapshot(),n=p.name||'',t=p.text||'';
 if(p.fill&&p.fill.type!=='none')a.fill=/Stage|Central product|Sales|Application API/.test(n)?'#EAF0F8':/Feature panel [1357]|Model gateway|Business context|Application database/.test(n)?'#F1EDF7':'#F3F6FA';
 if(p.line?.width>0)a.line={fill:p.fill?.type==='none'?'#BCC8D9':'#D4DEEB',width:1.2};
 if(!t)continue;
 let size=23,color=BODY,bold=false;
 if(n==='Slide title'){size=44;color=INK;bold=true;}
 else if(n==='Brand'){size=100;color=INK;bold=true;}
 else if(n==='Value statement'){size=38;color=INK;}
 else if(n==='Descriptor'){size=27;color=BLUE;}
 else if(n==='Overview statement'){size=37;color=INK;bold=true;}
 else if(n==='Questions title'){size=76;color=INK;bold=true;}
 else if(n==='Closing brand'){size=48;color=BLUE;bold=true;}
 else if(n==='Section label'||n==='Brand footer'){size=15;color=PURPLE;bold=true;}
 else if(n==='Page'){size=17;}
 else if(/placeholder|Presenter/i.test(n)){size=17;}
 else if(n==='Slide context'){size=25;}
 else if(/^Panel number|^Stage index/.test(n)){size=20;color=PURPLE;bold=true;}
 else if(/^Panel title/.test(n)){size=28;color=/[1357]$/.test(n)?PURPLE:BLUE;bold=true;}
 else if(/^Panel body/.test(n)){size=24;}
 else if(/^Capability|^Control \d|^Quality heading|^Chat heading|^Feature heading/.test(n)){size=26;color=/[1357]$/.test(n)?PURPLE:BLUE;bold=true;}
 else if(/^Description|^Quality detail|^Chat body|^Control detail/.test(n)){size=23;}
 else if(/^Feature detail/.test(n)){size=20;}
 else if(/^Stage title/.test(n)){size=25;color=INK;bold=true;}
 else if(n==='Formula examples'){size=24;color=BLUE;}
 else if(n==='Central product name'){size=42;color=BLUE;bold=true;}
 else if(n==='Example question'){size=29;color=INK;bold=true;}
 else if(/ label$/.test(n)){size=n==='Sales label'?34:31;color=INK;bold=true;}
 else if(/ detail$/.test(n)){size=19;}
 else if(/ title$/.test(n)){size=25;color=/Application|Business context/.test(n)?PURPLE:BLUE;bold=true;}
 else if(/ detail$/.test(n)){size=20;}
 else if(/connection$/.test(n)){size=17;}
 else if(n==='Discussion topics'){size=27;color=BLUE;}
 else if(n==='Discussion context'){size=24;}
 else if(n==='Cost qualification'){size=20;}
 a.text.style={fontFamily:'Aptos',fontSize:size,color,bold};
 }
 }
 return {slides:presentation.slides.items.length,updated:[input.start+1,input.end+1]};
}
