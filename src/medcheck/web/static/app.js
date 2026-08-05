// MedCheck UI logic. Kept in a separate file (no inline scripts/handlers) so the
// Content-Security-Policy can exclude 'unsafe-inline' from script-src.
(function () {
  'use strict';

  var CLOUD_MODELS = ['claude', 'openai', 'gemini'];

  // Wizard step switching (stepper buttons + prev/next buttons use data-goto)
  function showStep(n) {
    document.querySelectorAll('.tab-pane').forEach(function (p) {
      p.classList.remove('active');
    });
    var pane = document.getElementById('pane-' + n);
    if (pane) pane.classList.add('active');

    document.querySelectorAll('.pdp-stepper-step').forEach(function (s) {
      var step = parseInt(s.getAttribute('data-step'), 10);
      s.classList.toggle('active', step === n);
      s.classList.toggle('completed', step < n);
      if (step === n) {
        s.setAttribute('aria-current', 'step');
      } else {
        s.removeAttribute('aria-current');
      }
    });
  }

  // File dropzone - use textContent for safe DOM updates
  function fileSelected(input) {
    if (input.files && input.files[0]) {
      var f = input.files[0];
      var subtext = document.getElementById('dropzoneSubtext');
      var sizeMB = (f.size / 1024 / 1024).toFixed(2);
      subtext.textContent = f.name + ' (' + sizeMB + ' MB)';
      var badge = document.getElementById('autoDetectBadge');
      if (badge) badge.classList.add('is-visible');
    }
  }

  function isCloudModel() {
    var select = document.getElementById('modelSelect');
    return !!select && CLOUD_MODELS.indexOf(select.value) !== -1;
  }

  function syncConsentVisibility() {
    var block = document.getElementById('consentBlock');
    if (block) block.classList.toggle('is-visible', isCloudModel());
  }

  // Replace the results area content with a kit alert (text set via textContent,
  // never innerHTML — the server response echoes user input).
  function showResultAlert(kind, text) {
    var results = document.getElementById('resultsContent');
    if (!results) return;
    results.textContent = '';
    results.classList.remove('results-empty');
    var alert = document.createElement('div');
    alert.className = 'alert alert-' + kind;
    alert.setAttribute('role', 'alert');
    var body = document.createElement('p');
    body.textContent = text;
    alert.appendChild(body);
    results.appendChild(alert);
    alert.style.marginBottom = '1.5rem';
  }

  function setProgress(percent, labelText) {
    var fill = document.getElementById('progressFill');
    var label = document.getElementById('progressLabel');
    if (fill) fill.style.width = percent + '%';
    if (label && labelText) label.textContent = labelText;
  }

  function submitAnalysis(form) {
    var startBtn = document.getElementById('startBtn');
    var consent = document.getElementById('consentCheck');
    var cloud = isCloudModel();

    if (cloud && (!consent || !consent.checked)) {
      showResultAlert('danger', form.getAttribute('data-msg-consent'));
      showStep(3);
      if (consent) consent.focus();
      return;
    }

    var urlInput = document.getElementById('sourceUrl');
    var fileInput = document.getElementById('fileInput');
    var source = (urlInput && urlInput.value.trim()) ||
      (fileInput && fileInput.files && fileInput.files[0] && fileInput.files[0].name) ||
      'browser-upload';

    var anatomy = document.getElementById('anatomy');
    var language = document.getElementById('reportLanguage');
    var format = document.getElementById('reportFormat');

    var body = {
      source: source,
      report_format: format ? format.value : 'json',
      language: language ? language.value : 'en',
      allow_cloud_llm: !!(cloud && consent && consent.checked)
    };
    if (anatomy && anatomy.value) body.anatomy = anatomy.value;

    if (startBtn) startBtn.disabled = true;
    setProgress(30, form.getAttribute('data-msg-sending'));

    fetch(form.getAttribute('action'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })
      .then(function (resp) {
        return resp.json().then(function (data) {
          return { ok: resp.ok, status: resp.status, data: data };
        });
      })
      .then(function (result) {
        var detail = result.data && result.data.detail;
        if (typeof detail !== 'string') detail = JSON.stringify(result.data);
        if (result.ok) {
          setProgress(100, '');
          showResultAlert('success', detail);
        } else {
          setProgress(0, form.getAttribute('data-msg-waiting'));
          // 501 = known preview limitation -> warning; anything else -> danger.
          showResultAlert(result.status === 501 ? 'warning' : 'danger', detail);
        }
      })
      .catch(function (err) {
        setProgress(0, form.getAttribute('data-msg-waiting'));
        showResultAlert('danger', String(err));
      })
      .then(function () {
        if (startBtn) startBtn.disabled = false;
      });
  }

  document.addEventListener('DOMContentLoaded', function () {
    // Sticky header — must NOT be sticky at page load; scroll adds the class.
    var siteHeader = document.getElementById('site-header');
    if (siteHeader) {
      var onScroll = function () {
        siteHeader.classList.toggle('is-sticky', window.scrollY > 0);
      };
      window.addEventListener('scroll', onScroll, { passive: true });
      onScroll();
    }

    // Any element with data-goto="N" switches to wizard step N.
    document.querySelectorAll('[data-goto]').forEach(function (el) {
      el.addEventListener('click', function () {
        showStep(parseInt(el.getAttribute('data-goto'), 10));
      });
    });

    var dropzone = document.getElementById('dropzone');
    var fileInput = document.getElementById('fileInput');
    if (dropzone && fileInput) {
      dropzone.addEventListener('click', function () { fileInput.click(); });
      dropzone.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          fileInput.click();
        }
      });
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

    var modelSelect = document.getElementById('modelSelect');
    if (modelSelect) {
      modelSelect.addEventListener('change', syncConsentVisibility);
      syncConsentVisibility();
    }

    var form = document.getElementById('analyzeForm');
    if (form) {
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        submitAnalysis(form);
      });
    }
  });
})();
