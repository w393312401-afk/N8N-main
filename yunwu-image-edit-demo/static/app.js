const GPT_MODEL = "gpt-image-2-all";
const GEMINI_MODEL = "gemini-3.1-flash-image-preview";
const PROMPT_MAX_LENGTH = 2500;

const MASK_MAX_FILE_SIZE = 4 * 1024 * 1024;
const IMAGE_MAX_FILE_SIZE = 25 * 1024 * 1024;

const IMAGE_ALLOWED_ASPECT_RATIOS = [
  "1:1",
  "1:4",
  "4:1",
  "1:8",
  "8:1",
  "2:3",
  "3:2",
  "3:4",
  "4:3",
  "4:5",
  "5:4",
  "9:16",
  "16:9",
  "21:9",
];
const GPT_ALLOWED_ASPECT_RATIOS = new Set(IMAGE_ALLOWED_ASPECT_RATIOS);
const GEMINI_ALLOWED_ASPECT_RATIOS = new Set(IMAGE_ALLOWED_ASPECT_RATIOS);
const GEMINI_ALLOWED_IMAGE_SIZES = new Set(["512", "1K", "2K", "4K"]);
const VIDEO_ALLOWED_MODELS = new Set(["veo_3_1", "veo_3_1-fast"]);
const VIDEO_ALLOWED_SECONDS = new Set(["4", "8", "12"]);
const VIDEO_ALLOWED_SIZES = new Set(["16x9", "9x16", "1280x720", "720x1280"]);
const VIDEO_ALLOWED_WATERMARKS = new Set(["true", "false"]);
const TERMINAL_STATUSES = new Set(["completed", "failed"]);
const HISTORY_DRAG_TYPE = "application/x-yunwu-history-id";

const refs = {
  appShell: document.querySelector(".app-shell"),
  form: document.getElementById("image-form"),
  imageModelSection: document.getElementById("image-model-section"),
  model: document.getElementById("model"),
  modelRadios: Array.from(document.querySelectorAll('input[name="model-radio"]')),
  modelSummary: document.getElementById("model-summary"),
  prompt: document.getElementById("prompt"),
  promptHint: document.getElementById("prompt-hint"),
  promptCharCount: document.getElementById("prompt-char-count"),
  n: document.getElementById("n"),
  gptAspectRatio: document.getElementById("gpt-aspect-ratio"),
  aspectRatio: document.getElementById("aspect-ratio"),
  imageSize: document.getElementById("image-size"),
  videoFields: document.getElementById("video-fields"),
  videoModel: document.getElementById("video-model"),
  videoSeconds: document.getElementById("video-seconds"),
  videoSize: document.getElementById("video-size"),
  videoWatermark: document.getElementById("video-watermark"),
  videoEndCard: document.getElementById("video-end-card"),
  videoEndImage: document.getElementById("video-end-image"),
  videoEndPreview: document.getElementById("video-end-preview"),
  videoEndMeta: document.getElementById("video-end-meta"),
  videoEndHint: document.getElementById("video-end-hint"),
  image: document.getElementById("image"),
  mask: document.getElementById("mask"),
  imageCard: document.getElementById("image-card"),
  imageLabel: document.getElementById("image-label"),
  imagePreview: document.getElementById("image-preview"),
  maskPreview: document.getElementById("mask-preview"),
  imageMeta: document.getElementById("image-meta"),
  maskMeta: document.getElementById("mask-meta"),
  imageHint: document.getElementById("image-hint"),
  referenceHelper: document.getElementById("reference-helper"),
  maskCard: document.getElementById("mask-card"),
  gptFields: document.getElementById("gpt-fields"),
  geminiFields: document.getElementById("gemini-fields"),
  editFields: document.getElementById("edit-fields"),
  uploadEditFields: document.getElementById("upload-edit-fields"),
  healthBanner: document.getElementById("health-banner"),
  healthDot: document.getElementById("health-dot"),
  refreshHealth: document.getElementById("refresh-health"),
  keyPanel: document.getElementById("key-panel"),
  apiKeyInput: document.getElementById("api-key-input"),
  apiKeyPersist: document.getElementById("api-key-persist"),
  saveApiKey: document.getElementById("save-api-key"),
  apiKeyMessage: document.getElementById("api-key-message"),
  saveDirInput: document.getElementById("save-dir-input"),
  saveDirPersist: document.getElementById("save-dir-persist"),
  saveSaveDir: document.getElementById("save-save-dir"),
  saveDirMessage: document.getElementById("save-dir-message"),
  saveDirCurrent: document.getElementById("save-dir-current"),
  refreshHistory: document.getElementById("refresh-history"),
  formErrors: document.getElementById("form-errors"),
  submitButton: document.getElementById("submit-button"),
  submitLabel: document.getElementById("submit-label"),
  submitCopy: document.getElementById("submit-copy"),
  requestState: document.getElementById("request-state"),
  jobsList: document.getElementById("jobs-list"),
  jobsEmpty: document.getElementById("jobs-empty"),
  resultMessage: document.getElementById("result-message"),
  progressShell: document.getElementById("progress-shell"),
  progressMeta: document.getElementById("progress-meta"),
  resultGallery: document.getElementById("result-gallery"),
  savedPanel: document.getElementById("saved-panel"),
  savedSummary: document.getElementById("saved-summary"),
  savedList: document.getElementById("saved-list"),
  savedErrors: document.getElementById("saved-errors"),
  historyPanel: document.getElementById("history-panel"),
  historyList: document.getElementById("history-list"),
  historyEmpty: document.getElementById("history-empty"),
  historySummary: document.getElementById("history-summary"),
  rawPanel: document.getElementById("raw-panel"),
  rawOutput: document.getElementById("raw-output"),
  modeButtons: Array.from(document.querySelectorAll(".mode-button")),
};

const state = {
  model: refs.model.value || GEMINI_MODEL,
  mode: "generate",
  health: {
    ok: false,
    apiKeyConfigured: false,
    supportsApiKeyUpdate: false,
    supportsSaveDirUpdate: false,
    saveDir: "",
    message: "正在检查服务状态...",
    tone: "neutral",
  },
  imageMeta: null,
  videoEndMeta: null,
  maskMeta: null,
  imageHistorySourceId: null,
  videoEndHistorySourceId: null,
  fileErrors: {
    image: "",
    videoEnd: "",
    mask: "",
  },
  historyItems: [],
  saveDirDirty: false,
  selectedJobId: null,
  pendingSubmissions: 0,
  jobs: new Map(),
  trackers: new Map(),
};

document.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  setupImageDropTarget();
  applyModelUI();
  applyModeUI();
  syncPromptCounter();
  syncReferenceCardState();
  setApiKeyMessage("更新后会立刻作用于当前 Yunwu 请求。", "neutral");
  setSaveDirMessage("路径更新后，新任务会自动落盘到该目录。", "neutral");
  refreshHealth();
  refreshHistory();
  renderJobsPanel();
  renderSelectedJob();
  updateFormState();
  window.addEventListener("beforeunload", closeAllJobTracking);
});

