/* いちカズ ダッシュボード */
(function () {
  const $ = (id) => document.getElementById(id);

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
  function fmtDate(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    if (isNaN(d)) return '—';
    return d.toLocaleString('ja-JP', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
  }

  function renderActions(plan) {
    const slot = $('dash-actions');
    if (plan === 'pro') {
      slot.innerHTML = '<button class="btn-ghost" onclick="IK.openPortal()">サブスク管理・解約</button>'
        + '<a class="btn-nav" href="/">＋ 新規短縮</a>';
    } else {
      slot.innerHTML = '<button class="btn-nav" onclick="IK.upgrade()">Pro にアップグレード</button>'
        + '<a class="btn-ghost" href="/">＋ 新規短縮</a>';
    }
  }

  function renderApiKey(me) {
    const slot = $('api-key-slot');
    if (me.plan === 'pro' && me.api_key) {
      slot.innerHTML = '<div class="api-key-box"><strong>APIキー</strong>'
        + '<span style="font-size:.82rem;color:var(--text-muted)"> — <code style="display:inline;padding:2px 6px">POST /api/v1/shorten</code> に <code style="display:inline;padding:2px 6px">X-API-Key</code> ヘッダで</span>'
        + '<code>' + esc(me.api_key) + '</code></div>';
    } else {
      slot.innerHTML = '';
    }
  }

  function linkItem(l, plan) {
    const expired = l.expires_at && new Date(l.expires_at) < new Date();
    const proBtns = plan === 'pro'
      ? '<button class="mini-btn" onclick="DASH.analytics(\'' + esc(l.code) + '\')">解析</button>'
        + '<button class="mini-btn" onclick="DASH.edit(\'' + esc(l.code) + '\')">編集</button>'
      : '';
    return '<div class="link-item">'
      + '<div class="link-top">'
      + '<a class="link-short" href="' + esc(l.short_url) + '" target="_blank" rel="noopener">' + esc(l.short_url) + '</a>'
      + '<span class="link-clicks"><b>' + l.click_count + '</b> クリック</span>'
      + '</div>'
      + (l.title ? '<div class="link-meta">' + esc(l.title) + '</div>' : '')
      + '<div class="link-orig">→ ' + esc(l.original_url) + '</div>'
      + '<div class="link-meta">作成 ' + fmtDate(l.created_at)
      + (l.expires_at ? ' ｜ 期限 ' + fmtDate(l.expires_at) + (expired ? '（期限切れ）' : '') : '')
      + (l.is_custom ? ' ｜ カスタム' : '') + '</div>'
      + '<div class="link-buttons">'
      + '<button class="mini-btn" onclick="DASH.copy(\'' + esc(l.short_url) + '\')">コピー</button>'
      + (plan === 'pro' ? '<button class="mini-btn" onclick="DASH.qr(\'' + esc(l.code) + '\')">QR</button>' : '')
      + '<a class="mini-btn" href="/stats/' + esc(l.code) + '" target="_blank">統計</a>'
      + proBtns
      + '<button class="mini-btn danger" onclick="DASH.del(\'' + esc(l.code) + '\')">削除</button>'
      + '</div></div>';
  }

  let currentPlan = 'free';

  async function load() {
    const r = await IK.api('/api/links');
    if (r.status === 401) { location.href = '/'; return; }
    currentPlan = r.data.plan || 'free';
    renderActions(currentPlan);
    const me = IK.user || {};
    renderApiKey(me);
    const list = $('link-list');
    const links = (r.data.links || []);
    if (!links.length) {
      list.innerHTML = '<div class="empty-state">まだリンクがありません。<br><a href="/" style="color:var(--brand);font-weight:700">トップで短縮する →</a></div>';
      return;
    }
    list.innerHTML = links.map((l) => linkItem(l, currentPlan)).join('');
  }

  function showAlert(msg, type) {
    $('alert-slot').innerHTML = '<div class="alert ' + (type || 'success') + '">' + esc(msg) + '</div>';
    setTimeout(() => { $('alert-slot').innerHTML = ''; }, 5000);
  }

  window.DASH = {
    async copy(url) {
      try { await navigator.clipboard.writeText(url); showAlert('コピーしました', 'success'); }
      catch { showAlert(url, 'success'); }
    },
    qr(code) {
      $('qr-slot').innerHTML = '<img src="/qr/' + encodeURIComponent(code) + '" alt="QR" style="width:200px;height:200px" />';
      $('qr-url').textContent = 'https://1qaz.jp/' + code;
      $('qr-modal').hidden = false;
    },
    async analytics(code) {
      const r = await IK.api('/api/links/' + encodeURIComponent(code) + '/logs');
      if (!r.ok) { showAlert(r.data.detail || '取得失敗', 'error'); return; }
      const logs = r.data.logs || [];
      const lines = logs.slice(0, 30).map((g) =>
        fmtDate(g.accessed_at) + '  ' + (g.ip_address || '') + '  ' + (g.referer || 'direct')).join('\n');
      alert('「' + code + '」 合計 ' + r.data.click_count + ' クリック\n\n直近のアクセス:\n' + (lines || 'まだありません'));
    },
    async edit(code) {
      const url = prompt('新しいリンク先URL（空欄で変更なし）');
      if (url === null) return;
      const days = prompt('有効期限（日数）。0または空欄で無期限', '');
      if (days === null) return;
      const body = {};
      if (url.trim()) body.original_url = url.trim();
      body.expires_days = days.trim() ? parseInt(days, 10) : 0;
      const r = await IK.api('/api/links/' + encodeURIComponent(code), { method: 'PATCH', body: JSON.stringify(body) });
      if (!r.ok) { showAlert(r.data.detail || '更新失敗', 'error'); return; }
      showAlert('更新しました', 'success'); load();
    },
    async del(code) {
      if (!confirm('このリンクを削除しますか？\n1qaz.jp/' + code)) return;
      const r = await IK.api('/api/links/' + encodeURIComponent(code), { method: 'DELETE' });
      if (!r.ok) { showAlert(r.data.detail || '削除失敗', 'error'); return; }
      showAlert('削除しました', 'success'); load();
    },
  };

  document.addEventListener('DOMContentLoaded', async () => {
    if (!IK.token) { location.href = '/'; return; }
    // 決済リダイレクト処理
    const upg = new URLSearchParams(location.search).get('upgrade');
    if (upg === 'success') {
      showAlert('Proへのアップグレードありがとうございます！反映を確認しています…', 'success');
      history.replaceState(null, '', '/dashboard');
      await IK.refreshMe();
      setTimeout(() => IK.refreshMe(), 2500);
    } else if (upg === 'cancel') {
      history.replaceState(null, '', '/dashboard');
    } else {
      await IK.refreshMe();
    }
    load();
  });
})();
