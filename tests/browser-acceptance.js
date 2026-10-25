async (page) => {
  page.setDefaultTimeout(5000);
  const check = (ok, label) => { if (!ok) throw new Error(label); };
  await page.goto('http://127.0.0.1:8766/preview.html');
  await page.setViewportSize({width: 1100, height: 800});
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
  await page.keyboard.press('Escape');
  await panel.waitFor({state:'hidden'});
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
  await page.evaluate(()=>{
    const original=window.demoPacket;
    window.demoPacket=()=>({...original(),at:Date.now()-20000});
    window.__dshStats.receive(window.demoPacket());
  });
  await page.getByRole('button',{name:/— tok\/s/}).first().click();
  check(!(await page.getByRole('dialog',{name:'会话统计详情'}).first().textContent()).includes('204 tok/s'),'stale detail never shows a live-looking number');
  await page.evaluate(()=>window.__dshStats.dispose());
  check(await page.locator('[data-dsh-stats]').count()===0,'dispose cleans all hosts');
  check(await page.evaluate(()=>!document.querySelector('[data-dsh-stats-layout]') && [...document.querySelectorAll('[data-v4-composer-dock-content]')].every(d=>getComputedStyle(d).paddingBottom==='16px')), 'dispose restores native dock styles');
  return {passed:['outside-card mount','27px centered single row','2px bottom gutter','native gutter restored','Highspeed clipping','320px width','top-layer details','Escape','light/dark','390px width','session switch','draft cleanup','split panes','stale detail','dispose']};
}
