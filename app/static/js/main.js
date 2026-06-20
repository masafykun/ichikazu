/* いちカズ 共通フロント（セッション・認証・ナビ・短縮・アップグレード） */
window.IK = (function () {
  const $ = (id) => document.getElementById(id);
  let token = localStorage.getItem('ik_token') || '';
  let user = JSON.parse(localStorage.getItem('ik_user') || 'null');
  let authMode = 'login';
  let pendingUpgrade = false;

  function saveSession(t, u) {
    token = t; user = u;
    localStorage.setItem('ik_token', t);
    localStorage.setItem('ik_user', JSON.stringify(u));
    updateNav();
  }
  function logout() {
    token = ''; user = null;
    localStorage.removeItem('ik_token');
    localStorage.removeItem('ik_user');
    if (location.pathname === '/dashboard') location.href = '/';
    else updateNav();
  }
  function isPro() { return user && user.plan === 'pro'; }

  function updateNav() {
    const guest = $('nav-guest'), nu = $('nav-user');
    if (!guest || !nu) return;
    if (token && user) {
      guest.hidden = true; nu.hidden = false;
      const badge = $('nav-plan');
      if (badge) {
        badge.textContent = isPro() ? 'Pro' : 'Free';
        badge.className = 'plan-badge' + (isPro() ? ' pro' : '');
      }
    } else {
      guest.hidden = false; nu.hidden = true;
    }
  }

  async function api(path, opts = {}) {
    opts.headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
    if (token) opts.headers['Authorization'] = 'Bearer ' + token;
    const res = await fetch(path, opts);
    let data = {};
    try { data = await res.json(); } catch (e) {}
    return { ok: res.ok, status: res.status, data };
  }

  async function refreshMe() {
    if (!token) return;
    const r = await api('/api/auth/me');
    if (r.ok) { user = r.data; localStorage.setItem('ik_user', JSON.stringify(user)); updateNav(); }
    else if (r.status === 401) { logout(); }
  }

  /* ── 認証モーダル ── */
  function openAuth(mode) {
    authMode = mode;
    const modal = $('auth-modal');
    if (!modal) { location.href = '/'; return; }
    $('auth-title').textContent = mode === 'register' ? 'アカウント登録' : 'ログイン';
    $('auth-submit').textContent = mode === 'register' ? '登録する' : 'ログイン';
    $('auth-switch').innerHTML = mode === 'register'
      ? 'すでにアカウントをお持ちですか？ <a onclick="IK.openAuth(\'login\')">ログイン</a>'
      : 'アカウントがない方は <a onclick="IK.openAuth(\'register\')">無料登録</a>';
    const err = $('auth-error'); if (err) err.hidden = true;
    modal.hidden = false;
  }
  function closeAuth() { const m = $('auth-modal'); if (m) m.hidden = true; }
  function authError(msg) { const e = $('auth-error'); if (e) { e.textContent = msg; e.hidden = false; } }

  async function submitAuth() {
    const email = ($('auth-email').value || '').trim();
    const password = $('auth-password').value || '';
    if (!email || !password) return authError('メールアドレスとパスワードを入力してください');
    const btn = $('auth-submit'); btn.disabled = true;
    try {
      const r = await api('/api/auth/' + (authMode === 'register' ? 'register' : 'login'), {
        method: 'POST', body: JSON.stringify({ email, password }),
      });
      if (!r.ok) { authError(r.data.detail || '失敗しました'); return; }
      saveSession(r.data.token, r.data.user);
      closeAuth();
      if (pendingUpgrade) { pendingUpgrade = false; upgrade(); }
      else if (location.pathname === '/dashboard') location.reload();
    } catch (e) { authError('通信エラーが発生しました'); }
    finally { btn.disabled = false; }
  }

  /* ── アップグレード（Checkout） ── */
  async function upgrade() {
    if (!token) { pendingUpgrade = true; return openAuth('register'); }
    if (isPro()) { location.href = '/dashboard'; return; }
    const r = await api('/api/billing/checkout', { method: 'POST' });
    if (r.ok && r.data.url) { location.href = r.data.url; }
    else { alert(r.data.detail || '決済ページを開けませんでした'); }
  }

  async function openPortal() {
    const r = await api('/api/billing/portal', { method: 'POST' });
    if (r.ok && r.data.url) location.href = r.data.url;
    else alert(r.data.detail || 'ポータルを開けませんでした');
  }

  /* ── Pro オプション開閉 ── */
  function toggleOptions() {
    const opts = $('pro-options'), upsell = $('pro-upsell');
    if (!opts) return;
    const show = opts.hidden;
    opts.hidden = !show;
    if (show && !isPro()) {
      opts.classList.add('locked');
      if (upsell) upsell.hidden = false;
    } else {
      opts.classList.remove('locked');
      if (upsell) upsell.hidden = true;
    }
  }

  /* ── 短縮フォーム（indexのみ） ── */
  function initShortenForm() {
    const form = $('shorten-form');
    if (!form) return;
    const input = $('url-input');
    const submitBtn = $('submit-btn');
    const btnLabel = submitBtn.querySelector('.btn-label');
    const btnLoad = submitBtn.querySelector('.btn-loading');
    const resultDiv = $('result');
    const resultLink = $('result-link');
    const statsLink = $('stats-link');
    const copyBtn = $('copy-btn');
    const copyMsg = $('copy-msg');
    const errorMsg = $('error-msg');

    const setLoading = (on) => { submitBtn.disabled = on; btnLabel.hidden = on; btnLoad.hidden = !on; };
    const showError = (m) => { errorMsg.textContent = m; errorMsg.hidden = false; };

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const url = input.value.trim();
      if (!url) return;
      setLoading(true); errorMsg.hidden = true; resultDiv.hidden = true; copyMsg.hidden = true;

      const body = { url };
      if (isPro()) {
        const slug = ($('slug-input') && $('slug-input').value || '').trim();
        const exp = ($('expires-input') && $('expires-input').value || '').trim();
        if (slug) body.slug = slug;
        if (exp) body.expires_days = parseInt(exp, 10);
      }
      try {
        const r = await api('/api/shorten', { method: 'POST', body: JSON.stringify(body) });
        if (!r.ok) { showError(r.data.detail || '短縮URLの作成に失敗しました。'); return; }
        resultLink.href = r.data.short_url;
        resultLink.textContent = r.data.short_url;
        statsLink.href = '/stats/' + r.data.code;
        resultDiv.hidden = false;
      } catch (e) { showError('通信エラーが発生しました。再度お試しください。'); }
      finally { setLoading(false); }
    });

    copyBtn.addEventListener('click', async () => {
      const text = resultLink.href;
      try { await navigator.clipboard.writeText(text); }
      catch {
        const ta = document.createElement('textarea'); ta.value = text;
        document.body.appendChild(ta); ta.select(); document.execCommand('copy');
        document.body.removeChild(ta);
      }
      copyMsg.hidden = false;
      setTimeout(() => { copyMsg.hidden = true; }, 2000);
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    updateNav();
    initShortenForm();
    if (token) refreshMe();
  });

  return { openAuth, closeAuth, submitAuth, logout, upgrade, openPortal, toggleOptions, refreshMe, updateNav,
           api, isPro, get token() { return token; }, get user() { return user; } };
})();
