(function () {
  'use strict';

  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content
    || document.querySelector('input[name="csrf_token"]')?.value || '';

  // --- Setup 2FA ---
  const btnSetup = document.getElementById('btn-setup-2fa');
  if (btnSetup) {
    btnSetup.addEventListener('click', async function () {
      btnSetup.disabled = true;
      const url = btnSetup.dataset.setupUrl;
      const res = await fetch(url, {
        headers: { 'X-CSRFToken': csrfToken },
      });
      const data = await res.json();
      if (data.success) {
        document.getElementById('qr-image').src = data.qr_image;
        document.getElementById('totp-secret').textContent = data.secret;
        document.getElementById('setup-2fa-section').style.display = 'block';
      } else {
        alert(data.error);
        btnSetup.disabled = false;
      }
    });
  }

  // --- Enable 2FA ---
  const btnEnable = document.getElementById('btn-enable-2fa');
  if (btnEnable) {
    btnEnable.addEventListener('click', async function () {
      const msg = document.getElementById('enable-2fa-msg');
      btnEnable.disabled = true;
      const url = btnEnable.dataset.enableUrl;
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({
          password: document.getElementById('enable-password').value,
          code: document.getElementById('enable-code').value,
        }),
      });
      const data = await res.json();
      if (data.success) {
        location.reload();
      } else {
        msg.innerHTML = '<span class="text-danger">' + data.error + '</span>';
        btnEnable.disabled = false;
      }
    });
  }

  // --- Disable 2FA ---
  const btnDisable = document.getElementById('btn-disable-2fa');
  if (btnDisable) {
    btnDisable.addEventListener('click', async function () {
      const msg = document.getElementById('disable-2fa-msg');
      btnDisable.disabled = true;
      const url = btnDisable.dataset.disableUrl;
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify({
          password: document.getElementById('disable-password').value,
          code: document.getElementById('disable-code').value,
        }),
      });
      const data = await res.json();
      if (data.success) {
        location.reload();
      } else {
        msg.innerHTML = '<span class="text-danger">' + data.error + '</span>';
        btnDisable.disabled = false;
      }
    });
  }
})();
