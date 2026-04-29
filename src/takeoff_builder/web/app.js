const state = {
  summary: null,
  projects: [],
  selectedId: null,
  projectDetails: new Map(),
  isBuilding: false,
  buildStatus: null,
};

const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

function getSelectedProfile() {
  return $("buildProfile").value;
}

function getProfileConfig(profile = getSelectedProfile()) {
  return state.summary?.available_profiles?.[profile] ?? null;
}

function renderSummary() {
  const summary = state.summary;
  const cards = [
    ["Projects", summary.project_count],
    ["Sample", summary.sample_project_count],
    ["Challenge", summary.challenge_project_count],
  ];
  $("summaryGrid").innerHTML = cards
    .map(
      ([label, value]) => `
        <div class="summaryCard">
          <strong>${value}</strong>
          <span>${label}</span>
        </div>
      `
    )
    .join("");

  if (summary.profile) {
    $("buildProfile").value = summary.profile;
  }
  renderProfileMeta();
  renderWorkspaceOverview();
}

function renderProfileMeta() {
  const summary = state.summary;
  const profile = getSelectedProfile();
  const config = getProfileConfig(profile);
  $("profileDescription").textContent = config?.description || "";
  if (!state.isBuilding) {
    $("commandStatus").textContent = summary?.profile_label
      ? `Current build: ${summary.profile_label}`
      : "No build artifacts yet. Use the button above to generate them.";
  }
}

function renderWorkspaceOverview() {
  const summary = state.summary;
  const buildStatus = state.buildStatus;
  const selectedProfile = getSelectedProfile();
  const selectedConfig = getProfileConfig(selectedProfile);
  const builtLabel =
    summary.build_state === "ready" ? `Ready${summary.built_at_utc ? ` · ${formatDate(summary.built_at_utc)}` : ""}` : "Not built";
  $("overviewBuildState").textContent = builtLabel;
  $("overviewBuildMeta").textContent =
    buildStatus?.status === "running"
      ? `${buildStatus.message} Started ${formatDate(buildStatus.started_at)}.`
      : summary.build_state === "ready"
      ? `Artifacts, reports, and review storage are available under ${summary.output_path}.`
      : "The workspace can start empty and build from the UI.";
  $("overviewProfile").textContent = selectedConfig?.label || "Not selected";
  $("overviewProfileDescription").textContent = selectedConfig?.description || "Choose the scope that matches the submission goal.";
  $("overviewOutputPath").textContent = summary.output_path || "artifacts";
  const backend = summary.review_backend?.label || "Unknown";
  $("overviewRootPath").textContent = `Dataset root: ${summary.root_path || "Unknown"} · Review store: ${backend}`;
}

function setBuildUiState(isBuilding, message, isError = false) {
  state.isBuilding = isBuilding;
  $("rebuildButton").disabled = isBuilding;
  $("buildProfile").disabled = isBuilding;
  $("rebuildButton").textContent = isBuilding ? "Running Build..." : "Run Build";
  $("commandStatus").textContent = message;
  $("buildStateBadge").textContent = isError ? "Error" : isBuilding ? "Running" : state.summary?.build_state === "ready" ? "Ready" : "Idle";
  $("buildStateBadge").classList.toggle("isRunning", isBuilding);
  $("buildStateBadge").classList.toggle("isError", isError);
}

function filteredProjects() {
  const search = $("searchInput").value.trim().toLowerCase();
  const setFilter = $("setFilter").value;
  const scoreFilter = $("scoreFilter").value;
  return state.projects.filter((project) => {
    const haystack = [
      project.takeoff_id,
      project.project_name,
      project.trade_scope,
      project.set_name,
    ]
      .join(" ")
      .toLowerCase();
    const matchesSearch = !search || haystack.includes(search);
    const matchesSet = setFilter === "all" || project.set_name === setFilter;
    const matchesScore = scoreFilter === "all" || String(project.scored) === scoreFilter;
    return matchesSearch && matchesSet && matchesScore;
  });
}