function bindEvents() {
  refs.model.addEventListener("change", () => {
    state.model = refs.model.value;
    applyModelUI();
    updateFormState();
  });

  refs.modelRadios.forEach((radio) => {
    radio.addEventListener("change", () => {
      if (!radio.checked) {
        return;
      }
      refs.model.value = radio.value;
      state.model = radio.value;
      applyModelUI();
      updateFormState();
    });
  });

  refs.prompt.addEventListener("input", updateFormState);
  refs.n.addEventListener("input", updateFormState);
  refs.gptAspectRatio.addEventListener("change", updateFormState);
  refs.aspectRatio.addEventListener("change", updateFormState);
  refs.imageSize.addEventListener("change", updateFormState);
  refs.videoModel.addEventListener("change", updateFormState);
  refs.videoSeconds.addEventListener("change", updateFormState);
  refs.videoSize.addEventListener("change", updateFormState);
  refs.videoWatermark.addEventListener("change", updateFormState);

  refs.image.addEventListener("change", () => handleFileChange("image"));
  refs.videoEndImage.addEventListener("change", () => handleFileChange("videoEnd"));
  refs.mask.addEventListener("change", () => handleFileChange("mask"));

  refs.refreshHealth.addEventListener("click", refreshHealth);
  refs.refreshHistory.addEventListener("click", refreshHistory);
  refs.saveApiKey.addEventListener("click", handleApiKeySave);
  refs.saveSaveDir.addEventListener("click", handleSaveDirSave);
  refs.saveDirInput.addEventListener("input", () => {
    state.saveDirDirty = true;
  });

  refs.form.addEventListener("submit", handleSubmit);

  refs.modeButtons.forEach((button) => {
    button.addEventListener("click", () => {
      state.mode = button.dataset.mode;
      applyModeUI();
      updateFormState();
    });
  });
}

async function refreshHealth() {
  setHealthBanner("正在检查服务状态...", "neutral");
  setHealthDot("neutral");

  try {
    const response = await fetch("/api/health", { cache: "no-store" });
    const payload = await response.json();

    state.health.ok = Boolean(response.ok && payload.ok);
    state.health.apiKeyConfigured = Boolean(payload.apiKeyConfigured);
    state.health.supportsApiKeyUpdate = Boolean(payload.supportsApiKeyUpdate);
    state.health.supportsSaveDirUpdate = Boolean(payload.supportsSaveDirUpdate);
    state.health.saveDir = typeof payload.saveDir === "string" ? payload.saveDir : "";

    if (!state.health.ok) {
      state.health.message = "后端服务状态异常。";
      state.health.tone = "error";
    } else if (!state.health.apiKeyConfigured) {
      state.health.message = "服务已启动，但尚未配置 API Key，当前不能提交请求。";
      state.health.tone = "warning";
    } else {
      state.health.message = "服务可用，且已检测到 API Key。";
      state.health.tone = "success";
    }
  } catch (error) {
    state.health.ok = false;
    state.health.apiKeyConfigured = false;
    state.health.supportsApiKeyUpdate = false;
    state.health.supportsSaveDirUpdate = false;
    state.health.saveDir = "";
    state.health.message = "无法连接本地服务，请确认启动器或 uvicorn 已运行。";
    state.health.tone = "error";
  }

  syncHealthToSettings();
  setHealthBanner(state.health.message, state.health.tone);
  setHealthDot(state.health.tone);
  updateFormState();
}

function syncHealthToSettings() {
  const saveDir = state.health.saveDir || "未获取到保存路径";
  refs.saveDirCurrent.textContent = saveDir;

  if (!state.saveDirDirty || !refs.saveDirInput.value.trim()) {
    refs.saveDirInput.value = state.health.saveDir || "";
    state.saveDirDirty = false;
  }
}

function isGptModel(model) {
  return model === GPT_MODEL;
}

function isGeminiModel(model) {
  return model === GEMINI_MODEL;
}

function getPromptLimit(model) {
  return PROMPT_MAX_LENGTH;
}

function getModelLabel(model) {
  if (VIDEO_ALLOWED_MODELS.has(model)) {
    return model;
  }
  if (isGptModel(model)) {
    return "Yunwu gpt-image-2-all";
  }
  return "Gemini 3.1";
}

function isVideoMode() {
  return state.mode === "video";
}

function getModeLabel(mode) {
  if (mode === "edit") {
    return "图生图";
  }
  if (mode === "video") {
    return "视频";
  }
  return "文生图";
}

function getActiveModel() {
  return isVideoMode() ? refs.videoModel.value : state.model;
}

function getPromptPlaceholder() {
  if (isVideoMode()) {
    return "描述镜头运动、主体动作和气氛。0 图时按文生视频，1 图时按首帧/参考图，2 图时按首尾帧推断。";
  }
  if (state.mode === "edit") {
    return "明确保留什么、替换什么，例如：保留主体结构和机位，把场景改成晨雾森林，加入柔和体积光和电影级空气感。";
  }
  return "描述你想生成的图像，例如：晨雾森林中的古塔，青绿色氛围，体积光，细腻材质，电影级质感。";
}

function getSubmitLabel() {
  if (isVideoMode()) {
    if (refs.videoEndImage.files[0]) {
      return "提交首尾帧视频";
    }
    if (refs.image.files[0]) {
      return "提交图生视频";
    }
    return "提交文生视频";
  }
  if (state.mode === "edit") {
    return "提交图生图";
  }
  return "提交文生图";
}

function syncPromptCounter() {
  const limit = getPromptLimit(state.model);
  const length = refs.prompt.value.length;
  refs.promptCharCount.textContent = `${length} / ${limit}`;
  refs.promptCharCount.classList.toggle("is-near-limit", length >= Math.floor(limit * 0.85));
}

function syncShellContext() {
  if (!refs.appShell) {
    return;
  }
  refs.appShell.dataset.mode = state.mode;
  if (isVideoMode()) {
    refs.appShell.dataset.model = "video";
    return;
  }
  refs.appShell.dataset.model = isGptModel(state.model) ? "gpt" : "gemini";
}

function syncReferenceCardState() {
  refs.imageCard.classList.toggle("is-history-linked", Boolean(state.imageHistorySourceId));
  if (refs.videoEndCard) {
    refs.videoEndCard.classList.toggle("is-history-linked", Boolean(state.videoEndHistorySourceId));
  }
}

function createPreviewPlaceholder(kind) {
  const wrapper = document.createElement("span");
  wrapper.className = "preview-placeholder";

  const icon = document.createElement("span");
  icon.className = "preview-icon";
  if (kind === "image") {
    icon.textContent = "🖼";
  } else if (kind === "videoEnd") {
    icon.textContent = "🎬";
  } else {
    icon.textContent = "◻";
  }

  const text = document.createElement("span");
  if (kind === "image") {
    text.innerHTML = "拖入历史图<br/>或点击选择";
  } else if (kind === "videoEnd") {
    text.innerHTML = "拖入历史图<br/>或点击选择尾帧";
  } else {
    text.innerHTML = "点击选择蒙版";
  }

  wrapper.appendChild(icon);
  wrapper.appendChild(text);
  return wrapper;
}

function setHealthDot(tone) {
  refs.healthDot.className = `health-dot is-${tone}`;
}

function getSortedJobs() {
  return Array.from(state.jobs.values()).sort(
    (left, right) => (right.snapshot?.created_at || 0) - (left.snapshot?.created_at || 0),
  );
}

function getInFlightJobCount() {
  let count = state.pendingSubmissions;
  state.jobs.forEach((entry) => {
    if (!TERMINAL_STATUSES.has(entry.snapshot.status)) {
      count += 1;
    }
  });
  return count;
}

function jobTone(status) {
  if (status === "completed") {
    return "success";
  }
  if (status === "failed") {
    return "error";
  }
  if (status === "queued" || status === "running") {
    return "warning";
  }
  return "neutral";
}

function rememberJob(snapshot, meta = null) {
  const existing = state.jobs.get(snapshot.job_id);
  const previousStatus = existing?.snapshot?.status || "";
  const nextEntry = {
    snapshot,
    meta: meta || existing?.meta || {},
  };
  state.jobs.set(snapshot.job_id, nextEntry);
  renderJobsPanel();

  if (!state.selectedJobId) {
    state.selectedJobId = snapshot.job_id;
  }
  if (state.selectedJobId === snapshot.job_id) {
    renderSelectedJob();
  }
  if (snapshot.status === "completed" && previousStatus !== "completed") {
    refreshHistory();
  }
  updateFormState();
}

