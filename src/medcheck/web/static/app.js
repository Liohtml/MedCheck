// MedCheck UI logic. Kept in a separate file (no inline scripts/handlers) so the
// Content-Security-Policy can exclude 'unsafe-inline' from script-src.
(function () {
  'use strict';

  // Tab switching
  function showTab(n) {
    document.querySelectorAll('.tab-pane').forEach(function (p) {
      p.classList.remove('active');
    });
    document.querySelectorAll('.tab-btn').forEach(function (b) {
      b.classList.remove('active');
    });
    document.getElementById('pane-' + n).classList.add('active');
    var tabs = document.querySelectorAll('.tab-btn');
    if (tabs[n - 1]) tabs[n - 1].classList.add('active');
  }

  // File dropzone - use textContent for safe DOM updates
  function fileSelected(input) {
    if (input.files && input.files[0]) {
      var f = input.files[0];
      var subtext = document.getElementById('dropzoneSubtext');
      var sizeMB = (f.size / 1024 / 1024).toFixed(2);
      subtext.textContent = f.name + ' (' + sizeMB + ' MB)';
      document.getElementById('autoDetectBadge').style.display = 'inline-flex';
    }
  }

  function simulateProgress() {
    var fill = document.getElementById('progressFill');
    var label = document.getElementById('progressLabel');
    var steps = [
      [10, 'Uploading data...'],
      [30, 'Preprocessing imaging data...'],
      [55, 'Running ML modules...'],
      [75, 'Querying AI model...'],
      [90, 'Generating report...'],
      [100, 'Done!']
    ];
    var i = 0;
    var tick = setInterval(function () {
      if (i >= steps.length) { clearInterval(tick); return; }
      fill.style.width = steps[i][0] + '%';
      label.textContent = steps[i][1];
      i++;
    }, 800);
  }

  document.addEventListener('DOMContentLoaded', function () {
    // Any element with data-goto="N" switches to wizard step N.
    document.querySelectorAll('[data-goto]').forEach(function (el) {
      el.addEventListener('click', function () {
        showTab(parseInt(el.getAttribute('data-goto'), 10));
      });
    });

    var dropzone = document.getElementById('dropzone');
    var fileInput = document.getElementById('fileInput');
    if (dropzone && fileInput) {
      dropzone.addEventListener('click', function () { fileInput.click(); });
      dropzone.addEventListener('dragover', function (e) {
        e.preventDefault();
        dropzone.classList.add('dragover');
      });
      dropzone.addEventListener('dragleave', function () {
        dropzone.classList.remove('dragover');
      });
      dropzone.addEventListener('drop', function (e) {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        var dt = e.dataTransfer;
        if (dt && dt.files && dt.files[0]) {
          fileInput.files = dt.files;
          fileSelected(fileInput);
        }
      });
      fileInput.addEventListener('change', function () { fileSelected(fileInput); });
    }

    var form = document.getElementById('analyzeForm');
    if (form) {
      form.addEventListener('submit', function () { simulateProgress(); });
    }
  });
})();