function renderProjectList() {
  const projects = filteredProjects();
  if (!projects.some((project) => project.takeoff_id === state.selectedId)) {
    state.selectedId = projects[0]?.takeoff_id ?? null;
  }
  $("projectList").innerHTML = projects.length
    ? projects
        .map(
          (project) => `
            <button class="projectButton ${project.takeoff_id === state.selectedId ? "active" : ""}" data-project-id="${project.takeoff_id}">
              <strong>${project.takeoff_id}</strong>
              <div>${project.project_name}</div>
              <small>${project.trade_scope || "Unknown scope"} · ${project.predicted_item_count} predicted items</small>
            </button>
          `
        )
        .join("")
    : `<div class="emptyState"><h3>No matching projects</h3><p class="muted">Adjust filters or run a different build profile.</p></div>`;

  document.querySelectorAll("[data-project-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedId = button.dataset.projectId;
      renderProjectList();
      await renderSelectedProject();
    });
  });
}

async function renderSelectedProject() {
  if (!state.selectedId) {
    $("emptyState").classList.remove("hidden");
    $("projectPane").classList.add("hidden");
    $("emptyStateText").textContent =
      state.summary?.build_state === "not_built"
        ? "No artifacts exist yet. Choose a build profile and click Run Build to generate the dataset outputs."
        : "Choose a project from the left to inspect predictions, scoring, and reviewer state.";
    return;
  }

  let detail = state.projectDetails.get(state.selectedId);
  if (!detail) {
    detail = await api(`/api/projects/${state.selectedId}`);
    state.projectDetails.set(state.selectedId, detail);
  }

  $("emptyState").classList.add("hidden");
  $("projectPane").classList.remove("hidden");
  $("workspaceTitle").textContent = `${detail.takeoff_id} — ${detail.project_name}`;
  const backendLabel = detail.review_backend?.label || "Unknown";
  $("workspaceSubtitle").textContent = `Trade scope: ${detail.trade_scope || "Unknown"} · Review record stored in ${backendLabel}`;
  $("detailSet").textContent = detail.set_name.toUpperCase();
  $("detailTitle").textContent = `${detail.takeoff_id} — ${detail.project_name}`;
  $("detailTrade").textContent = detail.trade_scope || "Unknown";
  $("predictedCount").textContent = `${detail.prediction_preview.length} items shown`;

  $("pillRow").innerHTML = [
    `${detail.input_file_count} input files`,
    `${detail.predicted_item_count} predicted items`,
    detail.scored ? "sample scored" : "challenge output",
  ]
    .map((value) => `<span class="pill">${value}</span>`)
    .join("");

  $("snapshotList").innerHTML = `
    <dt>Takeoff ID</dt><dd>${detail.takeoff_id}</dd>
    <dt>Set</dt><dd>${detail.set_name}</dd>
    <dt>Trade Scope</dt><dd>${detail.trade_scope || "Unknown"}</dd>
    <dt>Input Files</dt><dd>${detail.input_file_count}</dd>
    <dt>Gold Files</dt><dd>${detail.gold_file_count}</dd>
    <dt>Warnings</dt><dd>${detail.warnings.length ? detail.warnings.join(" ") : "None"}</dd>
  `;

  $("artifactLinks").innerHTML = Object.entries(detail.artifact_paths)
    .filter(([, value]) => value)
    .map(([label, value]) => `<a href="/artifacts/${value}" target="_blank" rel="noreferrer">${label}</a>`)
    .join("");

  $("predictedItemsTable").innerHTML = detail.prediction_preview
    .map(
      (item) => `
        <tr>
          <td>${escapeHtml(item.description)}</td>
          <td>${item.quantity ?? ""}</td>
          <td>${item.unit ?? ""}</td>
          <td>${item.confidence ?? ""}</td>
        </tr>
      `
    )
    .join("");

  const evaluation = detail.evaluation_summary;
  $("evaluationList").innerHTML = `
    <dt>Matched Items</dt><dd>${evaluation.matched_items}</dd>
    <dt>Missing Items</dt><dd>${evaluation.missing_items.length}</dd>
    <dt>Extra Items</dt><dd>${evaluation.extra_items.length}</dd>
    <dt>Precision</dt><dd>${evaluation.precision}</dd>
    <dt>Recall</dt><dd>${evaluation.recall}</dd>
    <dt>Notes</dt><dd>${escapeHtml(evaluation.overall_notes)}</dd>
  `;
  $("evaluationCallout").textContent = detail.scored
    ? "Sample project: use this pane to understand current scoring gaps between baseline predictions and gold outputs."
    : "Challenge project: there is no visible gold output, so review quality depends on estimator correction and evidence inspection.";

  $("inputFilesList").innerHTML = detail.input_files_preview.map((path) => `<li>${escapeHtml(path)}</li>`).join("");
  populateReviewForm(detail.review_record);
  $("docReadme").textContent = detail.documents.readme;
  $("docArchitecture").textContent = detail.documents.architecture;
  $("docPacket").textContent = detail.documents.review_packet;
  $("docPlan").textContent = detail.documents.plan_30_day;
}

