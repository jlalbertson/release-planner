/**
 * Release Planner -- frontend application.
 *
 * Fetches data from the FastAPI backend, renders three tabs
 * (Big Rocks, Features, RFEs), provides client-side filtering,
 * summary cards, and Excel export.
 */

const API_BASE = "/api";

// ---- State ----

let currentData = null;      // CandidateResponse from the server
let currentVersion = null;   // Selected release version
let searchTimeout = null;    // Debounce timer for search input

// ---- Auth helpers ----

function getApiKey() {
  return sessionStorage.getItem("rp_api_key");
}

function showLogin() {
  document.getElementById("login-overlay").style.display = "flex";
  document.getElementById("api-key-input").focus();
}

function hideLogin() {
  document.getElementById("login-overlay").style.display = "none";
}

// ---- Fetch helper ----

async function fetchJSON(url, options) {
  const headers = {};
  const key = getApiKey();
  if (key) {
    headers["Authorization"] = "Bearer " + key;
  }
  const fetchOpts = Object.assign({ headers: headers }, options || {});
  const res = await fetch(url, fetchOpts);
  if (res.status === 401) {
    showLogin();
    throw new Error("Authentication required");
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(res.status + " " + res.statusText + ": " + text);
  }
  return res.json();
}

// ---- Utility ----

