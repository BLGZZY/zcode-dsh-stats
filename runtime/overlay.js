/* DSH-style compact statistics; no credentials, model calls or native React state access. */
(() => {
  'use strict';
  window.__dshStats?.dispose();
  const roots = new Map();
  // Only compact the native 16px dock gutter while our row is actually mounted.
  // A scoped rule preserves React's styles and restores native spacing on cleanup/drafts.
  const dockStyle = document.createElement('style');
  dockStyle.dataset.dshStatsLayout = '0.2.2';
  dockStyle.textContent = '[data-v4-composer-dock-content].pb-4:has([data-dsh-stats]){padding-bottom:2px!important}';
  document.head.appendChild(dockStyle);
  let packet = { sessions: {}, at: 0 }, dead = false;
  const css = `
    :host{display:block;color:var(--color-foreground-subtle,#626773);font:12px/20px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color-scheme:light dark;min-width:0;width:100%;margin-top:3px;flex:none}
    *{box-sizing:border-box}.row{display:flex;justify-content:center;align-items:center;gap:8px;flex-wrap:nowrap;min-width:0;height:24px;padding:0;font-variant-numeric:tabular-nums}
    button{font:inherit;color:inherit;border:0;background:transparent;border-radius:6px;padding:2px 4px;display:inline-flex;align-items:center;gap:6px;cursor:pointer;white-space:nowrap;min-height:24px;flex:none}
    button:hover,button[aria-expanded=true]{background:var(--color-surface-hover,rgba(128,128,128,.12));color:var(--color-foreground,#252831)}
    button:focus-visible{outline:2px solid #6b85bd;outline-offset:1px}svg{width:14px;height:14px;flex:none}.muted{opacity:.65}.short{display:none}
    .details{position:fixed;inset:auto;margin:0;z-index:2147483000;width:300px;max-width:calc(100vw - 24px);max-height:calc(100vh - 24px);overflow:auto;overscroll-behavior:contain;background:var(--color-background,#fff);color:var(--color-foreground,#252831);border:1px solid var(--color-border,rgba(128,128,128,.25));border-radius:12px;box-shadow:0 12px 35px #0002;padding:15px;font:12px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
    .details[hidden]{display:none}.title{font-weight:600;margin-bottom:9px;font-size:13px}.line{display:flex;justify-content:space-between;gap:12px;padding:3px 0}.note{opacity:.7;border-top:1px solid #8883;padding-top:9px;margin-top:8px;white-space:normal}.close{float:right;margin:-5px -6px 0 0}
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
    host.dataset.dshStats = '0.2.2';
    const shadow = host.attachShadow({ mode: 'open' });
    shadow.innerHTML = `<style>${css}</style><div class="row" role="group" aria-label="会话用量统计">
      <button type="button" class="activity" aria-haspopup="dialog" aria-expanded="false">${icon('activity')}<span class="counts extra"></span><span class="muted extra">·</span><span class="speed"></span></button>
      <button type="button" class="usage" aria-haspopup="dialog" aria-expanded="false">${icon('database')}<span class="total"></span><span class="cache extra"></span></button>
      <button type="button" class="context" aria-haspopup="dialog" aria-expanded="false">${icon('ring')}<span class="pressure"></span></button></div>
      <div class="details" popover="manual" role="dialog" aria-label="会话统计详情" hidden><button type="button" class="close" aria-label="关闭详情">×</button><div class="title">会话统计</div><div class="body"></div><div class="note"></div></div>`;
    // Keep telemetry outside the bordered input card so it never increases the editor's height.
    anchor.after(host);
    const state = { host, shadow, form, layout, anchor, pane, sid, data: null, dataStatus: 'waiting', context: null, trigger: null };
    const panel = shadow.querySelector('.details');
    state.close = () => {
      if (panel.matches(':popover-open')) panel.hidePopover();
      panel.hidden = true;
      shadow.querySelectorAll('[aria-expanded]').forEach(b => b.setAttribute('aria-expanded', 'false'));
    };
    function detail() {
      const d = state.data;
      const rows = [
        ['已完成轮数 / 请求数', d && !d.error ? `${d.turns} / ${d.steps}` : '—'],
        ['会话解码均速', speed(d?.tps)],
        ['速度有效样本', d && !d.error ? `${d.speedSamples} / ${d.steps}` : '—'],
        ['保留记录累计 token', full(d?.tokens)],
        ['缓存命中', percent(d?.cacheHit)],
        ['上下文', state.context ? `${full(state.context.used)} / ${full(state.context.max)}` : '原生读数不可用']
      ];
      const body = shadow.querySelector('.body'); body.replaceChildren();
      for (const [label, value] of rows) {
        const row = document.createElement('div');row.className = 'line';
        const a = document.createElement('span'), b = document.createElement('span');
        a.textContent = label; b.textContent = value; row.append(a, b);body.append(row);
      }
      const notes = {
        waiting: '正在等待当前会话的用量统计。上下文来自客户端当前读数。',
        stale: '用量统计超过 10 秒未更新，已暂时隐藏旧数字；恢复连接后自动刷新。上下文来自客户端当前读数。',
        unavailable: '当前会话数据不可用。远程会话不读取其他本地会话充数。',
        ready: '仅统计本地保留记录中的已完成主请求（ZCode 通常保留近 30 天）。速度 = Σ输出 token ÷ Σ(完成 − 首 token)，每次请求结束后刷新；不是流式瞬时速度。缺少计时的请求不参与均速。首 token 是首个文本/思考片段；仅工具参数的请求可能缺计时。思考计时取决于提供方；输入已含缓存，不重复相加。带 * 为部分样本。'
      };
      shadow.querySelector('.note').textContent = notes[state.dataStatus];
    }
    state.detail = detail;
    for (const button of shadow.querySelectorAll('.row button')) button.addEventListener('click', () => {
      if (!panel.hidden && state.trigger === button) { state.close(); return; }
      state.close();state.trigger = button;detail();panel.hidden = false;
      // Top-layer positioning escapes the composer's transform and overflow:hidden ancestors.
      panel.showPopover();
      button.setAttribute('aria-expanded', 'true');
      const r = host.getBoundingClientRect();
      panel.style.left = `${Math.max(12, Math.min(r.left, innerWidth - panel.offsetWidth - 12))}px`;
      panel.style.top = `${Math.max(12, r.top - panel.offsetHeight - 8)}px`;
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
    for (const layout of document.querySelectorAll('[data-composer-layout]')) {
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
