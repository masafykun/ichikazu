(function () {
  const form      = document.getElementById('shorten-form');
  const input     = document.getElementById('url-input');
  const submitBtn = document.getElementById('submit-btn');
  const btnLabel  = submitBtn.querySelector('.btn-label');
  const btnLoad   = submitBtn.querySelector('.btn-loading');
  const resultDiv = document.getElementById('result');
  const resultLink = document.getElementById('result-link');
  const statsLink  = document.getElementById('stats-link');
  const copyBtn   = document.getElementById('copy-btn');
  const copyMsg   = document.getElementById('copy-msg');
  const errorMsg  = document.getElementById('error-msg');

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const url = input.value.trim();
    if (!url) return;

    setLoading(true);
    errorMsg.hidden = true;
    resultDiv.hidden = true;
    copyMsg.hidden = true;

    try {
      const res = await fetch('/api/shorten', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        showError(data.detail || '短縮URLの作成に失敗しました。');
        return;
      }

      const data = await res.json();
      resultLink.href = data.short_url;
      resultLink.textContent = data.short_url;
      statsLink.href = `/stats/${data.code}`;
      resultDiv.hidden = false;
    } catch {
      showError('通信エラーが発生しました。再度お試しください。');
    } finally {
      setLoading(false);
    }
  });

  copyBtn.addEventListener('click', async () => {
    const text = resultLink.href;
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
    copyMsg.hidden = false;
    setTimeout(() => { copyMsg.hidden = true; }, 2000);
  });

  function setLoading(on) {
    submitBtn.disabled = on;
    btnLabel.hidden = on;
    btnLoad.hidden = !on;
  }

  function showError(msg) {
    errorMsg.textContent = msg;
    errorMsg.hidden = false;
  }
})();
