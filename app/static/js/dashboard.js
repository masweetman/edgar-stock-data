(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // Table sorting
  // ---------------------------------------------------------------------------
  let sortCol = -1;
  let sortAsc = true;

  function cellSortKey(cell, colIndex) {
    // For col 0 (Ticker): plain text, locale sort
    if (colIndex === 0) {
      return cell.textContent.trim().toLowerCase();
    }
    // For all other columns: extract the first numeric token from the cell text.
    // Badge cells (Quality, MOS) contain a leading number or the word "—".
    const text = cell.textContent.trim();
    if (text === '—' || text === '') return Infinity;
    // Strip leading $, trailing %, words like "Strong Buy" / "Buy" / "Hold" / "Overvalued"
    const numeric = parseFloat(text.replace(/[^0-9.\-]/g, ''));
    return isNaN(numeric) ? Infinity : numeric;
  }

  function sortTable(colIndex, ascending) {
    const tbody = document.getElementById('data-tbody');
    if (!tbody) return;
    const rows = Array.from(tbody.querySelectorAll('tr'));

    rows.sort(function (a, b) {
      const ka = cellSortKey(a.cells[colIndex], colIndex);
      const kb = cellSortKey(b.cells[colIndex], colIndex);
      // Always push Infinity (—) to the bottom regardless of direction
      if (ka === Infinity && kb === Infinity) return 0;
      if (ka === Infinity) return 1;
      if (kb === Infinity) return -1;
      if (typeof ka === 'string') {
        return ascending ? ka.localeCompare(kb) : kb.localeCompare(ka);
      }
      return ascending ? ka - kb : kb - ka;
    });

    rows.forEach(function (row) { tbody.appendChild(row); });
  }

  function updateArrows(activeColIndex, ascending) {
    document.querySelectorAll('th.sortable').forEach(function (th) {
      const arrow = th.querySelector('.sort-arrow');
      if (!arrow) return;
      const col = parseInt(th.dataset.col, 10);
      arrow.textContent = col === activeColIndex ? (ascending ? ' ▲' : ' ▼') : '';
    });
  }

  function attachSortHandlers() {
    document.querySelectorAll('th.sortable').forEach(function (th) {
      th.addEventListener('click', function () {
        const col = parseInt(th.dataset.col, 10);
        if (col === sortCol) {
          sortAsc = !sortAsc;
        } else {
          sortCol = col;
          sortAsc = true;
        }
        sortTable(sortCol, sortAsc);
        updateArrows(sortCol, sortAsc);
      });
    });
  }

  attachSortHandlers();

  // ---------------------------------------------------------------------------
  // Fetch button
  // ---------------------------------------------------------------------------
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
          const companyUrl = '/company/' + encodeURIComponent(e.ticker);
          row.innerHTML = [
            '<td><strong><a href="' + companyUrl + '">' + e.ticker + '</a></strong></td>',
            '<td>\u2014</td>',
            '<td>' + (e.eps_avg != null ? e.eps_avg.toFixed(2) : '\u2014') + '</td>',
            '<td>' + (e.bvps != null ? e.bvps.toFixed(2) : '\u2014') + '</td>',
            '<td>' + (e.div != null ? e.div.toFixed(4) : '\u2014') + '</td>',
            '<td>\u2014</td>',
            '<td>\u2014</td>',
            '<td>\u2014</td>',
            '<td>' + (e.quality_score != null ? e.quality_score : '\u2014') + '</td>',
            '<td>\u2014</td>',
          ].join('');
          tbody.appendChild(row);
        });

        // Re-apply active sort to freshly inserted rows
        if (sortCol >= 0) {
          sortTable(sortCol, sortAsc);
          updateArrows(sortCol, sortAsc);
        }

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
