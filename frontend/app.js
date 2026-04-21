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
    if (pillarRocks && (!feat.big_rock || (pillarRocks.indexOf(feat.big_rock) < 0 &&
        pillarRocks.indexOf(feat.big_rock.split(", ")[0]) < 0))) return false;
    if (filters.rock && (!feat.big_rock || (feat.big_rock !== filters.rock &&
        feat.big_rock.split(", ")[0] !== filters.rock))) return false;
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
    if (pillarRocks && (!rfe.big_rock || (pillarRocks.indexOf(rfe.big_rock) < 0 &&
        pillarRocks.indexOf(rfe.big_rock.split(", ")[0]) < 0))) return false;
    if (filters.rock && (!rfe.big_rock || (rfe.big_rock !== filters.rock &&
        rfe.big_rock.split(", ")[0] !== filters.rock))) return false;
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

  // Count tiers in filtered results
  var tier1Features = 0;
  var tier2Features = 0;
  var tier3Features = 0;
  for (var j = 0; j < filteredFeatures.length; j++) {
    var ft = filteredFeatures[j].tier || 1;
    if (ft === 3) { tier3Features++; }
    else if (ft === 2) { tier2Features++; }
    else { tier1Features++; }
  }

  var tier1Rfes = 0;
  var tier2Rfes = 0;
  for (var k = 0; k < filteredRfes.length; k++) {
    var rt = filteredRfes[k].tier || 1;
    if (rt === 2) { tier2Rfes++; }
    else { tier1Rfes++; }
  }

  var releaseLabel = currentVersion ? "rhoai-" + currentVersion : "this";

  // Tier 1 card
  var tier1Card = document.createElement("div");
  tier1Card.className = "summary-card";
  tier1Card.innerHTML =
    '<div class="card-title">Tier 1: Milestone Essentials</div>' +
    '<div class="card-desc">Must-have for ' + escapeHtml(releaseLabel) + ' release</div>' +
    '<div class="card-stat">' + tier1Features + ' <span>features</span></div>' +
    '<div class="card-stat">' + tier1Rfes + ' <span>RFEs</span></div>';
  container.appendChild(tier1Card);

  // Tier 2 card
  var tier2Card = document.createElement("div");
  tier2Card.className = "summary-card";
  tier2Card.innerHTML =
    '<div class="card-title">Tier 2: Enhancements</div>' +
    '<div class="card-desc">High-value UX/Customer impact</div>' +
    '<div class="card-stat">' + tier2Features + ' <span>features</span></div>' +
    '<div class="card-stat">' + tier2Rfes + ' <span>RFEs</span></div>';
  container.appendChild(tier2Card);

  // Tier 3 card
  var tier3Card = document.createElement("div");
  tier3Card.className = "summary-card";
  tier3Card.innerHTML =
    '<div class="card-title">Tier 3: Collaborative Support</div>' +
    '<div class="card-desc">Cross-team priorities</div>' +
    '<div class="card-stat">' + tier3Features + ' <span>features</span></div>';
  container.appendChild(tier3Card);

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

function tierLabel(tierNum) {
  if (tierNum === 1) return "Tier 1: Milestone Essentials";
  if (tierNum === 2) return "Tier 2: Enhancements";
  if (tierNum === 3) return "Tier 3: Collaborative Support";
  return "Tier " + tierNum;
}

function renderFeaturesTable(features) {
  var tbody = document.querySelector("#features-table tbody");
  tbody.innerHTML = "";

  if (features.length === 0) {
    tbody.innerHTML = '<tr><td colspan="13" class="empty-state"><p>No features match the current filters.</p></td></tr>';
    return;
  }

  var baseUrl = currentData.jira_base_url;
  var currentTier = 0;

  for (var i = 0; i < features.length; i++) {
    var f = features[i];
    var ft = f.tier || 1;

    if (ft !== currentTier) {
      currentTier = ft;
      var sep = document.createElement("tr");
      sep.className = "tier-separator";
      sep.innerHTML = '<td colspan="13">' + tierLabel(currentTier) + '</td>';
      tbody.appendChild(sep);
    }

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
  var currentTier = 0;

  for (var i = 0; i < rfes.length; i++) {
    var r = rfes[i];
    var rt = r.tier || 1;

    if (rt !== currentTier) {
      currentTier = rt;
      var sep = document.createElement("tr");
      sep.className = "tier-separator";
      sep.innerHTML = '<td colspan="8">' + tierLabel(currentTier) + '</td>';
      tbody.appendChild(sep);
    }

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
  var tabs = document.querySelectorAll(".tab");
  for (var i = 0; i < tabs.length; i++) {
    var tab = tabs[i];
    var name = tab.dataset.tab;
    if (name === "big-rocks") {
      tab.textContent = "Big Rocks (" + rocks.length + ")";
    } else if (name === "features") {
      tab.textContent = "Features (" + features.length + ")";
    } else if (name === "rfes") {
      tab.textContent = "RFEs (" + rfes.length + ")";
    }
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

// ---- Google Sheets export ----

function exportToSheets() {
  if (!currentVersion) return;
  var btn = document.getElementById("export-btn");
  btn.disabled = true;
  btn.textContent = "Creating spreadsheet...";

  fetchJSON(API_BASE + "/releases/" + currentVersion + "/export", { method: "POST" })
    .then(function (data) {
      btn.disabled = false;
      btn.textContent = "Export to Google Sheets";
      if (data && data.url) {
        window.open(data.url, "_blank");
      }
    })
    .catch(function (err) {
      btn.disabled = false;
      btn.textContent = "Export to Google Sheets";
      console.error("Export failed:", err);
    });
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
  document.getElementById("export-btn").addEventListener("click", exportToSheets);

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