function escapeHtml(str) {
  if (!str) return "";
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function showLoading(show) {
  document.getElementById("loading-overlay").style.display = show ? "flex" : "none";
}

// ---- Demo mode ----

async function checkDemoMode() {
  try {
    const res = await fetch(API_BASE + "/status");
    if (res.ok) {
      const data = await res.json();
      if (data.demo_mode) {
        document.getElementById("demo-banner").style.display = "block";
      }
    }
  } catch (_) {
    // ignore -- status endpoint is best-effort
  }
}

// ---- Filter state ----

function getFilters() {
  return {
    pillar: document.getElementById("filter-pillar").value,
    rock: document.getElementById("filter-rock").value,
    status: document.getElementById("filter-status").value,
    team: document.getElementById("filter-team").value,
    priority: document.getElementById("filter-priority").value,
    search: document.getElementById("filter-search").value.trim().toLowerCase(),
  };
}

function hasActiveFilters() {
  var f = getFilters();
  return f.pillar || f.rock || f.status || f.team || f.priority || f.search;
}

function updateClearButton() {
  var btn = document.getElementById("clear-filters");
  btn.style.display = hasActiveFilters() ? "inline-block" : "none";
}

function clearFilters() {
  document.getElementById("filter-pillar").value = "";
  document.getElementById("filter-rock").value = "";
  document.getElementById("filter-status").value = "";
  document.getElementById("filter-team").value = "";
  document.getElementById("filter-priority").value = "";
  document.getElementById("filter-search").value = "";
  applyFilters();
}

// ---- Populate filter dropdowns ----

function populateDropdown(selectId, values, currentValue) {
  var select = document.getElementById(selectId);
  // Keep the "All" option
  var firstOption = select.options[0];
  select.innerHTML = "";
  select.appendChild(firstOption);
  for (var i = 0; i < values.length; i++) {
    var opt = document.createElement("option");
    opt.value = values[i];
    opt.textContent = values[i];
    select.appendChild(opt);
  }
  // Restore selection if it still exists
  if (currentValue) {
    for (var j = 0; j < select.options.length; j++) {
      if (select.options[j].value === currentValue) {
        select.value = currentValue;
        break;
      }
    }
  }
}

function populateFilterDropdowns() {
  if (!currentData) return;
  var opts = currentData.filter_options;
  populateDropdown("filter-pillar", opts.pillars, "");
  populateDropdown("filter-rock", opts.rocks, "");
  populateDropdown("filter-status", opts.statuses, "");
  populateDropdown("filter-team", opts.teams, "");
  populateDropdown("filter-priority", opts.priorities, "");
}

// ---- Cascading rock filter ----

function updateRockDropdown() {
  if (!currentData) return;
  var filters = getFilters();
  var rocks = currentData.filter_options.rocks;

  if (filters.pillar) {
    // Only show rocks that belong to the selected pillar
    var pillarRocks = currentData.big_rocks
      .filter(function (r) { return r.pillar === filters.pillar; })
      .map(function (r) { return r.name; });
    rocks = rocks.filter(function (r) { return pillarRocks.indexOf(r) >= 0; });
  }

  populateDropdown("filter-rock", rocks, filters.rock);
}

// ---- Filtering logic ----

function getRocksForPillar(pillar) {
  if (!currentData || !pillar) return null;
  return currentData.big_rocks
    .filter(function (r) { return r.pillar === pillar; })
    .map(function (r) { return r.name; });
}

function matchesSearch(item, term) {
  if (!term) return true;
  var key = (item.issue_key || "").toLowerCase();
  var summary = (item.summary || item.full_name || item.name || "").toLowerCase();
  var components = (item.components || "").toLowerCase();
  return key.indexOf(term) >= 0 || summary.indexOf(term) >= 0 || components.indexOf(term) >= 0;
}

function filterBigRocks() {
  if (!currentData) return [];
  var filters = getFilters();
  return currentData.big_rocks.filter(function (rock) {
    if (filters.pillar && rock.pillar !== filters.pillar) return false;
    if (filters.rock && rock.name !== filters.rock) return false;
    if (filters.priority) {
      // Big Rocks don't have a text priority -- skip priority filter here
    }
    if (filters.search) {
      var term = filters.search;
      var name = (rock.name || "").toLowerCase();
      var fullName = (rock.full_name || "").toLowerCase();
      var pillar = (rock.pillar || "").toLowerCase();
      var owner = (rock.owner || "").toLowerCase();
      if (name.indexOf(term) < 0 && fullName.indexOf(term) < 0 &&
          pillar.indexOf(term) < 0 && owner.indexOf(term) < 0) return false;
    }
    return true;
  });
}

function filterFeatures() {
  if (!currentData) return [];
  var filters = getFilters();
  var pillarRocks = getRocksForPillar(filters.pillar);

  return currentData.features.filter(function (feat) {
    if (pillarRocks && pillarRocks.indexOf(feat.big_rock) < 0 &&
        pillarRocks.indexOf(feat.big_rock.split(", ")[0]) < 0) return false;
    if (filters.rock && feat.big_rock !== filters.rock &&
        feat.big_rock.split(", ")[0] !== filters.rock) return false;
    if (filters.status && feat.status !== filters.status) return false;
    if (filters.team && feat.components.indexOf(filters.team) < 0) return false;
    if (filters.priority && feat.priority !== filters.priority) return false;
    if (!matchesSearch(feat, filters.search)) return false;
    return true;
  });
}

function filterRfes() {
  if (!currentData) return [];
  var filters = getFilters();
  var pillarRocks = getRocksForPillar(filters.pillar);

  return currentData.rfes.filter(function (rfe) {
    if (pillarRocks && pillarRocks.indexOf(rfe.big_rock) < 0 &&
        pillarRocks.indexOf(rfe.big_rock.split(", ")[0]) < 0) return false;
    if (filters.rock && rfe.big_rock !== filters.rock &&
        rfe.big_rock.split(", ")[0] !== filters.rock) return false;
    if (filters.status && rfe.status !== filters.status) return false;
    if (filters.priority && rfe.priority !== filters.priority) return false;
    if (!matchesSearch(rfe, filters.search)) return false;
    return true;
  });
}

// ---- Summary cards ----

function renderSummaryCards(filteredFeatures, filteredRfes, filteredRocks) {
  var container = document.getElementById("summary-cards");
  container.innerHTML = "";

  if (!currentData) return;

  // Per-pillar cards
  var pillarMap = {};
  for (var i = 0; i < filteredRocks.length; i++) {
    var rock = filteredRocks[i];
    if (!rock.pillar) continue;
    if (!pillarMap[rock.pillar]) {
      pillarMap[rock.pillar] = { features: 0, rfes: 0 };
    }
  }

  for (var j = 0; j < filteredFeatures.length; j++) {
    var feat = filteredFeatures[j];
    var rockName = feat.big_rock.split(", ")[0];
    var rockObj = currentData.big_rocks.find(function (r) { return r.name === rockName; });
    if (rockObj && rockObj.pillar && pillarMap[rockObj.pillar] !== undefined) {
      pillarMap[rockObj.pillar].features++;
    }
  }

  for (var k = 0; k < filteredRfes.length; k++) {
    var rfe = filteredRfes[k];
    var rn = rfe.big_rock.split(", ")[0];
    var ro = currentData.big_rocks.find(function (r) { return r.name === rn; });
    if (ro && ro.pillar && pillarMap[ro.pillar] !== undefined) {
      pillarMap[ro.pillar].rfes++;
    }
  }

  var pillars = Object.keys(pillarMap).sort();
  for (var p = 0; p < pillars.length; p++) {
    var pillar = pillars[p];
    var stats = pillarMap[pillar];
    var card = document.createElement("div");
    card.className = "summary-card";
    card.innerHTML =
      '<div class="card-title">' + escapeHtml(pillar) + '</div>' +
      '<div class="card-stat">' + stats.features + ' <span>features</span></div>' +
      '<div class="card-stat">' + stats.rfes + ' <span>RFEs</span></div>';
    container.appendChild(card);
  }

  // Total card
  var totalCard = document.createElement("div");
  totalCard.className = "summary-card total-card";
  totalCard.innerHTML =
    '<div class="card-title">Total</div>' +
    '<div class="card-stat">' + filteredFeatures.length + ' <span>features</span></div>' +
    '<div class="card-stat">' + filteredRfes.length + ' <span>RFEs</span></div>' +
    '<div class="card-stat">' + filteredRocks.length + ' <span>big rocks</span></div>';
  container.appendChild(totalCard);
}

// ---- Status badge helper ----

function statusBadgeClass(status) {
  if (!status) return "";
  var s = status.toLowerCase().replace(/\s+/g, "-");
  if (s === "in-progress") return "status-in-progress";
  if (s === "new") return "status-new";
  if (s === "refinement") return "status-refinement";
  if (s === "approved") return "status-approved";
  if (s === "review" || s === "stakeholder-review") return "status-review";
  return "";
}

function priorityClass(priority) {
  if (!priority) return "";
  var p = priority.toLowerCase();
  if (p === "blocker" || p === "critical") return "priority-blocker";
  return "";
}

// ---- Table rendering ----

function renderBigRocksTable(rocks) {
  var tbody = document.querySelector("#big-rocks-table tbody");
  tbody.innerHTML = "";

  if (rocks.length === 0) {
    tbody.innerHTML = '<tr><td colspan="10" class="empty-state"><p>No big rocks match the current filters.</p></td></tr>';
    return;
  }

  var baseUrl = currentData.jira_base_url;

  for (var i = 0; i < rocks.length; i++) {
    var rock = rocks[i];
    var outcomeLinks = rock.outcome_keys.map(function (key) {
      return '<a class="issue-link" href="' + baseUrl + '/' + key + '" target="_blank" rel="noopener">' + escapeHtml(key) + '</a>';
    }).join(", ");

    var outcomeDescs = rock.outcome_keys.map(function (key) {
      return escapeHtml(rock.outcome_descriptions[key] || "");
    }).join("; ");

    var tr = document.createElement("tr");
    tr.innerHTML =
      '<td>' + escapeHtml(rock.pillar) + '</td>' +
      '<td>' + rock.priority + '</td>' +
      '<td>' + escapeHtml(rock.name) + '</td>' +
      '<td>' + outcomeLinks + '</td>' +
      '<td>' + outcomeDescs + '</td>' +
      '<td>' + escapeHtml(rock.state) + '</td>' +
      '<td>' + escapeHtml(rock.owner) + '</td>' +
      '<td>' + rock.feature_count + '</td>' +
      '<td>' + rock.rfe_count + '</td>' +
      '<td>' + escapeHtml(rock.notes) + '</td>';
    tbody.appendChild(tr);
  }
}

function renderFeaturesTable(features) {
  var tbody = document.querySelector("#features-table tbody");
  tbody.innerHTML = "";

  if (features.length === 0) {
    tbody.innerHTML = '<tr><td colspan="13" class="empty-state"><p>No features match the current filters.</p></td></tr>';
    return;
  }

  var baseUrl = currentData.jira_base_url;

  for (var i = 0; i < features.length; i++) {
    var f = features[i];
    var issueLink = '<a class="issue-link" href="' + baseUrl + '/' + f.issue_key + '" target="_blank" rel="noopener">' + escapeHtml(f.issue_key) + '</a>';
    var rfeLink = f.rfe
      ? '<a class="issue-link" href="' + baseUrl + '/' + f.rfe + '" target="_blank" rel="noopener">' + escapeHtml(f.rfe) + '</a>'
      : '';

    var tr = document.createElement("tr");
    tr.innerHTML =
      '<td>' + escapeHtml(f.big_rock) + '</td>' +
      '<td>' + issueLink + '</td>' +
      '<td><span class="status-badge ' + statusBadgeClass(f.status) + '">' + escapeHtml(f.status) + '</span></td>' +
      '<td class="' + priorityClass(f.priority) + '">' + escapeHtml(f.priority) + '</td>' +
      '<td>' + escapeHtml(f.phase) + '</td>' +
      '<td>' + escapeHtml(f.summary) + '</td>' +
      '<td>' + escapeHtml(f.components) + '</td>' +
      '<td>' + escapeHtml(f.target_release) + '</td>' +
      '<td>' + escapeHtml(f.fix_version) + '</td>' +
      '<td>' + escapeHtml(f.pm) + '</td>' +
      '<td>' + escapeHtml(f.delivery_owner) + '</td>' +
      '<td>' + rfeLink + '</td>' +
      '<td>' + escapeHtml(f.labels) + '</td>';
    tbody.appendChild(tr);
  }
}

function renderRfesTable(rfes) {
  var tbody = document.querySelector("#rfes-table tbody");
  tbody.innerHTML = "";

  if (rfes.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" class="empty-state"><p>No RFEs match the current filters.</p></td></tr>';
    return;
  }

  var baseUrl = currentData.jira_base_url;

  for (var i = 0; i < rfes.length; i++) {
    var r = rfes[i];
    var issueLink = '<a class="issue-link" href="' + baseUrl + '/' + r.issue_key + '" target="_blank" rel="noopener">' + escapeHtml(r.issue_key) + '</a>';

    var tr = document.createElement("tr");
    tr.innerHTML =
      '<td>' + escapeHtml(r.big_rock) + '</td>' +
      '<td>' + issueLink + '</td>' +
      '<td><span class="status-badge ' + statusBadgeClass(r.status) + '">' + escapeHtml(r.status) + '</span></td>' +
      '<td class="' + priorityClass(r.priority) + '">' + escapeHtml(r.priority) + '</td>' +
      '<td>' + escapeHtml(r.summary) + '</td>' +
      '<td>' + escapeHtml(r.components) + '</td>' +
      '<td>' + escapeHtml(r.pm) + '</td>' +
      '<td>' + escapeHtml(r.labels) + '</td>';
    tbody.appendChild(tr);
  }
}

// ---- Tab count display ----

function updateTabCount(rocks, features, rfes) {
  var activeTab = document.querySelector(".tab.active");
  var countEl = document.getElementById("tab-count");
  if (!activeTab) {
    countEl.textContent = "";
    return;
  }
  var tabName = activeTab.dataset.tab;
  if (tabName === "big-rocks") {
    countEl.textContent = rocks.length + " big rock" + (rocks.length !== 1 ? "s" : "");
  } else if (tabName === "features") {
    countEl.textContent = features.length + " feature" + (features.length !== 1 ? "s" : "");
  } else if (tabName === "rfes") {
    countEl.textContent = rfes.length + " RFE" + (rfes.length !== 1 ? "s" : "");
  }
}

// ---- Apply filters and re-render ----

function applyFilters() {
  updateRockDropdown();
  updateClearButton();

  var rocks = filterBigRocks();
  var features = filterFeatures();
  var rfes = filterRfes();

  renderSummaryCards(features, rfes, rocks);
  renderBigRocksTable(rocks);
  renderFeaturesTable(features);
  renderRfesTable(rfes);
  updateTabCount(rocks, features, rfes);
}

// ---- Tab switching ----

function setupTabs() {
  var tabs = document.querySelectorAll(".tab");
  for (var i = 0; i < tabs.length; i++) {
    tabs[i].addEventListener("click", function () {
      // Deactivate all tabs
      var allTabs = document.querySelectorAll(".tab");
      for (var j = 0; j < allTabs.length; j++) {
        allTabs[j].classList.remove("active");
      }
      var allContents = document.querySelectorAll(".tab-content");
      for (var k = 0; k < allContents.length; k++) {
        allContents[k].classList.remove("active");
      }

      // Activate clicked tab
      this.classList.add("active");
      var tabId = "tab-" + this.dataset.tab;
      document.getElementById(tabId).classList.add("active");

      // Update count
      if (currentData) {
        var rocks = filterBigRocks();
        var features = filterFeatures();
        var rfes = filterRfes();
        updateTabCount(rocks, features, rfes);
      }
    });
  }
}

// ---- Excel export ----

function exportExcel() {
  if (!currentVersion) return;
  var url = API_BASE + "/releases/" + currentVersion + "/export";
  var key = getApiKey();

  // Use XMLHttpRequest for download with auth header
  var xhr = new XMLHttpRequest();
  xhr.open("GET", url, true);
  xhr.responseType = "blob";
  if (key) {
    xhr.setRequestHeader("Authorization", "Bearer " + key);
  }

  xhr.onload = function () {
    if (xhr.status === 200) {
      var blob = xhr.response;
      var link = document.createElement("a");
      link.href = window.URL.createObjectURL(blob);
      link.download = "rhoai-" + currentVersion + "-candidates.xlsx";
      link.click();
      window.URL.revokeObjectURL(link.href);
    } else if (xhr.status === 401) {
      showLogin();
    } else {
      console.error("Export failed:", xhr.status, xhr.statusText);
    }
  };

  xhr.onerror = function () {
    console.error("Export request failed");
  };

  xhr.send();
}

// ---- Refresh ----

async function refreshData() {
  if (!currentVersion) return;
  var btn = document.getElementById("refresh-btn");
  btn.disabled = true;
  showLoading(true);

  try {
    await fetchJSON(API_BASE + "/releases/" + currentVersion + "/refresh", { method: "POST" });
    // The refresh endpoint returns CandidateResponse directly
    // but we fetch candidates again to keep flow consistent
    await loadRelease(currentVersion);
  } catch (err) {
    if (!err.message.includes("Authentication required")) {
      console.error("Refresh failed:", err);
    }
  } finally {
    btn.disabled = false;
    showLoading(false);
  }
}

// ---- Load release data ----

async function loadRelease(version) {
  currentVersion = version;
  showLoading(true);

  try {
    var data = await fetchJSON(API_BASE + "/releases/" + version + "/candidates");
    currentData = data;
    populateFilterDropdowns();
    clearFilters();
  } catch (err) {
    if (!err.message.includes("Authentication required")) {
      console.error("Failed to load release:", err);
    }
  } finally {
    showLoading(false);
  }
}

// ---- Init ----

async function init() {
  checkDemoMode();
  setupTabs();

  // Wire up filter events
  document.getElementById("filter-pillar").addEventListener("change", function () {
    // Reset rock filter when pillar changes
    document.getElementById("filter-rock").value = "";
    applyFilters();
  });
  document.getElementById("filter-rock").addEventListener("change", applyFilters);
  document.getElementById("filter-status").addEventListener("change", applyFilters);
  document.getElementById("filter-team").addEventListener("change", applyFilters);
  document.getElementById("filter-priority").addEventListener("change", applyFilters);

  // Debounced search
  document.getElementById("filter-search").addEventListener("input", function () {
    if (searchTimeout) clearTimeout(searchTimeout);
    searchTimeout = setTimeout(applyFilters, 300);
  });

  // Clear filters
  document.getElementById("clear-filters").addEventListener("click", clearFilters);

  // Export
  document.getElementById("export-btn").addEventListener("click", exportExcel);

  // Refresh
  document.getElementById("refresh-btn").addEventListener("click", refreshData);

  // Load releases
  try {
    var releases = await fetchJSON(API_BASE + "/releases");
    var select = document.getElementById("release-select");

    for (var i = 0; i < releases.length; i++) {
      var rel = releases[i];
      var opt = document.createElement("option");
      opt.value = rel.version;
      opt.textContent = rel.label;
      select.appendChild(opt);
    }

    select.addEventListener("change", function () {
      loadRelease(select.value);
    });

    if (releases.length > 0) {
      await loadRelease(releases[0].version);
    }
  } catch (err) {
    if (!err.message.includes("Authentication required")) {
      console.error("Failed to initialize:", err);
    }
  }
}

// ---- Login handler ----

function handleLogin() {
  var input = document.getElementById("api-key-input");
  var key = input.value.trim();
  if (key) {
    sessionStorage.setItem("rp_api_key", key);
    hideLogin();
    init();
  }
}

document.getElementById("login-btn").addEventListener("click", handleLogin);
document.getElementById("api-key-input").addEventListener("keydown", function (e) {
  if (e.key === "Enter") handleLogin();
});

init();
