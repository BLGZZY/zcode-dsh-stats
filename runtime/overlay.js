/* DSH-style compact statistics; no credentials, model calls or native React state access. */
(() => {
  'use strict';
  window.__dshStats?.dispose();
  const roots = new Map();
  // Only compact the native 16px dock gutter while our row is actually mounted.
  // A scoped rule preserves React's styles and restores native spacing on cleanup/drafts.
  const dockStyle = document.createElement('style');
  dockStyle.dataset.dshStatsLayout = '0.4.0';
  dockStyle.textContent = '[data-v4-composer-dock-content].pb-4:has([data-dsh-stats]){padding-bottom:2px!important}';
  document.head.appendChild(dockStyle);
  let packet = { sessions: {}, at: 0 }, dead = false;
  const css = `
    :host{display:block;color:var(--color-foreground-subtle,#626773);font:12px/20px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color-scheme:light dark;min-width:0;width:100%;margin-top:3px;flex:none}
    *{box-sizing:border-box}.row{display:flex;justify-content:center;align-items:center;gap:8px;flex-wrap:nowrap;min-width:0;height:24px;padding:0;font-variant-numeric:tabular-nums}
    button{font:inherit;color:inherit;border:0;background:transparent;border-radius:6px;padding:2px 4px;display:inline-flex;align-items:center;gap:6px;cursor:pointer;white-space:nowrap;min-height:24px;flex:none}
    button:hover,button[aria-expanded=true]{background:var(--color-surface-hover,rgba(128,128,128,.12));color:var(--color-foreground,#252831)}
    button:focus-visible{outline:2px solid #6b85bd;outline-offset:1px}svg{width:14px;height:14px;flex:none}.muted{opacity:.65}.short{display:none}
    .details{position:fixed;inset:auto;margin:0;z-index:2147483000;width:310px;max-width:calc(100vw - 24px);max-height:calc(100vh - 24px);overflow:auto;overscroll-behavior:contain;background:var(--color-background,#fafafb);color:var(--color-foreground,#252831);border:1px solid var(--color-border,rgba(128,128,128,.18));border-radius:16px;box-shadow:0 8px 30px #00000016;padding:16px;font:12px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-variant-numeric:tabular-nums}
    .details[hidden]{display:none}.card-head{display:flex;align-items:center;gap:8px;padding-bottom:10px;margin-bottom:8px;border-bottom:1px solid #8883}.title{display:flex;align-items:center;gap:7px;font-weight:600;font-size:13px;white-space:nowrap}.headline{margin-left:auto;white-space:nowrap;font-weight:550}.details .close{flex:none;min-height:20px;width:20px;justify-content:center;padding:0;margin-right:-7px;color:var(--color-foreground-subtle,#737985)}
    .line{display:flex;align-items:center;justify-content:space-between;gap:14px;min-height:25px}.label{color:var(--color-foreground-subtle,#7b808b)}.value{text-align:right;white-space:nowrap}.footnote{color:var(--color-foreground-subtle,#7b808b);font-size:11px;margin-top:9px;line-height:1.5}.footnote[hidden]{display:none}
    .details[data-kind=context] .card-head{border-bottom:0;margin-bottom:10px;padding-bottom:0}.meter{height:5px;display:flex;overflow:hidden;border-radius:5px;background:#8882;margin:4px 0 12px}.used{background:#4b8eff;height:100%}.legend{display:inline-flex;align-items:center;gap:7px}.swatch{height:8px;width:8px;border-radius:2px;background:#4b8eff;flex:none}.swatch.remaining{background:#b4bac4}.meter[data-warning] .used,.swatch[data-warning]{background:#d79b40}
    :host([data-narrow]) .extra{display:none}:host([data-narrow]) .short{display:inline}:host([data-narrow]) button{padding-inline:4px}
    :host([data-dark]){color:#a5a9b3}:host([data-dark]) .details{background:#25262a;color:#e5e6eb}:host([data-dark]) button:hover{color:#e5e6eb}
  `;
  const icons = {
    activity: '<path d="M3.34 19a10 10 0 1 1 17.32 0M12 13l4-4"/><circle cx="12" cy="13" r="1"/>',
    database: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0"/>',
    ring: '<circle cx="12" cy="12" r="9" opacity=".2"/><circle class="arc" cx="12" cy="12" r="9" transform="rotate(-90 12 12)" stroke-dasharray="0 57"/>'
  };
  const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">${icons[name]}</svg>`;
  const finite = n => typeof n === 'number' && Number.isFinite(n) && n >= 0;
  const compact = n => !finite(n) ? '—' : new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 }).format(n);
  const percent = n => finite(n) ? `${Math.round(n * 100)}%` : '—';
  const speed = n => finite(n) ? `${n.toFixed(n < 10 ? 1 : 0)} tok/s` : '— tok/s';
  const full = n => finite(n) ? new Intl.NumberFormat('zh-CN').format(n) : '未知';
  const tok = n => finite(n) ? `${full(n)} tok` : '—';
  const duration = ms => {
    if (!finite(ms)) return '—';
    if (ms < 1000) return `${Math.round(ms)}毫秒`;
    if (ms < 60000) return `${Number((ms / 1000).toFixed(1))}秒`;
    const seconds = Math.floor(ms / 1000), minutes = Math.floor(seconds / 60);
    return minutes < 60 ? `${minutes}分 ${seconds % 60}秒` : `${Math.floor(minutes / 60)}小时 ${minutes % 60}分`;
  };
  function visible(el) {
    if (el.closest('[inert],[aria-hidden="true"],[role="dialog"]')) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 80 || r.height < 8 || r.bottom < 0 || r.top > innerHeight) return false;
    for (let p = el; p; p = p.parentElement) {
      const s = getComputedStyle(p);
      if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') return false;
    }
    return true;
  }
  function nativeUsage(pane) {
    const node = pane.querySelector('[data-usage-used][data-usage-max]');
    if (node && node.dataset.usageUsed !== '' && node.dataset.usageMax !== '') {
      const used = Number(node.dataset.usageUsed), max = Number(node.dataset.usageMax);
      if (finite(used) && finite(max) && max > 0) return { used, max };
    }
    for (const node of pane.querySelectorAll('button[aria-label]')) {
      const m = node.getAttribute('aria-label').match(/(?:已用|used)\s*([\d,]+)\s*\/\s*(?:总量|total)\s*([\d,]+)/i);
      if (m) {
        const used = Number(m[1].replaceAll(',', '')), max = Number(m[2].replaceAll(',', ''));
        if (finite(used) && finite(max) && max > 0) return { used, max };
      }
    }
    return null;
  }
  function create(form, layout, anchor, pane, sid) {
    const host = document.createElement('div');
    host.dataset.dshStats = '0.4.0';
    const shadow = host.attachShadow({ mode: 'open' });
    shadow.innerHTML = `<style>${css}</style><div class="row" role="group" aria-label="会话用量统计">
      <button type="button" class="activity" aria-haspopup="dialog" aria-expanded="false">${icon('activity')}<span class="counts extra"></span><span class="muted extra">·</span><span class="speed"></span></button>
      <button type="button" class="usage" aria-haspopup="dialog" aria-expanded="false">${icon('database')}<span class="total"></span><span class="cache extra"></span></button>
      <button type="button" class="context" aria-haspopup="dialog" aria-expanded="false">${icon('ring')}<span class="pressure"></span></button></div>
      <div class="details" popover="manual" role="dialog" aria-label="会话统计详情" hidden><div class="card-head"><div class="title"></div><div class="headline"></div><button type="button" class="close" aria-label="关闭详情">×</button></div><div class="body"></div><div class="footnote" hidden></div></div>`;
    // Keep telemetry outside the bordered input card so it never increases the editor's height.
    anchor.after(host);
    const state = { host, shadow, form, layout, anchor, pane, sid, data: null, dataStatus: 'waiting', context: null, trigger: null, kind: 'activity' };
    const panel = shadow.querySelector('.details');
    state.close = () => {
      if (panel.matches(':popover-open')) panel.hidePopover();
      panel.hidden = true;
      shadow.querySelectorAll('[aria-expanded]').forEach(b => b.setAttribute('aria-expanded', 'false'));
    };
    function detail() {
      const d = state.data;
      const body = shadow.querySelector('.body'), title = shadow.querySelector('.title');
      const headline = shadow.querySelector('.headline'), footnote = shadow.querySelector('.footnote');
      body.replaceChildren();headline.textContent = '';headline.removeAttribute('title');
      panel.dataset.kind = state.kind;
      const labels = { activity: ['activity', '会话统计'], usage: ['database', 'Token 用量'], context: ['ring', '上下文已用'] };
      const [glyph, label] = labels[state.kind];
      title.innerHTML = icon(glyph);title.append(document.createTextNode(label));
      panel.setAttribute('aria-label', state.kind === 'activity' ? '会话统计详情' : state.kind === 'usage' ? 'Token 用量详情' : '上下文占用详情');
      const partial = [];
      function metric(value, samples, total, format, name) {
        const incomplete = finite(value) && finite(samples) && finite(total) && samples < total;
        if (incomplete) partial.push(`${name} ${samples}/${total}`);
        return { text: finite(value) ? format(value) + (incomplete ? '*' : '') : '—',
          hint: finite(samples) && finite(total) ? `有效样本 ${samples} / ${total}` : '当前客户端未提供这项数据' };
      }
      function line(label, value, help = '', color = '') {
        const row = document.createElement('div');row.className = 'line';
        const a = document.createElement('span'), b = document.createElement('span');
        a.className = 'label';b.className = 'value';a.textContent = label;
        if (help) a.title = help;
        if (color) { a.classList.add('legend');const dot = document.createElement('i');dot.className = `swatch ${color}`;a.prepend(dot); }
        b.textContent = typeof value === 'string' ? value : value.text;
        if (value.hint) b.title = value.hint;
        row.append(a, b);body.append(row);
      }
      let note = '';
      if (state.kind === 'activity') {
        line('模型用时', metric(d?.modelMs, d?.modelSamples, d?.steps, duration, '模型'), '客户端记录的已完成主请求总耗时，含首 token 等待及准备、重试、收尾开销，并非纯服务端推理时间。');
        line('工具调用用时', metric(d?.toolMs, d?.toolSamples, d?.toolCalls, duration, '工具'), '与主回合关联的工具调用从调度到终态的耗时之和，含排队、审批等待及失败/取消；并行调用会累加。');
        line('首 token 平均（TTFT）', metric(finite(d?.ttftMs) && d?.ttftSamples > 0 ? d.ttftMs / d.ttftSamples : null, d?.ttftSamples, d?.steps, duration, '首 token'), '有效首 token 等待时间的算术平均。');
        line('输出速度（TPS）', metric(d?.tps, d?.speedSamples, d?.steps, speed, '速度'), '有效样本的输出 token 总和 ÷ 解码耗时总和。');
      } else if (state.kind === 'usage') {
        const total = metric(d?.tokens, d?.tokenSamples, d?.steps, tok, '总量');
        headline.textContent = total.text;headline.title = total.hint;
        line('缓存命中', metric(d?.cacheHit, d?.cacheSamples, d?.steps, percent, '命中率'));
        const writesKnown = d && d.cacheWriteSamples === d.steps;
        line(writesKnown ? '未缓存输入' : '非缓存读取输入', metric(writesKnown ? d?.uncachedInputTokens : d?.nonCacheReadInputTokens, writesKnown ? d?.uncachedInputSamples : d?.nonCacheReadInputSamples, d?.steps, tok, '输入'), writesKnown ? '输入减去缓存读取与缓存写入。' : '输入减去缓存读取；可能包含未单独上报的缓存写入。');
        line('缓存读取', metric(d?.cacheReadTokens, d?.cacheReadSamples, d?.steps, tok, '缓存读取'));
        if (d?.cacheWriteTokens > 0 && writesKnown) line('缓存写入', metric(d.cacheWriteTokens, d.cacheWriteSamples, d.steps, tok, '缓存写入'));
        line('输出', metric(d?.outputTokens, d?.outputSamples, d?.steps, tok, '输出'));
      } else {
        const c = state.context, ratio = c ? c.used / c.max : null;
        title.replaceChildren(document.createTextNode('上下文已用 ' + percent(ratio)));
        headline.textContent = c ? `${compact(c.used)} / ${compact(c.max)}` : '— / —';
        const meter = document.createElement('div');meter.className = 'meter';meter.setAttribute('role', 'progressbar');meter.setAttribute('aria-label', '上下文占用');
        meter.setAttribute('aria-valuemin', '0');meter.setAttribute('aria-valuemax', '100');
        if (c) { meter.setAttribute('aria-valuenow', String(Math.min(100, Math.round(ratio * 100))));meter.setAttribute('aria-valuetext', `${full(c.used)} / ${full(c.max)} token`); }
        else meter.setAttribute('aria-valuetext', '当前上下文用量未知');
        const used = document.createElement('div');used.className = 'used';used.style.width = `${c ? Math.min(100, ratio * 100) : 0}%`;meter.append(used);body.append(meter);
        line('已用上下文', c ? tok(c.used) : '—', '', 'occupied');
        line('剩余可用', c ? tok(Math.max(0, c.max - c.used)) : '—', '', 'remaining');
        line('上下文上限', c ? tok(c.max) : '—');
        note = c ? (ratio > 1 ? '已超出上下文上限。' : '') + '原生总量 · 分项 token 暂不可用' : '当前会话的原生上下文读数不可用。';
      }
      if (state.kind !== 'context') {
        if (state.dataStatus !== 'ready') note = { waiting: '正在同步当前会话…', stale: '统计暂未更新，已隐藏过期数值。', unavailable: '当前会话的本地统计不可用。' }[state.dataStatus];
        else if (partial.length) note = '* 部分样本：' + partial.join(' · ');
      }
      footnote.textContent = note;footnote.hidden = !note;
      if (!panel.hidden) state.position();
    }
    state.detail = detail;
    state.position = () => {
      const r = state.trigger.getBoundingClientRect();
      panel.style.left = `${Math.max(12, Math.min(r.left, innerWidth - panel.offsetWidth - 12))}px`;
      panel.style.top = `${Math.max(12, r.top - panel.offsetHeight - 8)}px`;
    };
    for (const button of shadow.querySelectorAll('.row button')) button.addEventListener('click', () => {
      if (!panel.hidden && state.trigger === button) { state.close(); return; }
      closeAll();state.trigger = button;state.kind = button.className;detail();panel.hidden = false;
      // Top-layer positioning escapes the composer's transform and overflow:hidden ancestors.
      panel.showPopover();
      button.setAttribute('aria-expanded', 'true');
      state.position();
      shadow.querySelector('.close').focus();
    });
    shadow.querySelector('.close').addEventListener('click', () => { state.close();state.trigger?.focus(); });
    shadow.addEventListener('keydown', e => {
      if (e.key === 'Escape' && !panel.hidden) {
        e.preventDefault();e.stopPropagation();state.close();state.trigger?.focus();
      }
    });
    return state;
  }
  function paint(s) {
    s.context = nativeUsage(s.pane);
    const d = packet.sessions[s.sid];
    const stale = Date.now() - packet.at > 10000;
    const valid = d && !d.error && !packet.error && !stale;
    s.data = valid ? d : null;
    s.dataStatus = !packet.at ? 'waiting' : packet.error || d?.error ? 'unavailable' : stale ? 'stale' : d ? 'ready' : 'waiting';
    const q = sel => s.shadow.querySelector(sel);
    q('.counts').textContent = valid ? `${d.turns} 轮 ${d.steps} 步` : '待同步';
    q('.speed').textContent = valid ? speed(d.tps) + (d.speedSamples < d.steps && d.tps !== null ? '*' : '') : '— tok/s';
    q('.total').textContent = valid ? `${compact(d.tokens)} tok${d.tokenSamples < d.steps ? '*' : ''}` : '— tok';
    q('.cache').textContent = valid && d.cacheHit !== null ? `· 缓存命中 ${percent(d.cacheHit)}${d.cacheSamples < d.steps ? '*' : ''}` : '';
    q('.pressure').textContent = s.context ? percent(s.context.used / s.context.max) : '—';
    const arc = s.context ? Math.max(0, Math.min(1, s.context.used / s.context.max)) * 56.55 : 0;
    q('.arc').setAttribute('stroke-dasharray', `${arc} 56.55`);
    q('.context').setAttribute('aria-label', `上下文占用 ${q('.pressure').textContent}`);
    s.host.toggleAttribute('data-narrow', s.anchor.getBoundingClientRect().width < 510);
    const dark = document.documentElement.classList.contains('dark') || document.documentElement.dataset.theme === 'dark';
    s.host.toggleAttribute('data-dark', dark);
    if (!q('.details').hidden) s.detail();
  }
  function scan() {
    if (dead) return;
    const seen = new Set();
    const layouts = new Set(document.querySelectorAll('[data-composer-layout]'));
    // Official 3.14.4 has the same card structure, before the explicit layout marker.
    for (const editor of document.querySelectorAll('.chat-composer-input-surface [data-testid="v4-composer-input"][data-lexical-editor="true"]')) {
      const form = editor.closest('form');
      const card = form?.querySelector(':scope > .border-input-border');
      if (card?.contains(editor) && !card.hasAttribute('data-composer-layout')) layouts.add(card);
    }
    for (const layout of layouts) {
      if (layout.dataset.composerLayout === 'inline' || !visible(layout)) continue;
      const form = layout.closest('form');
      // Highspeed/context-header modes put the visible card on this outer surface.
      const anchor = layout.closest('.chat-composer-input-surface') || layout;
      const pane = layout.closest('[data-session-id]');
      const sid = pane?.dataset.sessionId;
      if (!form || !sid || sid === 'draft' || seen.has(form)) continue;
      seen.add(form);
      let s = roots.get(form);
      if (s && (s.sid !== sid || s.layout !== layout || s.anchor !== anchor || s.pane !== pane || !s.host.isConnected)) {
        s.close();s.host.remove();roots.delete(form);s = null;
      }
      if (!s) { s = create(form, layout, anchor, pane, sid);roots.set(form, s); }
      if (anchor.nextElementSibling !== s.host) anchor.after(s.host);
      paint(s);
    }
    for (const [form, s] of roots) if (!seen.has(form)) { s.close();s.host.remove();roots.delete(form); }
  }
  const outside = e => { for (const s of roots.values()) if (!e.composedPath().includes(s.host)) s.close(); };
  const closeAll = () => { for (const s of roots.values()) s.close(); };
  document.addEventListener('pointerdown', outside, true);
  window.addEventListener('scroll', closeAll, true);
  window.addEventListener('resize', closeAll);
  const timer = setInterval(scan, 500);
  window.__dshStats = {
    wanted: () => [...new Set([...roots.values()].map(s => s.sid))],
    receive: data => { packet = data;scan(); },
    dispose: () => { dead = true;clearInterval(timer);closeAll();for (const s of roots.values()) s.host.remove();roots.clear();dockStyle.remove();document.removeEventListener('pointerdown', outside, true);window.removeEventListener('scroll', closeAll, true);window.removeEventListener('resize', closeAll); }
  };
  scan();
})();
