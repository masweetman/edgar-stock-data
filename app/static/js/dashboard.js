(function () {
  'use strict';

  const btn = document.getElementById('btn-fetch');
  if (!btn) return;

  const spinner = document.getElementById('fetch-spinner');
  const errBox = document.getElementById('fetch-error');
  const logViewer = document.getElementById('log-viewer');
  const logOutput = document.getElementById('log-output');
  const logClose = document.getElementById('log-close');
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const fetchUrl = btn.dataset.fetchUrl;

  logClose.addEventListener('click', function () {
    logViewer.style.display = 'none';
  });

  function appendLog(lines) {
    if (!lines || !lines.length) return;
    logViewer.style.display = 'block';
    logOutput.textContent += lines.join('\n') + '\n';
    logOutput.scrollTop = logOutput.scrollHeight;
  }

  btn.addEventListener('click', async function () {
    btn.disabled = true;
    spinner.style.display = 'inline-block';
    errBox.style.display = 'none';
    logViewer.style.display = 'block';
    logOutput.textContent = '\u23F3 Fetching from SEC EDGAR...\n';

    try {
      const res = await fetch(fetchUrl, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrfToken },
      });
      const data = await res.json();

      appendLog(data.logs || []);

      if (data.success) {
        logOutput.textContent += '\n\u2705 Fetch complete.\n';
        // Rebuild table rows with fresh data
        const tbody = document.getElementById('data-tbody');
        tbody.innerHTML = '';
        data.data.forEach(function (e) {
          const row = document.createElement('tr');
          row.dataset.ticker = e.ticker;
          row.innerHTML = [
            '<td><strong>' + e.ticker + '</strong></td>',
            '<td>' + (e.cik || '\u2014') + '</td>',
            '<td>' + (e.eps_avg != null ? e.eps_avg.toFixed(2) : '\u2014') + '</td>',
            '<td>' + (e.bvps != null ? e.bvps.toFixed(2) : '\u2014') + '</td>',
            '<td>' + (e.div != null ? e.div.toFixed(4) : '\u2014') + '</td>',
            '<td>' + (e.div_date || '\u2014') + '</td>',
            '<td class="text-muted small">' + (e.fetched_at ? e.fetched_at.substring(0, 16).replace('T', ' ') : '\u2014') + '</td>',
          ].join('');
          tbody.appendChild(row);
        });

        // Show table, hide no-data alert
        document.getElementById('data-table').style.display = '';
        const noDataAlert = document.getElementById('no-data-alert');
        if (noDataAlert) noDataAlert.style.display = 'none';
      } else {
        logOutput.textContent += '\n\u274C Error: ' + (data.error || 'Fetch failed.') + '\n';
        errBox.textContent = data.error || 'Fetch failed.';
        errBox.style.display = 'block';
      }
    } catch (err) {
      logOutput.textContent += '\n\u274C Network error: ' + err.message + '\n';
      errBox.textContent = 'Network error: ' + err.message;
      errBox.style.display = 'block';
    } finally {
      btn.disabled = false;
      spinner.style.display = 'none';
      logOutput.scrollTop = logOutput.scrollHeight;
    }
  });
})();
