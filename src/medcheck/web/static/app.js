// Same-origin UI: only opaque job/upload references survive refresh in sessionStorage.
// Credentials and patient context are never persisted in browser storage.
(function () {
  "use strict";
  var source = null,
    studies = [],
    selectedStudy = "",
    jobId = null,
    result = null,
    busy = false,
    uploadVersion = 0;
  var currentStep = 1,
    previewVersion = 0,
    imageVersion = 0;
  var $ = function (id) {
    return document.getElementById(id);
  };
  function message(key) {
    return (
      $("uiStrings").getAttribute("data-ui-" + key.replace(/_/g, "-")) || key
    );
  }
  function node(tag, text, cls) {
    var el = document.createElement(tag);
    if (text != null) el.textContent = text;
    if (cls) el.className = cls;
    return el;
  }
  function headers() {
    var h = {};
    if ($("apiKey").value) h["X-API-Key"] = $("apiKey").value;
    return h;
  }
  async function request(url, options) {
    options = options || {};
    options.headers = Object.assign(headers(), options.headers || {});
    var controller = new AbortController();
    options.signal = controller.signal;
    var timeout = setTimeout(function () {
      controller.abort();
    }, 120000);
    try {
      var response = await fetch(url, options);
      if (!response.ok) {
        var detail;
        try {
          detail = (await response.json()).detail;
        } catch (_) {
          detail = null;
        }
        var error = new Error(
          typeof detail === "string" ? detail : "HTTP " + response.status,
        );
        error.status = response.status;
        throw error;
      }
      return response;
    } finally {
      clearTimeout(timeout);
    }
  }
  async function json(url, body, method) {
    var options =
      body === undefined
        ? {}
        : {
            method: method || "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          };
    return (await request(url, options)).json();
  }
  function alertText(text) {
    $("formAlert").textContent = text;
    $("formAlert").hidden = !text;
    if (text) $("formAlert").focus();
  }
  function showStep(n) {
    if (n > 1 && !source) {
      alertText(message("choose_file"));
      return;
    }
    alertText("");
    currentStep = n;
    document.querySelectorAll(".tab-pane").forEach(function (p, i) {
      p.classList.toggle("active", i + 1 === n);
    });
    document.querySelectorAll(".pdp-stepper-step").forEach(function (s) {
      var step = Number(s.dataset.step);
      s.classList.toggle("active", step === n);
      s.classList.toggle("completed", step < n);
      if (step === n) s.setAttribute("aria-current", "step");
      else s.removeAttribute("aria-current");
    });
    var heading = $("pane-" + n).querySelector("h2");
    heading.tabIndex = -1;
    heading.focus({ preventScroll: true });
    if (n === 3) preview();
  }
  function remember() {
    try {
      sessionStorage.setItem(
        "medcheckJob",
        JSON.stringify({
          id: jobId,
          source: source,
          study: $("studySelect").value || selectedStudy,
        }),
      );
    } catch (_) {}
  }
  function forget() {
    try {
      sessionStorage.removeItem("medcheckJob");
    } catch (_) {}
  }
  function cloud() {
    return (
      ["claude", "openai", "gemini"].indexOf($("modelSelect").value) !== -1
    );
  }
  function syncModel() {
    $("consentBlock").classList.toggle("is-visible", cloud());
    $("modelHint").hidden = true;
    if (currentStep === 3) preview();
  }
  function body() {
    var value = {
      source: source,
      study_uid: $("studySelect").value || selectedStudy || undefined,
      mode: $("modelSelect").value === "local" ? "local" : "vision",
      llm_provider:
        $("modelSelect").value === "local-vision"
          ? "local"
          : $("modelSelect").value,
      report_format: "json",
      language: $("reportLanguage").value,
      allow_cloud_llm: cloud() && $("consentCheck").checked,
      deidentify: $("deidentify").checked,
      pixels_reviewed: $("pixelsReviewed").checked,
      ocr_redact: cloud() && !$("ocrBlock").hidden && $("ocrRedact").checked,
    };
    [
      ["anatomy", "anatomy"],
      ["symptoms", "symptoms"],
      ["trauma", "trauma"],
      ["suspected_diagnosis", "suspectedDx"],
      ["official_report", "officialReport"],
    ].forEach(function (pair) {
      var v = $(pair[1]).value.trim();
      if (v) value[pair[0]] = v;
    });
    if ($("budget").value !== "") value.budget_usd = Number($("budget").value);
    return value;
  }
  async function preview() {
    if (!source || busy) return;
    var version = ++previewVersion;
    try {
      var data = await json("/api/preview", body());
      if (version !== previewVersion) return;
      $("analysisPreview").replaceChildren();
      $("analysisPreview").appendChild(
        node(
          "p",
          data.external
            ? message("external_notice") +
                " " +
                data.provider +
                " · " +
                data.image_limit +
                " " +
                message("images")
            : $("modelSelect").value === "local-vision"
              ? message("model_local_vision") +
                " · " +
                data.image_limit +
                " " +
                message("images")
              : message("local_notice"),
        ),
      );
      if (data.external)
        $("analysisPreview").appendChild(
          node(
            "p",
            data.estimated_cost_usd == null
              ? message("cost_unknown")
              : "≈ $" + Number(data.estimated_cost_usd).toFixed(4),
          ),
        );
      (data.warnings || []).forEach(function (warning) {
        $("analysisPreview").appendChild(node("p", warning));
      });
    } catch (e) {
      if (version === previewVersion)
        $("analysisPreview").textContent = e.message;
    }
  }
  function studySummary() {
    var study = studies.find(function (s) {
      return s.study_uid === $("studySelect").value;
    });
    if (!study) return;
    selectedStudy = study.study_uid;
    var count = study.series.reduce(function (n, s) {
      return n + s.slices;
    }, 0);
    $("studySummary").className = "study-summary";
    $("studySummary").replaceChildren(
      node(
        "strong",
        study.series.length +
          " " +
          message("series_count") +
          " · " +
          count +
          " " +
          message("images"),
      ),
    );
    var list = node("ul");
    study.series.forEach(function (s) {
      list.appendChild(
        node("li", s.name + " · " + s.slices + " " + message("images")),
      );
    });
    $("studySummary").appendChild(list);
    if ((study.warnings || []).length) {
      var warnings = node("div", null, "alert alert-warning");
      warnings.setAttribute("role", "note");
      var warningList = node("ul");
      study.warnings.forEach(function (warning) {
        warningList.appendChild(node("li", warning));
      });
      warnings.appendChild(warningList);
      $("studySummary").appendChild(warnings);
    }
  }
  async function upload() {
    if (busy) return;
    var version = ++uploadVersion,
      file = $("fileInput").files[0];
    source = null;
    $("studyBlock").hidden = true;
    $("autoDetectBadge").classList.remove("is-visible");
    alertText("");
    if (!file) return;
    if (!/\.(zip|dcm)$/i.test(file.name)) {
      alertText(message("bad_file"));
      return;
    }
    if (file.size > 500 * 1024 * 1024) {
      alertText(message("file_large"));
      return;
    }
    $("dropzoneSubtext").textContent =
      file.name + " · " + (file.size / 1024 / 1024).toFixed(2) + " MB";
    $("uploadStatus").textContent = message("uploading");
    $("dropzone").setAttribute("aria-busy", "true");
    try {
      var data = new FormData();
      data.append("file", file);
      var uploaded = await (
        await request("/api/upload", { method: "POST", body: data })
      ).json();
      var inspected = await json("/api/inspect", { source: uploaded.source });
      if (version !== uploadVersion) return;
      if (!inspected.studies.length) throw new Error(message("bad_file"));
      source = uploaded.source;
      studies = inspected.studies;
      $("studySelect").replaceChildren();
      studies.forEach(function (s, i) {
        var option = node(
          "option",
          (s.description || message("study") + " " + (i + 1)) +
            (s.date ? " · " + s.date : ""),
        );
        option.value = s.study_uid;
        $("studySelect").appendChild(option);
      });
      $("studyBlock").hidden = false;
      studySummary();
      $("uploadStatus").textContent = message("uploaded");
      $("autoDetectBadge").classList.add("is-visible");
    } catch (e) {
      if (version === uploadVersion) {
        $("uploadStatus").textContent = message("retry_upload");
        alertText(e.message);
      }
    } finally {
      if (version === uploadVersion) $("dropzone").removeAttribute("aria-busy");
    }
  }
  function progress(percent, text) {
    $("progressFill").style.width = percent + "%";
    $("progressBar").setAttribute("aria-valuenow", percent);
    $("progressLabel").textContent = text;
  }
  function setBusy(value) {
    busy = value;
    $("startBtn").disabled = value;
    $("fileInput").disabled = value;
    $("cancelBtn").hidden = !value;
    $("analyzeForm").setAttribute("aria-busy", String(value));
  }
  function section(title, text) {
    var el = node("section", null, "result-section");
    el.appendChild(node("h3", title));
    if (text) el.appendChild(node("p", text));
    $("resultsContent").appendChild(el);
    return el;
  }
  async function download(format) {
    try {
      var response = await request(
        "/api/jobs/" + jobId + "/report?format=" + encodeURIComponent(format),
      );
      var url = URL.createObjectURL(await response.blob());
      var a = node("a");
      a.href = url;
      a.download =
        "medcheck-report." +
        (format === "dicom-sr" ? "dcm" : format === "fhir" ? "json" : format);
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(function () {
        URL.revokeObjectURL(url);
      }, 1000);
    } catch (e) {
      alertText(e.message);
    }
  }
  function findingReview(finding, index, container) {
    var form = node("div", null, "field-stack result-finding");
    form.appendChild(
      node(
        "strong",
        finding.name ||
          finding.structure ||
          finding.anatomy ||
          (index + 1).toString(),
      ),
    );
    var findingText = node(
      "p",
      finding.findings || finding.description || finding.status || "",
    );
    form.appendChild(findingText);
    (finding.image_references || []).forEach(function (reference) {
      var seriesIndex = (result.series || []).findIndex(function (series) {
        return series.key === reference.series_name;
      });
      if (seriesIndex < 0) return;
      var open = node(
        "button",
        message("open_image") + " · " + (Number(reference.slice_index) + 1),
        "btn btn-secondary",
      );
      open.type = "button";
      open.addEventListener("click", function () {
        $("seriesSelect").value = seriesIndex;
        changeSeries();
        $("sliceRange").value = reference.slice_index;
        image();
        $("viewer").scrollIntoView({ block: "center" });
      });
      form.appendChild(open);
    });
    var id = "finding-" + index;
    var label = node("label", message("review"));
    label.htmlFor = id;
    form.appendChild(label);
    var select = node("select", null, "form-control");
    select.id = id;
    ["unreviewed", "confirmed", "rejected", "edited"].forEach(function (value) {
      var option = node("option", message(value));
      option.value = value;
      select.appendChild(option);
    });
    select.value = finding.review_status || "unreviewed";
    form.appendChild(select);
    var editLabel = node("label", message("findings_text"));
    editLabel.htmlFor = id + "-text";
    form.appendChild(editLabel);
    var edit = node("textarea", null, "form-control");
    edit.id = id + "-text";
    edit.value = finding.findings || finding.description || "";
    edit.rows = 3;
    form.appendChild(edit);
    var noteLabel = node("label", message("review_notes"));
    noteLabel.htmlFor = id + "-note";
    form.appendChild(noteLabel);
    var note = node("textarea", null, "form-control");
    note.id = id + "-note";
    note.rows = 2;
    form.appendChild(note);
    var save = node("button", message("save_review"), "btn btn-secondary");
    save.type = "button";
    save.disabled = true;
    select.addEventListener("change", function () {
      save.disabled = select.value === "unreviewed";
      edit.disabled = select.value !== "edited";
    });
    edit.disabled = select.value !== "edited";
    edit.addEventListener("input", function () {
      save.disabled = select.value !== "edited";
    });
    note.addEventListener("input", function () {
      save.disabled = select.value === "unreviewed";
    });
    var status = node("p");
    status.setAttribute("role", "status");
    save.addEventListener("click", async function () {
      save.disabled = true;
      try {
        result = await json(
          "/api/jobs/" + jobId + "/findings/" + index,
          {
            status: select.value,
            findings: select.value === "edited" ? edit.value : undefined,
            note: note.value,
          },
          "PATCH",
        );
        status.textContent = message("saved");
        if (select.value === "edited") findingText.textContent = edit.value;
      } catch (e) {
        status.textContent = e.message;
      } finally {
        save.disabled = false;
      }
    });
    form.append(save, status);
    container.appendChild(form);
  }
  function render(data) {
    result = data;
    $("resultsContent").replaceChildren();
    $("resultsContent").classList.remove("results-empty");
    section(
      message("complete"),
      data.analysis_provenance &&
        data.analysis_provenance.settings &&
        data.analysis_provenance.settings.mode === "local"
        ? message("no_findings_local")
        : data.overall_impression ||
            data.impression ||
            message("no_findings_local"),
    );
    if ((data.findings || []).length) {
      var findings = section(message("findings"));
      data.findings.forEach(function (f, i) {
        findingReview(f, i, findings);
      });
    }
    if ((data.limitations || []).length) {
      var limitations = section(message("limitations"));
      var list = node("ul");
      data.limitations.forEach(function (v) {
        list.appendChild(node("li", v));
      });
      limitations.appendChild(list);
    }
    ["quality_checks", "analysis_provenance", "reconciliation"].forEach(
      function (key) {
        if (!data[key] || !Object.keys(data[key]).length) return;
        var details = node("details", null, "result-section");
        details.appendChild(
          node(
            "summary",
            message(
              key === "quality_checks"
                ? "quality"
                : key === "reconciliation"
                  ? "reconciliation"
                  : "provenance",
            ),
          ),
        );
        var pre = node("pre", JSON.stringify(data[key], null, 2));
        pre.style.whiteSpace = "pre-wrap";
        pre.style.fontSize = ".8rem";
        details.appendChild(pre);
        $("resultsContent").appendChild(details);
      },
    );
    $("downloads").replaceChildren();
    ["json", "html", "pdf", "fhir", "dicom-sr"].forEach(function (format) {
      var button = node(
        "button",
        message("download") + " " + format.toUpperCase(),
        "btn btn-secondary",
      );
      button.type = "button";
      button.addEventListener("click", function () {
        download(format);
      });
      $("downloads").appendChild(button);
    });
    $("downloads").hidden = false;
    $("deleteBtn").hidden = false;
    $("seriesSelect").replaceChildren();
    (data.series || []).forEach(function (s, i) {
      var option = node("option", s.name || s.key);
      option.value = i;
      $("seriesSelect").appendChild(option);
    });
    $("viewer").hidden = !(data.series || []).length;
    if (!$("viewer").hidden) changeSeries();
  }
  function changeSeries() {
    var series = result.series[Number($("seriesSelect").value)];
    $("sliceRange").max = Math.max(0, series.slices - 1);
    $("sliceRange").value = 0;
    image();
  }
  async function image() {
    var version = ++imageVersion,
      index = Number($("sliceRange").value),
      count = Number($("sliceRange").max) + 1;
    $("sliceLabel").textContent =
      message("slice") + " " + (index + 1) + " / " + count;
    try {
      var response = await request(
        "/api/jobs/" +
          jobId +
          "/images/" +
          $("seriesSelect").value +
          "/" +
          index,
      );
      var bitmap = await createImageBitmap(await response.blob());
      if (version !== imageVersion) {
        bitmap.close();
        return;
      }
      var canvas = $("sliceImage");
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
      canvas.getContext("2d").drawImage(bitmap, 0, 0);
      bitmap.close();
    } catch (e) {
      if (version === imageVersion) alertText(e.message);
    }
  }
  async function poll() {
    $("resumeBtn").hidden = true;
    try {
      var data = await json("/api/jobs/" + jobId);
      alertText("");
      progress(data.progress || 0, data.step || message("running"));
      if (data.status === "completed") {
        setBusy(false);
        progress(100, message("complete"));
        render(data.result);
      } else if (data.status === "failed" || data.status === "cancelled") {
        setBusy(false);
        progress(
          0,
          data.status === "cancelled"
            ? message("cancelled")
            : data.error || message("error_generic"),
        );
      } else {
        window.setTimeout(poll, 750);
      }
    } catch (e) {
      setBusy(false);
      $("resumeBtn").hidden = e.status === 404;
      if (e.status === 404) {
        forget();
        jobId = null;
      }
      progress(
        0,
        e.status === 404 ? message("progress_waiting") : message("retry_job"),
      );
      alertText(e.message);
    }
  }
  async function analyze() {
    if (busy) return;
    if (!source) {
      showStep(1);
      alertText(message("choose_file"));
      return;
    }
    if (cloud() && !$("consentCheck").checked) {
      alertText(message("consent_required"));
      $("consentCheck").focus();
      return;
    }
    if (cloud() && !$("pixelsReviewed").checked) {
      alertText(message("pixel_required"));
      $("pixelsReviewed").focus();
      return;
    }
    alertText("");
    setBusy(true);
    $("cancelBtn").disabled = true;
    $("resumeBtn").hidden = true;
    $("downloads").hidden = true;
    $("viewer").hidden = true;
    $("deleteBtn").hidden = true;
    $("resultsContent").textContent = "";
    progress(0, message("pending"));
    try {
      var data = await json("/api/analyze", body());
      jobId = data.id;
      remember();
      $("cancelBtn").disabled = false;
      $("progressWrap").scrollIntoView({ block: "center", behavior: "auto" });
      await poll();
    } catch (e) {
      setBusy(false);
      progress(0, message("progress_waiting"));
      alertText(e.message);
    }
  }
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-goto]").forEach(function (el) {
      el.addEventListener("click", function () {
        showStep(Number(el.dataset.goto));
      });
    });
    $("analyzeForm").addEventListener("submit", function (e) {
      e.preventDefault();
      analyze();
    });
    $("dropzone").addEventListener("click", function (e) {
      if (e.target !== $("fileInput") && !busy) $("fileInput").click();
    });
    $("dropzone").addEventListener("keydown", function (e) {
      if ((e.key === "Enter" || e.key === " ") && !busy) {
        e.preventDefault();
        $("fileInput").click();
      }
    });
    $("dropzone").addEventListener("dragover", function (e) {
      e.preventDefault();
      if (!busy) $("dropzone").classList.add("dragover");
    });
    $("dropzone").addEventListener("dragleave", function () {
      $("dropzone").classList.remove("dragover");
    });
    $("dropzone").addEventListener("drop", function (e) {
      e.preventDefault();
      $("dropzone").classList.remove("dragover");
      if (busy) return;
      if (e.dataTransfer.files.length !== 1) {
        alertText(message("bad_file"));
        return;
      }
      $("fileInput").files = e.dataTransfer.files;
      upload();
    });
    $("budget").addEventListener("change", preview);
    $("fileInput").addEventListener("change", upload);
    $("studySelect").addEventListener("change", studySummary);
    $("modelSelect").addEventListener("change", syncModel);
    $("cancelBtn").addEventListener("click", async function () {
      $("cancelBtn").disabled = true;
      try {
        await json("/api/jobs/" + jobId + "/cancel", {});
      } catch (e) {
        alertText(e.message);
      } finally {
        $("cancelBtn").disabled = false;
      }
    });
    $("resumeBtn").addEventListener("click", function () {
      setBusy(true);
      poll();
    });
    $("seriesSelect").addEventListener("change", changeSeries);
    $("sliceRange").addEventListener("input", image);
    window.addEventListener("beforeunload", function (e) {
      if (busy) {
        e.preventDefault();
        e.returnValue = "";
      }
    });
    $("deleteBtn").addEventListener("click", async function () {
      $("deleteBtn").disabled = true;
      try {
        await request("/api/jobs/" + jobId, { method: "DELETE" });
        if (source && source.indexOf("upload:") === 0)
          await request("/api/uploads/" + source.slice(7), {
            method: "DELETE",
          });
        jobId = null;
        source = null;
        selectedStudy = "";
        result = null;
        forget();
        $("fileInput").value = "";
        $("studyBlock").hidden = true;
        $("uploadStatus").textContent = "";
        $("autoDetectBadge").classList.remove("is-visible");
        $("dropzoneSubtext").textContent = message("dropzone_formats");
        $("downloads").hidden = true;
        $("viewer").hidden = true;
        $("deleteBtn").hidden = true;
        $("resultsContent").textContent = message("deleted");
        progress(0, message("progress_waiting"));
        showStep(1);
      } catch (e) {
        alertText(e.message);
      } finally {
        $("deleteBtn").disabled = false;
      }
    });
    syncModel();
    function capabilities() {
      json("/api/capabilities")
        .then(function (data) {
          $("ocrBlock").hidden = !data.ocr_available;
          (data.providers || []).forEach(function (p) {
            var option = $("modelSelect").querySelector(
              'option[value="' + p.name + '"]',
            );
            if (p.name === "local") {
              var localVision = $("modelSelect").querySelector(
                'option[value="local-vision"]',
              );
              localVision.disabled = !p.available;
              localVision.textContent =
                message("model_local_vision") +
                " · " +
                (p.available ? p.model : message("unavailable"));
            }
            if (option && p.name !== "local") {
              option.disabled = !p.available;
              option.textContent =
                p.name +
                " · " +
                (p.available ? p.model : message("unavailable"));
            }
          });
        })
        .catch(function () {
          /* Upload provides an actionable authentication error. */
        });
    }
    function restoreStudies() {
      json("/api/inspect", { source: source })
        .then(function (data) {
          studies = data.studies;
          $("studySelect").replaceChildren();
          studies.forEach(function (study, index) {
            var option = node(
              "option",
              study.description || message("study") + " " + (index + 1),
            );
            option.value = study.study_uid;
            $("studySelect").appendChild(option);
          });
          if (selectedStudy) $("studySelect").value = selectedStudy;
          $("studyBlock").hidden = false;
          studySummary();
        })
        .catch(function () {
          /* The reconnect action remains available if a key is needed. */
        });
    }
    capabilities();
    $("apiKey").addEventListener("change", function () {
      capabilities();
      if (source && !studies.length) restoreStudies();
    });
    try {
      var saved = JSON.parse(sessionStorage.getItem("medcheckJob") || "null");
      if (saved && /^[a-zA-Z0-9-]+$/.test(saved.id)) {
        jobId = saved.id;
        source = saved.source;
        selectedStudy = saved.study || "";
        setBusy(true);
        restoreStudies();
        poll();
      }
    } catch (_) {
      forget();
    }
  });
})();