function selectJob(jobId) {
  if (!state.jobs.has(jobId)) {
    return;
  }
  state.selectedJobId = jobId;
  renderJobsPanel();
  renderSelectedJob();
}

function renderJobsPanel() {
  refs.jobsList.innerHTML = "";
  const jobs = getSortedJobs();

  if (!jobs.length) {
    refs.jobsEmpty.hidden = false;
    refs.jobsEmpty.textContent = state.pendingSubmissions > 0 ? "正在创建任务..." : "暂无任务。";
    return;
  }

  refs.jobsEmpty.hidden = true;

  jobs.forEach((entry) => {
    const { snapshot, meta } = entry;
    const card = document.createElement("button");
    card.type = "button";
    card.className = "job-card";
    if (snapshot.job_id === state.selectedJobId) {
      card.classList.add("is-selected");
    }
    card.addEventListener("click", () => {
      selectJob(snapshot.job_id);
    });

    const head = document.createElement("div");
    head.className = "job-card-head";

    const title = document.createElement("p");
    title.className = "job-card-title";
    title.textContent =
      meta.prompt ||
      `${getModeLabel(meta.mode)}任务`;

    const status = document.createElement("span");
    status.className = `status-pill status-${jobTone(snapshot.status)}`;
    status.textContent =
      snapshot.status === "completed"
        ? "已完成"
        : snapshot.status === "failed"
          ? "失败"
          : snapshot.status === "running"
            ? "进行中"
            : "已受理";

    head.appendChild(title);
    head.appendChild(status);

    const metaText = document.createElement("div");
    metaText.className = "job-card-meta";
    const chunks = [];
    if (meta.model) {
      chunks.push(meta.model);
    }
    if (meta.mode) {
      chunks.push(getModeLabel(meta.mode));
    }
    chunks.push(phaseToLabel(snapshot.phase));
    chunks.push(`${((snapshot.elapsed_ms || 0) / 1000).toFixed(1)} 秒`);
    metaText.textContent = chunks.join(" · ");

    const message = document.createElement("div");
    message.className = "job-card-message";
    message.textContent = snapshot.message || "等待状态更新。";

    const id = document.createElement("div");
    id.className = "job-card-id";
    id.textContent = `job: ${snapshot.job_id.slice(0, 12)}`;

    card.appendChild(head);
    card.appendChild(metaText);
    card.appendChild(message);
    card.appendChild(id);
    refs.jobsList.appendChild(card);
  });
}

function clearResultDetail() {
  setProgressVisible(false);
  setProgressMeta("");
  renderGallery([]);
  renderSavedFiles({ saves: [], errors: [], saveDir: "" });
  setRawResponse(null);
}

function renderSelectedJob() {
  const entry = state.selectedJobId ? state.jobs.get(state.selectedJobId) : null;
  const inFlightCount = getInFlightJobCount();

  if (!entry) {
    setRequestState(inFlightCount > 0 ? `并发中 ${inFlightCount}` : "等待提交", inFlightCount > 0 ? "warning" : "neutral");
    setResultMessage(
      inFlightCount > 0
        ? "任务已在后台并发处理。点击上方任务卡可切换查看。"
        : "提交后，这里会显示结果或错误信息。",
      "neutral",
    );
    clearResultDetail();
    return;
  }

  const snapshot = entry.snapshot;
  const seconds = ((snapshot.elapsed_ms || 0) / 1000).toFixed(1);
  const phaseLabel = phaseToLabel(snapshot.phase);
  setProgressVisible(!TERMINAL_STATUSES.has(snapshot.status));
  setProgressMeta(`阶段：${phaseLabel} · 已耗时 ${seconds} 秒`);

  if (snapshot.status === "queued") {
    setRequestState("已提交", "warning");
    setResultMessage(snapshot.message || "任务已受理，等待发送到上游。", "neutral");
    renderGallery([]);
    renderSavedFiles({ saves: [], errors: [], saveDir: "" });
    setRawResponse(null);
    return;
  }

  if (snapshot.status === "running") {
    setRequestState("进行中", "warning");
    setResultMessage(snapshot.message || "请求已发送到上游，正在等待结果。", "neutral");
    renderGallery([]);
    renderSavedFiles({ saves: [], errors: [], saveDir: "" });
    setRawResponse(null);
    return;
  }

  if (snapshot.status === "completed") {
    const result = snapshot.result || {};
    const previewItems = extractPreviewItems(result);
    const savedInfo = extractSavedInfo(result);

    setRequestState("请求成功", "success");
    setResultMessage(buildSuccessMessage(snapshot, previewItems, savedInfo, seconds), previewItems.length ? "success" : "warning");
    renderGallery(previewItems);
    renderSavedFiles(savedInfo);
    setRawResponse(result);
    return;
  }

  if (snapshot.status === "failed") {
    const error = snapshot.error || {};
    setRequestState("请求失败", "error");
    setResultMessage(error.message || snapshot.message || "请求失败。", "error");
    renderGallery([]);
    renderSavedFiles({ saves: [], errors: [], saveDir: "" });
    setRawResponse({ error });
  }
}

async function refreshHistory() {
  try {
    const response = await fetch("/api/history?limit=24", { cache: "no-store" });
    const payload = await response.json();
    state.historyItems = Array.isArray(payload.items) ? payload.items : [];
    renderHistory();
  } catch (error) {
    state.historyItems = [];
    renderHistory("加载历史记录失败。");
  }
}

function renderHistory(errorMessage = "") {
  refs.historyList.innerHTML = "";
  const visibleItems = state.historyItems.filter((item) => (item.is_image || item.is_video) && item.preview_url);

  if (errorMessage) {
    refs.historyEmpty.hidden = false;
    refs.historyEmpty.textContent = errorMessage;
    refs.historySummary.textContent = "历史记录不可用。";
    return;
  }

  if (!visibleItems.length) {
    refs.historyEmpty.hidden = false;
    refs.historyEmpty.textContent = "暂无历史媒体记录。";
    refs.historySummary.textContent = "最近 24 条媒体记录为空，总生成时长 0 秒。";
    return;
  }

  refs.historyEmpty.hidden = true;
  refs.historySummary.textContent = buildHistorySummary(visibleItems);

  visibleItems.forEach((item) => {
    const card = document.createElement("article");
    card.className = "history-card";
    if (item.is_image) {
      card.classList.add("is-draggable");
      card.draggable = true;
    }
    card.title = item.name || "历史媒体";
    if (item.is_image) {
      card.addEventListener("dragstart", (event) => {
        event.dataTransfer.effectAllowed = "copy";
        event.dataTransfer.setData(HISTORY_DRAG_TYPE, item.id);
      });
    }

    const media = document.createElement("div");
    media.className = "history-thumb";
    media.title = item.name || "历史媒体";
    if (item.is_image) {
      media.addEventListener("click", () => {
        void applyHistoryItemToImage(item.id);
      });

      const image = document.createElement("img");
      image.src = item.preview_url;
      image.alt = item.name || "历史图片";
      image.draggable = false;
      media.appendChild(image);
    } else if (item.is_video) {
      const video = document.createElement("video");
      video.src = item.preview_url;
      video.muted = true;
      video.playsInline = true;
      video.preload = "metadata";
      video.controls = false;
      video.draggable = false;
      media.appendChild(video);
    }

    const kindBadge = document.createElement("span");
    kindBadge.className = "history-kind";
    kindBadge.textContent = item.is_video ? "视频" : "图片";

    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "history-delete";
    deleteButton.textContent = "删除";
    deleteButton.draggable = false;
    deleteButton.title = item.name ? `删除 ${item.name}` : "删除历史媒体";
    ["pointerdown", "mousedown", "touchstart"].forEach((eventName) => {
      deleteButton.addEventListener(eventName, (event) => {
        event.stopPropagation();
      });
    });
    deleteButton.addEventListener("dragstart", (event) => {
      event.preventDefault();
      event.stopPropagation();
    });
    deleteButton.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      await deleteHistoryItem(item.id);
    });

    card.appendChild(media);
    card.appendChild(kindBadge);
    card.appendChild(deleteButton);
    refs.historyList.appendChild(card);
  });
}

