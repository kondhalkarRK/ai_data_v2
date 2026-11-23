const {chromium}=require('@playwright/test');
const {pathToFileURL}=require('node:url');
const path=require('node:path'), fs=require('node:fs'), assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'msedge'});
 const out='tmp/soci-report-qa';fs.mkdirSync(out,{recursive:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[],network=[];page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/^https?:/.test(r.url()))network.push(r.url());});
  await page.goto(pathToFileURL(path.resolve('docs/reports/soci-client-readiness.html')).href);
  const ids=await page.locator('nav [data-page]').evaluateAll(nodes=>nodes.map(n=>n.dataset.page));
  assert.equal(ids.length,18);
  let sections=0;
  for(const theme of ['light','dark']){
   if(await page.locator('html').getAttribute('data-theme')!==theme)await page.locator('#theme').click();
   for(const id of ids){
    await page.locator(`nav [data-page="${id}"]`).click();
    assert((await page.locator('h1').innerText()).trim().length);
    assert(await page.locator('nav [aria-current="page"]').count()===1);
    assert(await page.locator('tbody tr').count()>0);
    const count=await page.locator('.subnav button').count();
    for(let i=1;i<count;i++){
     await page.locator('.subnav button').nth(i).click();
     assert.equal(await page.locator('#view > section').count(),1);
     assert(await page.locator('tbody tr').count()>0);sections++;
    }
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),id+' overflow');
   }
   await page.locator('nav [data-page="overview"]').click();
   await page.screenshot({path:`${out}/overview-${theme}.png`,fullPage:true});
   await page.locator('nav [data-page="semantic"]').click();
   await page.screenshot({path:`${out}/semantic-${theme}.png`,fullPage:true});
   await page.locator('nav [data-page="security"]').click();
   await page.getByRole('button',{name:'Users and passwords',exact:true}).click();
   await page.screenshot({path:`${out}/passwords-${theme}.png`,fullPage:true});
  }
  await page.emulateMedia({media:'print'});
  assert.equal(await page.locator('.sidebar').evaluate(e=>getComputedStyle(e).display),'none');
  assert.equal(await page.locator('.table-wrap').first().evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(255, 255, 255)');
  await page.emulateMedia({media:'screen'});
  await page.setViewportSize({width:390,height:844});
  await page.reload();
  assert.equal(await page.locator('.sidebar').isVisible(),false);
  await page.locator('#menu').click();assert(await page.locator('.sidebar').isVisible());
  await page.locator('nav [data-page="security"]').click();
  assert.equal(await page.locator('.sidebar').isVisible(),false);
  await page.getByRole('button',{name:'API endpoints',exact:true}).click();
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.screenshot({path:`${out}/mobile-security.png`,fullPage:true});
  await page.locator('#theme').click();const chosen=await page.locator('html').getAttribute('data-theme');await page.reload();
  assert.equal(await page.locator('html').getAttribute('data-theme'),chosen);
  assert.deepEqual(errors,[]);assert.deepEqual(network,[]);
  console.log(JSON.stringify({passed:true,navigationPages:ids.length,subsectionChecks:sections,themes:['light','dark'],mobileWidth:390,print:'checked',externalRequests:network.length,errors},null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
