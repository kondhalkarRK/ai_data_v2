const {chromium}=require('@playwright/test');
const fs=require('node:fs');
const assert=require('node:assert/strict');
(async()=>{
 const css=fs.readFileSync('apps/web/app/globals.css','utf8').replace(/^@import.*$/gm,'');
 const browser=await chromium.launch({headless:true,channel:'msedge'});
 try {
  const page=await browser.newPage();
  await page.setContent(`<style>${css}</style><div class="executive-cockpit" data-chart-palette="classic"><svg><rect id="probe" width="50" height="50" fill="var(--executive-vibrant-category-1, #123456)"/><rect id="category" x="55" width="50" height="50" fill="var(--executive-category-1)"/></svg></div>`);
  const results=[];
  for(const theme of ['', 'dark', 'theme-ai']){
   await page.evaluate(t=>document.documentElement.className=t,theme);
   const read=()=>page.evaluate(()=>({bar:getComputedStyle(document.querySelector('#probe')).fill,category:getComputedStyle(document.querySelector('#category')).fill}));
   await page.locator('.executive-cockpit').evaluate(el=>el.dataset.chartPalette='classic');
   const classic=await read();
   await page.locator('.executive-cockpit').evaluate(el=>el.dataset.chartPalette='vibrant');
   const vibrant=await read();
   assert.notEqual(classic.bar,vibrant.bar);assert.notEqual(classic.category,vibrant.category);
   assert.notEqual(vibrant.bar,'rgb(0, 0, 0)');
   results.push({theme:theme||'light',classic,vibrant});
  }
  const ts=require('typescript');
  const motion=ts.transpileModule(fs.readFileSync('apps/web/components/executive/cockpit/chart-motion.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  await page.addScriptTag({content:`(()=>{const exports={};${motion};window.animateChart=exports.animateChart;})()`});
  await page.evaluate(()=>{
   const body=document.createElement('div'); body.id='motion';
   body.innerHTML='<svg width="150" height="80"><path data-chart-line d="M0 70 L30 40 L75 60 L150 10" fill="none" stroke="blue"/><rect data-chart-reveal width="40" height="40" fill="teal"/></svg>';
   document.body.append(body);window.stopChartMotion=window.animateChart(body);
  });
  assert(await page.evaluate(()=>document.querySelector('#motion').getAnimations({subtree:true}).length>0));
  await page.evaluate(()=>window.dispatchEvent(new Event('beforeprint')));
  assert(await page.evaluate(()=>document.querySelector('#motion').getAnimations({subtree:true}).every(a=>a.playState==='finished')));
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.evaluate(()=>{window.stopChartMotion();window.stopChartMotion=window.animateChart(document.querySelector('#motion'));});
  assert.equal(await page.evaluate(()=>document.querySelector('#motion').getAnimations({subtree:true}).length),0);
  const homeCss=fs.readFileSync('apps/web/components/home/home-workspace.module.css','utf8');
  await page.addStyleTag({content:homeCss});
  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.evaluate(()=>{const demo=document.createElement('div');demo.className='demoChart';demo.id='demo';demo.innerHTML='<svg><path class="connector" d="M0 0 L100 100"/></svg>';document.body.append(demo);});
  assert.equal(await page.locator('#demo .connector').evaluate(el=>getComputedStyle(el).animationDuration),'3s');
  assert.equal(await page.locator('#demo .connector').evaluate(el=>getComputedStyle(el).animationIterationCount),'infinite');
  await page.locator('#demo').evaluate(el=>el.dataset.animationPaused='true');
  assert.equal(await page.locator('#demo .connector').evaluate(el=>getComputedStyle(el).animationPlayState),'paused');
  await page.emulateMedia({reducedMotion:'reduce'});
  assert.equal(await page.locator('#demo .connector').evaluate(el=>getComputedStyle(el).animationName),'none');
  console.log(JSON.stringify({passed:true,results,motion:'reveal, print completion, reduced-motion, home repeat and pause passed'},null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