function buildHistorySummary(items) {
  const uniqueBatches = new Set();
  let totalElapsedMs = 0;
  let imageCount = 0;
  let videoCount = 0;

  items.forEach((item) => {
    if (item.is_video) {
      videoCount += 1;
    } else if (item.is_image) {
      imageCount += 1;
    }
    const batchId = typeof item.batch_id === "string" && item.batch_id ? item.batch_id : item.id;
    if (uniqueBatches.has(batchId)) {
      return;
    }
    uniqueBatches.add(batchId);
    totalElapsedMs += Math.max(Number(item.elapsed_ms || 0), 0);
  });

  return `最近 ${items.length} 条媒体记录（图片 ${imageCount} / 视频 ${videoCount}），来自 ${uniqueBatches.size} 次生成，总生成时长 ${formatDuration(totalElapsedMs)}。`;
}

async function deleteHistoryItem(historyId) {
  try {
    const response = await fetch(`/api/history/${historyId}`, {
      method: "DELETE",
      headers: {
        Accept: "application/json",
      },
    });
    let payload = null;
    try {
      payload = await response.json();
    } catch (error) {
      payload = null;
    }

    if (!response.ok || payload?.error || payload?.ok === false) {
      if (response.status === 404 || response.status === 405) {
        setResultMessage("当前运行的本地服务还是旧版本，不支持历史删除。先重启启动器。", "error");
        return;
      }
      const message = extractApiErrorMessage(payload, "删除历史记录失败。");
      setResultMessage(message, "error");
      return;
    }

    const clearedReference = state.imageHistorySourceId === historyId;
    const clearedVideoEnd = state.videoEndHistorySourceId === historyId;
    state.historyItems = state.historyItems.filter((item) => item.id !== historyId);
    if (clearedReference) {
      clearReferenceInputs();
    } else if (clearedVideoEnd) {
      clearSingleInput("videoEnd");
      syncReferenceCardState();
      updateFormState();
    }
    renderHistory();
    const suffix = clearedReference ? " 当前首帧、尾帧和蒙版也已清空。" : clearedVideoEnd ? " 当前尾帧已清空。" : "";
    setResultMessage(`${payload.message || "历史记录已删除，本地文件保留。"}${suffix}`, "success");
  } catch (error) {
    setResultMessage("删除历史记录失败，请检查本地服务。", "error");
  }
}

function clearSingleInput(kind) {
  const input =
    kind === "image" ? refs.image :
    kind === "videoEnd" ? refs.videoEndImage :
    refs.mask;

  if (input) {
    input.value = "";
  }

  if (kind === "image") {
    state.fileErrors.image = "";
    state.imageHistorySourceId = null;
  } else if (kind === "videoEnd") {
    state.fileErrors.videoEnd = "";
    state.videoEndHistorySourceId = null;
  } else {
    state.fileErrors.mask = "";
  }

  setFileMeta(kind, null);
  renderPreview(kind, null);
}

function clearReferenceInputs() {
  clearSingleInput("image");
  clearSingleInput("videoEnd");
  clearSingleInput("mask");
  syncReferenceCardState();
  updateFormState();
}

function setupImageDropTarget() {
  setupHistoryDropTarget(refs.imageCard, "image");
  setupHistoryDropTarget(refs.videoEndCard, "videoEnd");
}

function setupHistoryDropTarget(target, kind) {
  if (!target) {
    return;
  }

  ["dragenter", "dragover"].forEach((eventName) => {
    target.addEventListener(eventName, (event) => {
      const historyId = event.dataTransfer?.getData(HISTORY_DRAG_TYPE);
      if (!historyId) {
        return;
      }
      event.preventDefault();
      target.classList.add("is-drop-target");
    });
  });

  target.addEventListener("dragleave", () => {
    target.classList.remove("is-drop-target");
  });

  target.addEventListener("drop", async (event) => {
    const historyId = event.dataTransfer?.getData(HISTORY_DRAG_TYPE);
    target.classList.remove("is-drop-target");
    if (!historyId) {
      return;
    }
    event.preventDefault();
    await applyHistoryItemToImage(historyId, kind);
  });
}

async function applyHistoryItemToImage(historyId, targetKind = "image") {
  const item = state.historyItems.find((entry) => entry.id === historyId);
  const targetLabel = targetKind === "videoEnd" ? "视频尾帧" : isVideoMode() ? "视频首帧 / 垫图" : "图生图参考图";
  if (!item || !item.is_image || !item.file_url) {
    setResultMessage(`这条历史记录不是可用图片，不能填入${targetLabel}。`, "error");
    return;
  }

  try {
    const response = await fetch(item.file_url, { cache: "no-store" });
    if (!response.ok) {
      throw new Error("history-file-fetch-failed");
    }

    const blob = await response.blob();
    const file = new File([blob], item.name || `history-${historyId}.png`, {
      type: blob.type || item.mime_type || "application/octet-stream",
    });

    const dataTransfer = new DataTransfer();
    dataTransfer.items.add(file);
    const input = targetKind === "videoEnd" ? refs.videoEndImage : refs.image;
    const card = targetKind === "videoEnd" ? refs.videoEndCard : refs.imageCard;
    input.files = dataTransfer.files;

    if (targetKind === "image" && state.mode === "generate") {
      state.mode = "edit";
      applyModeUI();
    }

    await handleFileChange(targetKind);

    if (targetKind === "videoEnd") {
      state.videoEndHistorySourceId = refs.videoEndImage.files[0] && state.videoEndMeta ? historyId : null;
      if (state.videoEndMeta) {
        renderPreview("videoEnd", state.videoEndMeta);
      }
    } else {
      state.imageHistorySourceId = refs.image.files[0] && state.imageMeta ? historyId : null;
      if (state.imageMeta) {
        renderPreview("image", state.imageMeta);
      }
    }

    syncReferenceCardState();
    card.scrollIntoView({ behavior: "smooth", block: "center" });
    const successLabel = targetKind === "videoEnd" ? "视频尾帧" : isVideoMode() ? "视频首帧 / 垫图" : "图生图参考图";
    setResultMessage(`历史图片已填入${successLabel}。`, "success");
  } catch (error) {
    setResultMessage("读取历史图片失败，请刷新历史记录后重试。", "error");
  }
}

