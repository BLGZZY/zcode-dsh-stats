async (page) => {
  page.setDefaultTimeout(5000);
  const check = (ok, label) => { if (!ok) throw new Error(label); };
  const passed=[];
  const rows = async card => card.locator('.body .line').evaluateAll(items => items.map(row =>
    [row.querySelector('.label').textContent, row.querySelector('.value').textContent]));
  const equalRows = async (card, expected, label) => check(JSON.stringify(await rows(card))===JSON.stringify(expected), label);
  const setStats = async patch => page.evaluate(patch => {
    window.demoPacket=()=>{const packet=window.acceptanceBasePacket();Object.assign(packet.sessions.demo,patch);return packet;};
    window.__dshStats.receive(window.demoPacket());
  },patch);
  const assertSingleCard = async (card, kind) => {
    check(await page.getByRole('dialog').count()===1, kind+' is the only visible card');
    check(await page.locator('[data-dsh-stats] .row button[aria-expanded="true"]').count()===1, kind+' is the only expanded button');
    const trigger=page.locator('[data-dsh-stats] .row button.'+kind);
    const [a,b]=await Promise.all([card.boundingBox(),trigger.boundingBox()]);
    check(Math.abs(a.x-b.x)<2 && a.y+a.height<=b.y && b.y-a.y-a.height<=10,kind+' anchors above its own button');
  };
  await page.goto('http://127.0.0.1:8766/preview.html');
  await page.setViewportSize({width: 1100, height: 800});
  await page.evaluate(()=>{window.acceptanceBasePacket=window.demoPacket;});
  await page.getByRole('button', {name:'6 轮 58 步 · 204 tok/s'}).waitFor();
  const geometry = await page.evaluate(() => {
    const host = document.querySelector('[data-dsh-stats]');
    const card = document.querySelector('.chat-composer-input-surface');
    const layout = document.querySelector('[data-composer-layout]');
    const h = host.getBoundingClientRect(), c = card.getBoundingClientRect();
    const buttons = [...host.shadowRoot.querySelectorAll('.row button')].map(b=>b.getBoundingClientRect());
    host.style.display = 'none';
    const without = card.getBoundingClientRect().height;
    host.style.removeProperty('display');
    return {outside: !layout.contains(host) && !card.contains(host) && card.nextElementSibling === host,
      extraHeight: h.bottom-c.bottom, cardUnchanged: c.height === without,
      oneRow: buttons.every(b=>b.top === buttons[0].top),
      centered: Math.abs((buttons[0].left+buttons.at(-1).right)/2-(c.left+c.right)/2)<1};
  });
  check(geometry.outside && geometry.cardUnchanged, 'outside card without increasing input height');
  check(geometry.extraHeight > 0 && geometry.extraHeight <= 27 && geometry.oneRow && geometry.centered, 'centered single row uses at most 27px');
  check(await page.evaluate(()=>{
    const dock=document.querySelector('[data-v4-composer-dock-content]');
    const host=dock.querySelector('[data-dsh-stats]');
    return getComputedStyle(dock).paddingBottom==='2px' && Math.abs(dock.getBoundingClientRect().bottom-host.getBoundingClientRect().bottom-2)<1;
  }), 'footer sits 2px from dock bottom');
  await page.screenshot({path:'output/playwright/light.png'});
  await page.getByRole('button', {name:'6 轮 58 步 · 204 tok/s'}).click();
  const panel=page.getByRole('dialog', {name:'会话统计详情'});
  await panel.waitFor({state:'visible'});
  check(await panel.evaluate(el=>el.matches(':popover-open')), 'native top-layer');
  const rect=await panel.boundingBox();
  check(rect.x>=0 && rect.y>=0 && rect.x+rect.width<=1100 && rect.y+rect.height<=800,'detail stays in viewport');
  await page.screenshot({path:'output/playwright/detail.png'});
  await equalRows(panel,[['模型用时','8分 23秒'],['工具调用用时','13分 20秒'],['首 token 平均（TTFT）','3.9秒'],['输出速度（TPS）','204 tok/s']], 'activity has exactly four timing/speed rows');
  check(!(await panel.textContent()).includes('缓存命中') && !(await panel.textContent()).includes('5,230,601'), 'activity excludes token breakdown');
  await assertSingleCard(panel,'activity');
  passed.push('activity exact four metrics');
  await page.evaluate(()=>{window.acceptanceEscapes=0;document.addEventListener('keydown',e=>{if(e.key==='Escape')window.acceptanceEscapes++;});});
  await page.keyboard.press('Escape');
  await panel.waitFor({state:'hidden'});
  check(await page.evaluate(()=>window.acceptanceEscapes===0 && document.querySelector('[data-dsh-stats]').shadowRoot.activeElement?.className==='activity'),'Escape stays inside stats and returns focus');
  const usage=page.getByRole('dialog',{name:'Token 用量详情'});
  const context=page.getByRole('dialog',{name:'上下文占用详情'});
  await page.locator('[data-dsh-stats] .usage').click();
  await usage.waitFor({state:'visible'});
  check(await usage.locator('.headline').textContent()==='5,230,601 tok','usage headline preserves full total');
  await equalRows(usage,[['缓存命中','83%'],['未缓存输入','874,308 tok'],['缓存读取','4,299,648 tok'],['输出','56,645 tok']], 'usage contains cache and input/output only');
  check(!/模型用时|工具调用用时|TTFT|TPS/.test(await usage.textContent()),'usage excludes activity metrics');
  await assertSingleCard(usage,'usage');
  await page.screenshot({path:'output/playwright/cards-usage.png'});
  // Switching directly between buttons must replace, rather than stack, cards.
  await page.locator('[data-dsh-stats] .context').click();
  await context.waitFor({state:'visible'});
  await assertSingleCard(context,'context');
  check(await context.locator('.title').textContent()==='上下文已用 16%' && await context.locator('.headline').textContent()==='160K / 1M','context headline follows native used/max');
  await equalRows(context,[['已用上下文','160,000 tok'],['剩余可用','840,000 tok'],['上下文上限','1,000,000 tok']], 'context has native used, remaining and limit without invented categories');
  const meter=context.getByRole('progressbar',{name:'上下文占用'});
  check(await meter.getAttribute('aria-valuenow')==='16' && await meter.getAttribute('aria-valuetext')==='160,000 / 1,000,000 token','context accessible progress follows native values');
  check(await meter.evaluate(el=>el.children.length===1 && el.firstElementChild.style.width==='16%'),'context progress is one actual-used segment');
  await page.screenshot({path:'output/playwright/cards-context.png'});
  await page.locator('[data-dsh-stats] .context').click();
  await context.waitFor({state:'hidden'});
  passed.push('usage exact totals and isolation','native context and progress','three independent anchors','one card at a time','same button toggles closed','Escape focus and propagation');
  // Verified Windows 3.14.4 exposes the legacy composer markers without data-composer-layout.
  await page.evaluate(()=>{
    const composer=document.querySelector('[data-composer-layout]'), input=composer.querySelector('textarea');
    const surface=document.querySelector('.chat-composer-input-surface');
    const rect=el=>{const r=el.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};};
    window.acceptanceLegacyFixture={composer,input,surface,layout:composer.getAttribute('data-composer-layout'),
      className:composer.className,testid:input.getAttribute('data-testid'),lexical:input.getAttribute('data-lexical-editor'),
      surfaceRect:rect(surface),hostRect:rect(document.querySelector('[data-dsh-stats]'))};
    composer.classList.add('border-input-border');
    input.setAttribute('data-testid','v4-composer-input');input.setAttribute('data-lexical-editor','true');
    composer.removeAttribute('data-composer-layout');
    window.__dshStats.receive(window.demoPacket());
  });
  await page.getByRole('button',{name:'6 轮 58 步 · 204 tok/s'}).waitFor();
  check(await page.evaluate(()=>{
    const saved=window.acceptanceLegacyFixture,hosts=document.querySelectorAll('[data-dsh-stats]');
    const matches=(el,before)=>{const r=el.getBoundingClientRect();return ['x','y','width','height'].every(k=>Math.abs(r[k]-before[k])<1);};
    return !document.querySelector('[data-composer-layout]') && hosts.length===1 &&
      hosts[0].closest('[data-session-id]')?.dataset.sessionId==='demo' && saved.surface.nextElementSibling===hosts[0] &&
      matches(saved.surface,saved.surfaceRect) && matches(hosts[0],saved.hostRect);
  }),'legacy profile has one correctly scoped host and unchanged composer/footer geometry');
  await page.locator('[data-dsh-stats] .activity').click();
  await panel.waitFor({state:'visible'});
  await assertSingleCard(panel,'activity');
  await equalRows(panel,[['模型用时','8分 23秒'],['工具调用用时','13分 20秒'],['首 token 平均（TTFT）','3.9秒'],['输出速度（TPS）','204 tok/s']], 'legacy profile keeps session statistics and card anchor');
  await page.keyboard.press('Escape');
  await page.evaluate(()=>{
    const s=window.acceptanceLegacyFixture;s.composer.className=s.className;s.composer.setAttribute('data-composer-layout',s.layout);
    for(const [name,value] of [['data-testid',s.testid],['data-lexical-editor',s.lexical]]) {
      if(value===null)s.input.removeAttribute(name);else s.input.setAttribute(name,value);
    }
    delete window.acceptanceLegacyFixture;window.__dshStats.receive(window.demoPacket());
  });
  check(await page.locator('[data-dsh-stats]').count()===1,'restored modern profile keeps exactly one host');
  passed.push('Windows 3.14.4 legacy profile mount, scope and geometry');
  // A live paint must preserve the close node and keyboard focus in every card.
  for (const [kind,card] of [['activity',panel],['usage',usage],['context',context]]) {
    await page.locator('[data-dsh-stats] .'+kind).click();
    await card.getByRole('button',{name:'关闭详情'}).focus();
    await page.evaluate(()=>{window.acceptanceClose=document.querySelector('[data-dsh-stats]').shadowRoot.activeElement;});
    if(kind==='context') await page.evaluate(()=>{document.querySelector('[data-usage-used]').dataset.usageUsed='161000';window.__dshStats.receive(window.demoPacket());});
    else await setStats(kind==='activity'?{tps:205.4,modelMs:497000}:{tokens:5230602});
    check(await page.evaluate(()=>{const s=document.querySelector('[data-dsh-stats]').shadowRoot;return s.activeElement===window.acceptanceClose && window.acceptanceClose.isConnected;}),kind+' live update keeps close focused');
    check((await card.textContent()).includes(kind==='activity'?'205 tok/s':kind==='usage'?'5,230,602 tok':'161,000 tok'),kind+' receives changed data while open');
    await page.keyboard.press('Escape');
    await setStats({});
  }
  await page.evaluate(()=>{document.querySelector('[data-usage-used]').dataset.usageUsed='160000';window.__dshStats.receive(window.demoPacket());});
  passed.push('live updates preserve close focus in all cards');
  await setStats({modelSamples:57,toolSamples:73,ttftMs:222300,ttftSamples:57,speedSamples:57,tokenSamples:57,cacheSamples:57,cacheReadSamples:57,outputSamples:57,cacheWriteTokens:null,cacheWriteSamples:0,uncachedInputTokens:null,uncachedInputSamples:0,nonCacheReadInputTokens:874308,nonCacheReadInputSamples:57});
  await page.locator('[data-dsh-stats] .activity').click();
  await equalRows(panel,[['模型用时','8分 23秒*'],['工具调用用时','13分 20秒*'],['首 token 平均（TTFT）','3.9秒*'],['输出速度（TPS）','204 tok/s*']],'partial activity metrics carry stars');
  check((await panel.locator('.footnote').textContent()).includes('模型 57/58') && (await panel.locator('.footnote').textContent()).includes('工具 73/74'),'partial activity explains sample coverage');
  await page.locator('[data-dsh-stats] .usage').click();
  check(await usage.locator('.headline').textContent()==='5,230,601 tok*','partial total is marked');
  await equalRows(usage,[['缓存命中','83%*'],['非缓存读取输入','874,308 tok*'],['缓存读取','4,299,648 tok*'],['输出','56,645 tok*']],'missing write data uses non-cache-read input fallback');
  check((await usage.locator('.label').filter({hasText:'非缓存读取输入'}).getAttribute('title')).includes('可能包含'),'fallback explains potentially unreported writes');
  check((await usage.locator('.footnote').textContent()).includes('输入 57/58'),'partial usage explains input coverage');
  passed.push('partial sample markers and coverage','missing cache writes fallback');
  await page.keyboard.press('Escape');
  // Missing raw timing/context fields must remain unknown instead of becoming zero.
  await setStats({modelMs:null,toolMs:null,ttftMs:null,ttftSamples:0,tps:null});
  await page.locator('[data-dsh-stats] .activity').click();
  check((await rows(panel)).every(([,value])=>value==='—'),'missing activity values remain unknown');
  await page.evaluate(()=>{const n=document.querySelector('[data-usage-used]');n.dataset.usageUsed='';n.dataset.usageMax='';window.__dshStats.receive(window.demoPacket());});
  await page.locator('[data-dsh-stats] .context').click();
  check(await context.locator('.headline').textContent()==='— / —' && (await rows(context)).every(([,value])=>value==='—'),'missing context is unknown');
  check(await context.getByRole('progressbar').getAttribute('aria-valuenow')===null && (await context.locator('.footnote').textContent()).includes('不可用'),'unknown context has no fake percentage');
  await page.keyboard.press('Escape');
  await setStats({});
  await page.evaluate(()=>{const n=document.querySelector('[data-usage-used]');n.dataset.usageUsed='160000';n.dataset.usageMax='1000000';window.__dshStats.receive(window.demoPacket());});
  passed.push('unknown metrics and context stay unknown');
  await page.getByRole('button', {name:'切换明暗'}).click();
  await page.waitForFunction(()=>document.querySelector('[data-dsh-stats]').hasAttribute('data-dark'));
  await page.screenshot({path:'output/playwright/dark.png'});
  await page.setViewportSize({width:390,height:740});
  await page.waitForFunction(()=>document.querySelector('[data-dsh-stats]').hasAttribute('data-narrow'));
  check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'no horizontal overflow');
  await page.getByRole('button', {name:'204 tok/s', exact:true}).click();
  const small=await panel.boundingBox();
  check(small.x>=0 && small.x+small.width<=390,'narrow detail fits');
  await page.keyboard.press('Escape');
  await page.screenshot({path:'output/playwright/narrow.png'});
  // Highspeed applies clipping/background to the outer surface, not to the input layout.
  await page.evaluate(()=>{const c=document.querySelector('.chat-composer-input-surface');c.classList.add('highspeed-composer-surface');c.style.cssText='border:1px solid purple;border-radius:18px;overflow:hidden';});
  check(await page.evaluate(()=>{
    const h=document.querySelector('[data-dsh-stats]'), c=document.querySelector('.highspeed-composer-surface');
    return c.nextElementSibling===h && h.getBoundingClientRect().top>=c.getBoundingClientRect().bottom;
  }), 'outside Highspeed card and its clipping');
  await page.setViewportSize({width:320,height:740});
  await page.waitForFunction(()=>document.querySelector('[data-dsh-stats]').hasAttribute('data-narrow'));
  check(await page.evaluate(()=>{
    const h=document.querySelector('[data-dsh-stats]'),r=h.shadowRoot.querySelector('.row');
    return r.scrollWidth<=r.clientWidth && r.getBoundingClientRect().height===24;
  }), '320px footer stays one row without overflow');
  // Empty/new/remote sessions must never inherit a previous conversation's statistics.
  await page.evaluate(()=>document.querySelector('[data-session-id]').dataset.sessionId='different-session');
  await page.getByRole('button', {name:'— tok/s',exact:true}).waitFor();
  check(await page.getByText('204 tok/s',{exact:true}).count()===0,'old speed removed on session switch');
  await page.evaluate(()=>document.querySelector('[data-session-id]').dataset.sessionId='draft');
  await page.waitForFunction(()=>!document.querySelector('[data-dsh-stats]'));
  check(await page.evaluate(()=>getComputedStyle(document.querySelector('[data-v4-composer-dock-content]')).paddingBottom==='16px'), 'draft restores native bottom spacing');
  // Multiple panes, each with its own data; no duplicate after composer replacement.
  await page.setViewportSize({width:1100,height:800});
  await page.evaluate(()=>{
    const a=document.querySelector('main');a.dataset.sessionId='demo';
    const b=a.cloneNode(true);b.dataset.sessionId='second';b.dataset.paneId='second';document.body.append(b);
    document.body.style.cssText='display:flex;flex-wrap:wrap';document.querySelector('header').style.width='100%';
    for(const main of [a,b]){main.querySelector('article').remove();main.querySelector('.caption').remove();main.style.cssText='width:50%;margin:0;padding:24px 12px';}
    const base=window.demoPacket;
    window.demoPacket=()=>{const packet=base();packet.sessions.second={...packet.sessions.demo,tps:33,tokens:1234};return packet;};
    window.__dshStats.receive(window.demoPacket());
  });
  await page.getByRole('button',{name:/33 tok\/s/}).waitFor();
  check(await page.locator('[data-dsh-stats]').count()===2,'split panes mount exactly once');
  await page.locator('[data-dsh-stats] .activity').first().click();
  await page.locator('[data-dsh-stats] .usage').last().click();
  check(await page.getByRole('dialog').count()===1 && await page.getByRole('dialog',{name:'Token 用量详情'}).locator('.headline').textContent()==='1,234 tok','switching panes leaves only the newly selected card with its own data');
  await page.keyboard.press('Escape');
  passed.push('one card across split panes');
  await page.evaluate(()=>{
    const original=window.demoPacket;
    window.demoPacket=()=>({...original(),at:Date.now()-20000});
    window.__dshStats.receive(window.demoPacket());
  });
  await page.getByRole('button',{name:/— tok\/s/}).first().click();
  const staleActivity=page.getByRole('dialog',{name:'会话统计详情'});
  check((await rows(staleActivity)).every(([,value])=>value==='—') && (await staleActivity.locator('.footnote').textContent()).includes('过期'),'stale activity hides every timing and speed value with explanation');
  await page.locator('[data-dsh-stats] .usage').first().click();
  const staleUsage=page.getByRole('dialog',{name:'Token 用量详情'});
  check(await staleUsage.locator('.headline').textContent()==='—' && (await rows(staleUsage)).every(([,value])=>value==='—') && (await staleUsage.locator('.footnote').textContent()).includes('过期'),'stale usage hides total and all breakdown values');
  await page.locator('[data-dsh-stats] .context').first().click();
  const liveContext=page.getByRole('dialog',{name:'上下文占用详情'});
  check(await liveContext.getByRole('progressbar').getAttribute('aria-valuenow')==='16' && await liveContext.locator('.headline').textContent()==='160K / 1M','stale collector does not hide independent live native context');
  passed.push('stale activity and usage hide values','native context survives stale collector');
  await page.evaluate(()=>window.__dshStats.dispose());
  check(await page.locator('[data-dsh-stats]').count()===0,'dispose cleans all hosts');
  check(await page.evaluate(()=>!document.querySelector('[data-dsh-stats-layout]') && [...document.querySelectorAll('[data-v4-composer-dock-content]')].every(d=>getComputedStyle(d).paddingBottom==='16px')), 'dispose restores native dock styles');
  return {passed:[...passed,'outside-card mount','27px centered single row','2px bottom gutter','native gutter restored','Highspeed clipping','320px width','top-layer details','Escape','light/dark','390px width','session switch','draft cleanup','split panes','stale detail','dispose']};
}