function populateReviewForm(record) {
  $("reviewStatus").value = record.status || "not_started";
  $("reviewerName").value = record.reviewer || "";
  $("reviewNotes").value = record.notes || "";
  $("correctedItems").value = JSON.stringify(record.corrected_items || [], null, 2);
  $("reviewSaveState").textContent = record.updated_at ? `Last saved ${record.updated_at}` : "";
}

async function handleReviewSave(event) {
  event.preventDefault();
  if (!state.selectedId) return;
  let correctedItems;
  try {
    correctedItems = JSON.parse($("correctedItems").value || "[]");
  } catch {
    $("reviewSaveState").textContent = "Corrected items must be valid JSON.";
    return;
  }

  $("reviewSaveState").textContent = "Saving review...";
  const payload = {
    status: $("reviewStatus").value,
    reviewer: $("reviewerName").value,
    notes: $("reviewNotes").value,
    corrected_items: correctedItems,
  };
  const saved = await api(`/api/reviews/${state.selectedId}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  const detail = state.projectDetails.get(state.selectedId);
  detail.review_record = saved;
  $("reviewSaveState").textContent = `Saved at ${saved.updated_at}`;
}

async function refreshWorkspace(selectFirst = false) {
  state.summary = await api("/api/summary");
  const projectsPayload = await api("/api/projects");
  state.projects = projectsPayload.projects;
  if (selectFirst || !state.projects.some((project) => project.takeoff_id === state.selectedId)) {
    state.selectedId = state.projects[0]?.takeoff_id ?? null;
  }
  state.projectDetails.clear();
  renderSummary();
  renderProjectList();
  await renderSelectedProject();
}

async function waitForBuildCompletion() {
  while (true) {
    const status = await api("/api/build-status");
    state.buildStatus = status;
    if (status.status === "running") {
      setBuildUiState(true, status.message || "Build running...");
      renderWorkspaceOverview();
      await sleep(1000);
      continue;
    }
    if (status.status === "failed") {
      throw new Error(status.error || status.message || "Build failed");
    }
    return status;
  }
}

async function handleRebuild() {
  const profile = getSelectedProfile();
  const config = getProfileConfig(profile);
  setBuildUiState(true, `Running ${config?.label || profile}...`);
  try {
    const response = await api("/api/build", { method: "POST", body: JSON.stringify({ profile }) });
    state.buildStatus = response.build_state;
    renderWorkspaceOverview();
    await waitForBuildCompletion();
    await refreshWorkspace(true);
    state.buildStatus = await api("/api/build-status");
    setBuildUiState(false, `Build complete: ${state.summary.profile_label}`);
  } catch (error) {
    setBuildUiState(false, `Build failed: ${error.message}`, true);
    renderWorkspaceOverview();
  }
}

function formatDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function bootstrap() {
  state.buildStatus = await api("/api/build-status");
  await refreshWorkspace(true);

  ["searchInput", "setFilter", "scoreFilter"].forEach((id) => {
    $(id).addEventListener("input", () => {
      renderProjectList();
      renderSelectedProject();
    });
    $(id).addEventListener("change", () => {
      renderProjectList();
      renderSelectedProject();
    });
  });

  $("buildProfile").addEventListener("change", () => {
    renderProfileMeta();
    renderWorkspaceOverview();
  });
  $("reviewForm").addEventListener("submit", handleReviewSave);
  $("rebuildButton").addEventListener("click", handleRebuild);
  if (state.buildStatus?.status === "running") {
    setBuildUiState(true, state.buildStatus.message || "Build running...");
  } else if (state.buildStatus?.status === "failed") {
    setBuildUiState(false, state.buildStatus.error || "Build failed", true);
  } else {
    setBuildUiState(false, $("commandStatus").textContent || "Ready");
  }
}

bootstrap().catch((error) => {
  $("workspaceTitle").textContent = "Application error";
  $("workspaceSubtitle").textContent = error.message;
  setBuildUiState(false, `Application error: ${error.message}`, true);
});