function applyModelUI() {
  const isVideo = isVideoMode();
  const isGpt = isGptModel(state.model);
  const isGemini = isGeminiModel(state.model);

  refs.prompt.maxLength = String(getPromptLimit(state.model));
  refs.prompt.placeholder = getPromptPlaceholder();
  refs.imageModelSection.hidden = isVideo;
  refs.videoFields.hidden = !isVideo;

  if (isVideo) {
    refs.promptHint.textContent = `必填，最大 ${getPromptLimit(state.model)} 个字符。动作、镜头和气氛写清楚，时长和画幅不要塞进提示词。`;
    refs.gptFields.hidden = true;
    refs.geminiFields.hidden = true;
    refs.editFields.hidden = false;
    refs.uploadEditFields.hidden = false;
    refs.videoEndCard.hidden = false;
    refs.maskCard.hidden = true;
    refs.imageLabel.textContent = "首帧 / 参考图";
    refs.imageHint.textContent = "可不传。0 图走文生视频，1 图走首帧 / 参考图模式，支持 PNG / JPG / WEBP，最大 25 MB。";
    refs.videoEndHint.textContent = "可选。上传后会按首尾帧模式推断提交；尾帧不能单独存在。";
    refs.referenceHelper.textContent = "历史图片可点击回填首帧，也可直接拖到“首帧 / 参考图”或“尾帧”卡片。";
    refs.modelSummary.textContent =
      "当前工作流：视频。0 图文生，1 图首帧 / 参考图，2 图首尾帧；本地代理会按兼容请求形态自动回退，再轮询并下载成片。";
    state.fileErrors.mask = "";
    syncPromptCounter();
    syncShellContext();
    return;
  }

  refs.modelRadios.forEach((radio) => {
    radio.checked = radio.value === state.model;
  });
  refs.promptHint.textContent = `必填，最大 ${getPromptLimit(state.model)} 个字符。尺寸和比例走参数区，不要重复写进提示词。`;

  refs.gptFields.hidden = !isGpt;
  refs.geminiFields.hidden = !isGemini;
  refs.editFields.hidden = state.mode === "generate";
  refs.uploadEditFields.hidden = state.mode === "generate";
  refs.videoEndCard.hidden = true;
  refs.maskCard.hidden = !isGpt || state.mode !== "edit";
  refs.imageLabel.textContent = "参考图";
  refs.referenceHelper.textContent = "右侧历史图可直接拖入“参考图”卡片，少做重复上传。";

  if (isGpt) {
    refs.modelSummary.textContent =
      "当前模型：gpt-image-2-all。比例选项已与 Gemini 对齐，默认 9:16；提交时会优先携带 aspect_ratio。";
    refs.imageHint.textContent = "gpt-image-2-all 图生图必须上传参考图；当前 GPT 比例已与 Gemini 保持一致。";
  } else {
    refs.modelSummary.textContent =
      "当前模型：gemini-3.1-flash-image-preview。适合快速试图、参考图驱动和比例探索；如果上游提示当前分组无可用渠道，就切回 GPT Image。";
    refs.imageHint.textContent = "Gemini 图生图必填。当前界面先支持单张参考图，并会作为 inline_data 发送。";
  }

  if (!isGpt) {
    state.fileErrors.mask = "";
  }

  syncPromptCounter();
  syncShellContext();
}

function applyModeUI() {
  refs.modeButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.mode === state.mode);
  });

  refs.submitLabel.textContent = getSubmitLabel();
  applyModelUI();
}

async function handleApiKeySave() {
  if (!state.health.supportsApiKeyUpdate) {
    setApiKeyMessage("当前运行的是旧后端，不支持在线改密钥。先关闭本地服务，再重新启动。", "error");
    return;
  }

  const apiKey = refs.apiKeyInput.value.trim();
  if (!apiKey) {
    setApiKeyMessage("新密钥不能为空。", "error");
    return;
  }

  refs.saveApiKey.disabled = true;
  setApiKeyMessage("正在保存新密钥...", "neutral");

  try {
    const response = await fetch("/api/settings/api-key", {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        api_key: apiKey,
        persist: refs.apiKeyPersist.checked,
      }),
    });
    const payload = await response.json();

    if (!response.ok || payload.error) {
      const message = extractApiErrorMessage(payload, "保存新密钥失败。");
      setApiKeyMessage(message, "error");
      return;
    }

    refs.apiKeyInput.value = "";
    setApiKeyMessage(payload.message || "API Key 已更新。", "success");
    await refreshHealth();
  } catch (error) {
    setApiKeyMessage("保存新密钥失败，请检查本地服务。", "error");
  } finally {
    refs.saveApiKey.disabled = false;
  }
}

async function handleSaveDirSave() {
  if (!state.health.supportsSaveDirUpdate) {
    setSaveDirMessage("当前运行的是旧后端，不支持在线改保存路径。先关闭本地服务，再重新启动。", "error");
    return;
  }

  const saveDir = refs.saveDirInput.value.trim();
  if (!saveDir) {
    setSaveDirMessage("保存路径不能为空。", "error");
    return;
  }

  refs.saveSaveDir.disabled = true;
  setSaveDirMessage("正在保存路径...", "neutral");

  try {
    const response = await fetch("/api/settings/save-dir", {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        save_dir: saveDir,
        persist: refs.saveDirPersist.checked,
      }),
    });
    const payload = await response.json();

    if (!response.ok || payload.error) {
      const message = extractApiErrorMessage(payload, "保存路径失败。");
      setSaveDirMessage(message, "error");
      return;
    }

    state.saveDirDirty = false;
    setSaveDirMessage(payload.message || "保存路径已更新。", "success");
    await refreshHealth();
  } catch (error) {
    setSaveDirMessage("保存路径失败，请检查本地服务。", "error");
  } finally {
    refs.saveSaveDir.disabled = false;
  }
}

async function handleFileChange(kind) {
  const input =
    kind === "image" ? refs.image :
    kind === "videoEnd" ? refs.videoEndImage :
    refs.mask;
  const file = input.files[0];

  if (kind === "image") {
    state.imageHistorySourceId = null;
  } else if (kind === "videoEnd") {
    state.videoEndHistorySourceId = null;
  }
  state.fileErrors[kind] = "";
  setFileMeta(kind, null);
  renderPreview(kind, null);

  if (!file) {
    updateFormState();
    return;
  }

  const basicError = validateBasicFile(kind, file);
  if (basicError) {
    state.fileErrors[kind] = basicError;
    input.value = "";
    updateFormState();
    return;
  }

  try {
    const meta = await loadImageMeta(file);

    if (kind === "mask" && state.imageMeta) {
      const sameSize =
        meta.width === state.imageMeta.width &&
        meta.height === state.imageMeta.height;
      if (!sameSize) {
        state.fileErrors.mask = "蒙版尺寸必须与参考图完全一致。";
        input.value = "";
        URL.revokeObjectURL(meta.objectUrl);
        updateFormState();
        return;
      }
    }

    if (kind === "image" && state.maskMeta && state.model === GPT_MODEL) {
      const sameSize =
        meta.width === state.maskMeta.width &&
        meta.height === state.maskMeta.height;
      state.fileErrors.mask = sameSize ? "" : "蒙版尺寸必须与参考图完全一致。";
    }

    setFileMeta(kind, meta);
    renderPreview(kind, meta);
  } catch (error) {
    const label =
      kind === "image" ? (isVideoMode() ? "首帧 / 垫图" : "参考图") :
      kind === "videoEnd" ? "尾帧" :
      "蒙版";
    state.fileErrors[kind] = `无法读取该${label}文件，请更换文件后重试。`;
    input.value = "";
  }

  syncReferenceCardState();
  updateFormState();
}

function validateBasicFile(kind, file) {
  const lowerName = file.name.toLowerCase();
  const isImage = /\.(png|jpg|jpeg|webp)$/.test(lowerName);
  const isPng = file.type === "image/png" || lowerName.endsWith(".png");

  if (kind === "image" || kind === "videoEnd") {
    const label =
      kind === "videoEnd" ? "尾帧" :
      isVideoMode() ? "首帧 / 垫图" :
      "参考图";
    if (!isImage) {
      return `${label}只支持 PNG、JPG、JPEG、WEBP。`;
    }
    if (file.size >= IMAGE_MAX_FILE_SIZE) {
      return `${label}必须小于 25MB。`;
    }
    return "";
  }

  if (!isPng) {
    return "蒙版只支持 PNG。";
  }
  if (file.size >= MASK_MAX_FILE_SIZE) {
    return "蒙版必须小于 4MB。";
  }
  return "";
}

function loadImageMeta(file) {
  const objectUrl = URL.createObjectURL(file);
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => {
      resolve({
        file,
        objectUrl,
        width: image.naturalWidth,
        height: image.naturalHeight,
      });
    };
    image.onerror = () => {
      URL.revokeObjectURL(objectUrl);
      reject(new Error("image-load-failed"));
    };
    image.src = objectUrl;
  });
}

function setFileMeta(kind, nextMeta) {
  const key =
    kind === "image" ? "imageMeta" :
    kind === "videoEnd" ? "videoEndMeta" :
    "maskMeta";
  const previous = state[key];
  if (previous && previous.objectUrl && previous.objectUrl !== nextMeta?.objectUrl) {
    URL.revokeObjectURL(previous.objectUrl);
  }
  state[key] = nextMeta;
}

function renderPreview(kind, meta) {
  const preview =
    kind === "image" ? refs.imagePreview :
    kind === "videoEnd" ? refs.videoEndPreview :
    refs.maskPreview;
  const metaText =
    kind === "image" ? refs.imageMeta :
    kind === "videoEnd" ? refs.videoEndMeta :
    refs.maskMeta;
  preview.innerHTML = "";

  if (!meta) {
    preview.appendChild(createPreviewPlaceholder(kind));
    metaText.textContent = "";
    return;
  }

  const image = document.createElement("img");
  image.src = meta.objectUrl;
  image.alt =
    kind === "image" ? (isVideoMode() ? "视频首帧预览" : "参考图预览") :
    kind === "videoEnd" ? "视频尾帧预览" :
    "蒙版预览";
  preview.appendChild(image);
  const chunks = [`${meta.width} × ${meta.height}`, formatBytes(meta.file.size)];
  if (kind === "image" && state.imageHistorySourceId) {
    chunks.push("来自历史记录");
  }
  if (kind === "videoEnd" && state.videoEndHistorySourceId) {
    chunks.push("来自历史记录");
  }
  metaText.textContent = chunks.join(" · ");
}

function updateFormState() {
  syncPromptCounter();
  syncReferenceCardState();
  refs.submitLabel.textContent = getSubmitLabel();
  const errors = collectFormErrors();
  renderFormErrors(errors);
  refs.submitButton.disabled = errors.length > 0;

  if (errors.length > 0) {
    refs.submitCopy.textContent = "先把上面的校验问题修掉，再提交。";
    return;
  }

  if (state.pendingSubmissions > 0) {
    refs.submitCopy.textContent = `正在创建 ${state.pendingSubmissions} 个任务；已支持并发，可继续提交。`;
    return;
  }

  const inFlightCount = getInFlightJobCount();
  if (inFlightCount > 0) {
    refs.submitCopy.textContent = `当前有 ${inFlightCount} 个任务在后台处理；已支持并发，可继续提交。`;
    return;
  }

  const modelLabel = getModelLabel(getActiveModel());
  const modeLabel = getModeLabel(state.mode);
  refs.submitCopy.textContent = `${modelLabel} ${modeLabel} 参数校验通过，可以提交。`;
}

function collectFormErrors() {
  const errors = [];
  const activeModel = getActiveModel();

  if (!state.health.ok) {
    errors.push(state.health.message);
  } else if (!state.health.apiKeyConfigured) {
    errors.push("后端未配置 API Key，当前无法提交。");
  }

  const prompt = refs.prompt.value.trim();
  if (!prompt) {
    errors.push("请输入提示词。");
  } else if (prompt.length > getPromptLimit(activeModel)) {
    errors.push(`提示词长度不能超过 ${getPromptLimit(activeModel)} 个字符。`);
  }

  if (isVideoMode()) {
    if (!VIDEO_ALLOWED_MODELS.has(refs.videoModel.value)) {
      errors.push("视频 model 取值不合法。");
    }
    if (!VIDEO_ALLOWED_SECONDS.has(refs.videoSeconds.value)) {
      errors.push("seconds 取值不合法。");
    }
    if (!VIDEO_ALLOWED_SIZES.has(refs.videoSize.value)) {
      errors.push("视频 size 取值不合法。");
    }
    if (!VIDEO_ALLOWED_WATERMARKS.has(refs.videoWatermark.value)) {
      errors.push("watermark 取值不合法。");
    }
    if (state.fileErrors.image) {
      errors.push(state.fileErrors.image);
    }
    if (state.fileErrors.videoEnd) {
      errors.push(state.fileErrors.videoEnd);
    }
    if (refs.videoEndImage.files[0] && (!refs.image.files[0] || !state.imageMeta)) {
      errors.push("尾帧不能单独上传，至少先给首帧。");
    }
    return [...new Set(errors)];
  }

  if (isGptModel(state.model)) {
    const n = Number(refs.n.value);
    if (!Number.isInteger(n) || n < 1 || n > 10) {
      errors.push("n 必须是 1 到 10 的整数。");
    }
    if (!GPT_ALLOWED_ASPECT_RATIOS.has(refs.gptAspectRatio.value)) {
      errors.push("GPT aspect_ratio 取值不合法。");
    }
  } else {
    if (!GEMINI_ALLOWED_ASPECT_RATIOS.has(refs.aspectRatio.value)) {
      errors.push("aspectRatio 取值不合法。");
    }
    if (!GEMINI_ALLOWED_IMAGE_SIZES.has(refs.imageSize.value)) {
      errors.push("imageSize 取值不合法。");
    }
  }

  if (state.mode === "edit") {
    if (state.fileErrors.image) {
      errors.push(state.fileErrors.image);
    } else if (!refs.image.files[0] || !state.imageMeta) {
      errors.push("图生图模式必须上传参考图。");
    }

    if (isGptModel(state.model)) {
      if (state.fileErrors.mask) {
        errors.push(state.fileErrors.mask);
      }
      if (state.imageMeta && state.maskMeta) {
        const sameSize =
          state.imageMeta.width === state.maskMeta.width &&
          state.imageMeta.height === state.maskMeta.height;
        if (!sameSize) {
          errors.push("蒙版尺寸必须与参考图完全一致。");
        }
      }
    }
  }

  return [...new Set(errors)];
}

function renderFormErrors(errors) {
  if (errors.length === 0) {
    refs.formErrors.hidden = true;
    refs.formErrors.innerHTML = "";
    return;
  }

  refs.formErrors.hidden = false;
  refs.formErrors.className = "notice notice-warning";

  const list = document.createElement("ul");
  errors.forEach((item) => {
    const listItem = document.createElement("li");
    listItem.textContent = item;
    list.appendChild(listItem);
  });

  refs.formErrors.innerHTML = "";
  refs.formErrors.appendChild(list);
}

async function handleSubmit(event) {
  event.preventDefault();
  const errors = collectFormErrors();
  if (errors.length > 0) {
    renderFormErrors(errors);
    return;
  }

  const submissionMeta = {
    model: getActiveModel(),
    mode: state.mode,
    prompt: refs.prompt.value.trim(),
  };
  state.pendingSubmissions += 1;
  updateFormState();
  setRequestState("创建中", "warning");
  setResultMessage("正在创建新任务。旧任务不会被打断，你可以继续提交。", "neutral");

  try {
    const request = buildRequest();
    const response = await fetch(request.url, request.options);
    const payload = await response.json();

    if (!response.ok || payload.error) {
      const message = extractApiErrorMessage(payload, "请求失败。");
      state.pendingSubmissions = Math.max(0, state.pendingSubmissions - 1);
      updateFormState();
      if (!state.selectedJobId) {
        setRequestState("请求失败", "error");
        setResultMessage(message, "error");
        clearResultDetail();
        setRawResponse(payload);
      } else {
        renderSelectedJob();
      }
      return;
    }

    state.pendingSubmissions = Math.max(0, state.pendingSubmissions - 1);
    rememberJob(payload, submissionMeta);
    selectJob(payload.job_id);
    startJobTracking(payload.job_id);
  } catch (error) {
    state.pendingSubmissions = Math.max(0, state.pendingSubmissions - 1);
    updateFormState();
    setRequestState("请求失败", "error");
    setResultMessage("提交任务失败，请检查本地服务或网络连接。", "error");
    if (!state.selectedJobId) {
      clearResultDetail();
    } else {
      renderSelectedJob();
    }
  }
}

function buildRequest() {
  if (isVideoMode()) {
    const formData = new FormData();
    formData.append("model", refs.videoModel.value);
    formData.append("prompt", refs.prompt.value.trim());
    formData.append("seconds", refs.videoSeconds.value);
    if (refs.image.files[0]) {
      formData.append("input_reference", refs.image.files[0]);
    }
    if (refs.videoEndImage.files[0]) {
      formData.append("input_reference_end", refs.videoEndImage.files[0]);
    }
    formData.append("size", refs.videoSize.value);
    formData.append("watermark", refs.videoWatermark.value);

    return {
      url: "/api/video-create",
      options: {
        method: "POST",
        body: formData,
      },
    };
  }

  if (state.mode === "edit") {
    const formData = new FormData();
    formData.append("model", state.model);
    formData.append("image", refs.image.files[0]);
    formData.append("prompt", refs.prompt.value.trim());

    if (isGptModel(state.model)) {
      formData.append("n", String(Number(refs.n.value)));
      formData.append("aspect_ratio", refs.gptAspectRatio.value);
      if (refs.mask.files[0]) {
        formData.append("mask", refs.mask.files[0]);
      }
    } else {
      formData.append("aspect_ratio", refs.aspectRatio.value);
      formData.append("image_size", refs.imageSize.value);
    }

    return {
      url: "/api/image-edit",
      options: {
        method: "POST",
        body: formData,
      },
    };
  }

  const payload = {
    model: state.model,
    prompt: refs.prompt.value.trim(),
  };

  if (isGptModel(state.model)) {
    payload.n = Number(refs.n.value);
    payload.aspect_ratio = refs.gptAspectRatio.value;
  } else {
    payload.aspect_ratio = refs.aspectRatio.value;
    payload.image_size = refs.imageSize.value;
  }

  return {
    url: "/api/image-generate",
    options: {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
  };
}

function startJobTracking(jobId) {
  const existing = state.trackers.get(jobId);
  if (existing?.source || existing?.pollTimer) {
    return;
  }

  const tracker = existing || { source: null, pollTimer: null };
  state.trackers.set(jobId, tracker);
  const source = new EventSource(`/api/jobs/${jobId}/events`);
  tracker.source = source;

  source.onmessage = (event) => {
    const snapshot = JSON.parse(event.data);
    rememberJob(snapshot);
    if (TERMINAL_STATUSES.has(snapshot.status)) {
      closeJobTracking(jobId);
    }
  };

  source.onerror = () => {
    const activeTracker = state.trackers.get(jobId);
    if (!activeTracker?.source) {
      return;
    }
    source.close();
    activeTracker.source = null;
    startPolling(jobId);
  };
}

function startPolling(jobId) {
  const tracker = state.trackers.get(jobId) || { source: null, pollTimer: null };
  if (tracker.pollTimer) {
    return;
  }
  state.trackers.set(jobId, tracker);
  tracker.pollTimer = window.setInterval(async () => {
    try {
      const response = await fetch(`/api/jobs/${jobId}`, { cache: "no-store" });
      if (!response.ok) {
        throw new Error("job-poll-failed");
      }
      const snapshot = await response.json();
      rememberJob(snapshot);
      if (TERMINAL_STATUSES.has(snapshot.status)) {
        closeJobTracking(jobId);
      }
    } catch (error) {
      if (state.selectedJobId === jobId) {
        setProgressMeta("状态流断开，轮询也失败了。请稍后重试。");
      }
      closeJobTracking(jobId);
      renderSelectedJob();
      updateFormState();
    }
  }, 1000);
}

function closePolling(jobId) {
  const tracker = state.trackers.get(jobId);
  if (!tracker?.pollTimer) {
    return;
  }
  window.clearInterval(tracker.pollTimer);
  tracker.pollTimer = null;
  if (!tracker.source) {
    state.trackers.delete(jobId);
  }
}

function closeJobTracking(jobId) {
  const tracker = state.trackers.get(jobId);
  if (!tracker) {
    return;
  }
  if (tracker.source) {
    tracker.source.close();
    tracker.source = null;
  }
  if (tracker.pollTimer) {
    window.clearInterval(tracker.pollTimer);
    tracker.pollTimer = null;
  }
  state.trackers.delete(jobId);
}

function closeAllJobTracking() {
  Array.from(state.trackers.keys()).forEach((jobId) => {
    closeJobTracking(jobId);
  });
}

function buildSuccessMessage(snapshot, previewItems, savedInfo, seconds) {
  const base = snapshot.message || "请求成功。";
  const previewText =
    previewItems.length > 0
      ? `解析到 ${previewItems.length} 个可预览结果`
      : "没有解析到可预览图片";
  const saveText =
    savedInfo.saves.length > 0
      ? `自动保存 ${savedInfo.saves.length} 个文件`
      : savedInfo.errors.length > 0
        ? previewItems.length > 0
          ? "自动保存未成功，但预览和原始链接仍可用"
          : "自动保存失败"
        : "没有可自动保存的媒体结果";
  return `${base} ${previewText}，${saveText}，总耗时 ${seconds} 秒。`;
}

function extractSavedInfo(result) {
  return {
    saves: Array.isArray(result?._local_saves) ? result._local_saves : [],
    errors: Array.isArray(result?._local_save_errors) ? result._local_save_errors : [],
    saveDir: typeof result?._save_dir === "string" ? result._save_dir : "",
  };
}

function renderSavedFiles(savedInfo) {
  const { saves, errors, saveDir } = savedInfo;

  if (!saves.length && !errors.length) {
    refs.savedPanel.hidden = true;
    refs.savedList.innerHTML = "";
    refs.savedErrors.hidden = true;
    refs.savedErrors.textContent = "";
    refs.savedSummary.textContent = "等待任务完成后展示自动保存结果。";
    return;
  }

  refs.savedPanel.hidden = false;
  refs.savedList.innerHTML = "";

  if (saves.length > 0) {
    refs.savedSummary.textContent = saveDir
      ? `已自动保存到：${saveDir}`
      : `已自动保存 ${saves.length} 个文件。`;

    saves.forEach((item, index) => {
      const card = document.createElement("article");
      card.className = "saved-card";

      const title = document.createElement("div");
      title.className = "saved-title";
      title.textContent = item.name || `文件 ${index + 1}`;

      const path = document.createElement("code");
      path.className = "saved-path";
      path.textContent = item.path || "";

      const meta = document.createElement("div");
      meta.className = "saved-meta";
      meta.textContent = buildSavedMeta(item);

      card.appendChild(title);
      card.appendChild(path);
      card.appendChild(meta);
      refs.savedList.appendChild(card);
    });
  } else {
    refs.savedSummary.textContent = "没有成功落盘的文件。";
  }

  if (errors.length > 0) {
    refs.savedErrors.hidden = false;
    refs.savedErrors.innerHTML = "";

    const list = document.createElement("ul");
    errors.forEach((item) => {
      const listItem = document.createElement("li");
      listItem.textContent = item;
      list.appendChild(listItem);
    });
    refs.savedErrors.appendChild(list);
  } else {
    refs.savedErrors.hidden = true;
    refs.savedErrors.textContent = "";
  }
}

function buildSavedMeta(item) {
  const chunks = [];
  if (item.mime_type) {
    chunks.push(item.mime_type);
  }
  if (typeof item.size === "number") {
    chunks.push(formatBytes(item.size));
  }
  if (item.source) {
    chunks.push(`来源：${item.source}`);
  }
  return chunks.join(" · ");
}

function phaseToLabel(phase) {
  const map = {
    accepted: "任务已受理",
    calling_upstream: "已发往上游",
    processing_response: "整理上游响应",
    completed: "处理完成",
    failed: "处理失败",
  };
  return map[phase] || phase || "处理中";
}

function setHealthBanner(message, tone) {
  refs.healthBanner.className = `health-banner notice notice-${tone}`;
  refs.healthBanner.textContent = message;
}

function setApiKeyMessage(message, tone) {
  refs.apiKeyMessage.className = `action-msg action-copy notice-inline notice-inline-${tone}`;
  refs.apiKeyMessage.textContent = message;
}

function setSaveDirMessage(message, tone) {
  refs.saveDirMessage.className = `action-msg action-copy notice-inline notice-inline-${tone}`;
  refs.saveDirMessage.textContent = message;
}

function setRequestState(text, tone) {
  refs.requestState.className = `status-pill status-${tone}`;
  refs.requestState.textContent = text;
}

function setResultMessage(message, tone) {
  refs.resultMessage.className = `result-notice notice notice-${tone}`;
  refs.resultMessage.textContent = message;
}

function setProgressVisible(visible) {
  refs.progressShell.hidden = !visible;
}

function setProgressMeta(text) {
  refs.progressMeta.textContent = text;
}

function renderGallery(items) {
  if (!items.length) {
    refs.resultGallery.hidden = true;
    refs.resultGallery.innerHTML = "";
    return;
  }

  refs.resultGallery.hidden = false;
  refs.resultGallery.innerHTML = "";

  items.forEach((item, index) => {
    const figure = document.createElement("figure");
    figure.className = "result-item";
    let media = null;
    if (item.kind === "video") {
      const video = document.createElement("video");
      video.src = item.src;
      video.controls = true;
      video.playsInline = true;
      video.preload = "metadata";
      media = video;
      figure.classList.add("is-video");
    } else {
      const image = document.createElement("img");
      image.src = item.src;
      image.alt = `结果图 ${index + 1}`;
      media = image;
    }

    const caption = document.createElement("figcaption");
    caption.textContent = item.label || `结果图 ${index + 1}`;

    figure.appendChild(media);
    figure.appendChild(caption);
    refs.resultGallery.appendChild(figure);
  });
}

function setRawResponse(payload) {
  if (!payload) {
    refs.rawPanel.hidden = true;
    refs.rawOutput.textContent = "";
    return;
  }

  refs.rawPanel.hidden = false;
  refs.rawOutput.textContent = JSON.stringify(payload, null, 2);
}

function extractPreviewItems(payload) {
  const items = [];
  const seen = new Set();

  function pushItem(source, label, kind = "image") {
    if (!source || !isSafeMediaSource(source) || seen.has(`${kind}:${source}`)) {
      return;
    }
    seen.add(`${kind}:${source}`);
    items.push({ src: source, label, kind });
  }

  function pushInlineData(blob, label) {
    if (!blob || typeof blob !== "object" || typeof blob.data !== "string") {
      return;
    }
    const mimeType = blob.mimeType || blob.mime_type || "image/png";
    if (!String(mimeType).startsWith("image/")) {
      return;
    }
    pushItem(`data:${mimeType};base64,${blob.data}`, label, "image");
  }

  function detectMediaKindFromSource(source) {
    const normalized = String(source || "").toLowerCase().split("?")[0];
    if (!normalized) {
      return "";
    }
    if (normalized.startsWith("data:video/")) {
      return "video";
    }
    if (normalized.startsWith("data:image/")) {
      return "image";
    }
    if (/\.(mp4|webm|mov|m4v|avi)$/i.test(normalized)) {
      return "video";
    }
    if (/\.(png|jpg|jpeg|webp|gif|bmp|svg)$/i.test(normalized)) {
      return "image";
    }
    return "";
  }

  function detectMediaKind(record, fallbackSource = "") {
    if (record?.is_video) {
      return "video";
    }
    if (record?.is_image) {
      return "image";
    }
    const mimeHints = [
      record?.mime_type,
      record?.mimeType,
      record?.content_type,
      record?.contentType,
      record?.type,
    ];
    for (const hint of mimeHints) {
      if (typeof hint !== "string") {
        continue;
      }
      const lower = hint.toLowerCase();
      if (lower.startsWith("video/")) {
        return "video";
      }
      if (lower.startsWith("image/")) {
        return "image";
      }
    }
    return detectMediaKindFromSource(fallbackSource) || "image";
  }

  function walk(value, depth = 0) {
    if (value === null || value === undefined || depth > 8) {
      return;
    }

    if (Array.isArray(value)) {
      value.forEach((entry) => walk(entry, depth + 1));
      return;
    }

    if (typeof value !== "object") {
      return;
    }

    if (typeof value.preview_url === "string" && (value.is_image || value.is_video)) {
      pushItem(
        value.preview_url,
        value.name || (value.is_video ? "本地视频" : "本地图像"),
        value.is_video ? "video" : "image",
      );
    }
    if (typeof value.url === "string") {
      pushItem(value.url, "URL 返回", detectMediaKind(value, value.url));
    }
    if (typeof value.image_url === "string") {
      pushItem(value.image_url, "image_url 返回", "image");
    }
    if (typeof value.video_url === "string") {
      pushItem(value.video_url, "video_url 返回", "video");
    }
    if (typeof value.file_url === "string") {
      pushItem(value.file_url, "file_url 返回", detectMediaKind(value, value.file_url));
    }
    if (typeof value.b64_json === "string") {
      pushItem(`data:image/png;base64,${value.b64_json}`, "b64_json 返回", "image");
    }
    if (typeof value.b64 === "string") {
      pushItem(`data:image/png;base64,${value.b64}`, "Base64 返回", "image");
    }

    pushInlineData(value.inlineData, "Gemini inlineData");
    pushInlineData(value.inline_data, "Gemini inline_data");

    Object.values(value).forEach((entry) => walk(entry, depth + 1));
  }

  walk(payload);
  return items;
}

function extractApiErrorMessage(payload, fallback) {
  if (payload?.error?.message) {
    return payload.error.message;
  }

  if (Array.isArray(payload?.detail)) {
    return payload.detail
      .map((item) => item.msg || item.message || JSON.stringify(item))
      .join("；");
  }

  if (typeof payload?.detail === "string" && payload.detail.trim()) {
    return payload.detail.trim();
  }

  return fallback;
}

function formatBytes(bytes) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function formatDuration(milliseconds) {
  const totalSeconds = Math.max(Math.round(milliseconds / 100) / 10, 0);
  if (totalSeconds < 60) {
    return `${totalSeconds.toFixed(1)} 秒`;
  }

  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds - minutes * 60;
  if (minutes < 60) {
    return `${minutes} 分 ${seconds.toFixed(1)} 秒`;
  }

  const hours = Math.floor(minutes / 60);
  const restMinutes = minutes - hours * 60;
  return `${hours} 小时 ${restMinutes} 分 ${seconds.toFixed(1)} 秒`;
}

function isSafeImageSource(source) {
  return isSafeMediaSource(source);
}

function isSafeMediaSource(source) {
  return (
    source.startsWith("/") ||
    source.startsWith("http://") ||
    source.startsWith("https://") ||
    source.startsWith("data:image/") ||
    source.startsWith("data:video/")
  );
}
