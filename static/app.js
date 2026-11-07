const state = {
  file: null,
  metadata: null,
  previewUrl: null,
};

const $ = (selector) => document.querySelector(selector);
const dropZone = $("#drop-zone");
const fileInput = $("#file-input");
const statusEl = $("#status");

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.classList.toggle("error", isError);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

function pickFile(file) {
  if (!file) return;
  if (file.type !== "image/png" && !file.name.toLowerCase().endsWith(".png")) {
    setStatus("请选择 PNG 图片", true);
    return;
  }
  state.file = file;
  $("#selected-file").textContent = `${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MB`;
  setStatus("已选择，点击读取");
}

function renderFieldGrid(values) {
  return `<div class="info-grid">${Object.entries(values).map(([key, value]) =>
    `<div class="info-key">${escapeHtml(key)}</div><div class="info-value">${escapeHtml(formatValue(value))}</div>`
  ).join("")}</div>`;
}

function renderCategorized(metadata) {
  const file = metadata.file || {};
  const generation = metadata.generation || {};
  const prompts = metadata.prompts || {};
  const raw = metadata.raw || {};
  const fileValues = { "文件名": file.filename, "格式": file.format, "色彩模式": file.mode, "尺寸": `${file.width || "?"} × ${file.height || "?"}`, "宽高比": file.aspect_ratio, "文件大小": `${((file.file_size_bytes || 0) / 1024 / 1024).toFixed(2)} MB` };
  const generationValues = { "模型": generation.model_name, "模型哈希": generation.model_hash, "种子": generation.seed, "步数": generation.steps, "采样器": generation.sampler, "噪声计划": generation.noise_schedule, "CFG / Scale": generation.scale, "CFG 重采样": generation.cfg_rescale, "样本数": generation.n_samples, "请求类型": generation.request_type };
  const other = Object.fromEntries(Object.entries(raw).filter(([key]) => !["Comment", "Description"].includes(key)));
  return `
    <article class="info-card"> <h3>图片信息</h3>${renderFieldGrid(fileValues)}</article>
    <article class="info-card"> <h3>生成参数</h3>${renderFieldGrid(generationValues)}</article>
    <article class="info-card wide"> <h3>正向提示词</h3><div class="prompt-box">${escapeHtml(prompts.prompt || "未找到正向提示词")}</div></article>
    <article class="info-card wide"> <h3>负面提示词</h3><div class="prompt-box">${escapeHtml(prompts.negative_prompt || "未找到负面提示词")}</div></article>
    <article class="info-card wide"><details><summary>其他 PNG 元信息</summary><pre class="json-result">${escapeHtml(JSON.stringify(other, null, 2))}</pre></details></article>`;
}

function renderResults() {
  const metadata = state.metadata;
  if (!metadata) return;
  $("#result-section").classList.remove("is-hidden");
  const isJson = $("#output-mode").value === "json";
  $("#categorized-result").classList.toggle("is-hidden", isJson);
  $("#json-result").classList.toggle("is-hidden", !isJson);
  $("#categorized-result").innerHTML = renderCategorized(metadata);
  $("#json-result").textContent = JSON.stringify(metadata, null, 2);
}

async function readFile() {
  if (!state.file) {
    setStatus("请先拖入或选择 PNG 图片", true);
    return;
  }
  setStatus("正在读取…");
  $("#read-button").disabled = true;
  try {
    const response = await fetch("/api/inspect", {
      method: "POST",
      body: state.file,
      headers: { "Content-Type": "image/png", "X-Filename": encodeURIComponent(state.file.name) },
    });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || "读取失败");
    state.metadata = result.metadata;
    const fileInfo = state.metadata.file || {};
    if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
    state.previewUrl = URL.createObjectURL(state.file);
    $("#preview-image").src = state.previewUrl;
    $("#image-size").textContent = `${fileInfo.width} × ${fileInfo.height}`;
    $("#preview-panel").classList.toggle("is-hidden", !$("#show-image").checked);
    $("#favorite-button").disabled = false;
    renderResults();
    setStatus("读取完成");
  } catch (error) {
    setStatus(error.message || "读取失败", true);
  } finally {
    $("#read-button").disabled = false;
  }
}

async function resetAll() {
  try { await fetch("/api/reset", { method: "POST" }); } catch (_) { /* server may already be stopped */ }
  state.file = null;
  state.metadata = null;
  if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
  state.previewUrl = null;
  fileInput.value = "";
  $("#selected-file").textContent = "尚未选择文件";
  $("#preview-image").removeAttribute("src");
  $("#preview-panel").classList.add("is-hidden");
  $("#result-section").classList.add("is-hidden");
  $("#favorite-button").disabled = true;
  setStatus("已重置");
}

async function favoriteCurrent() {
  if (!state.metadata) return;
  const button = $("#favorite-button");
  button.disabled = true;
  try {
    const response = await fetch("/api/favorites", { method: "POST" });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || "收藏失败");
    setStatus(result.already_exists ? "这张图片已经收藏过" : "已收藏");
    await loadFavorites();
  } catch (error) {
    setStatus(error.message || "收藏失败", true);
  } finally {
    button.disabled = false;
  }
}

async function loadFavorites() {
  const container = $("#favorites-list");
  try {
    const response = await fetch("/api/favorites");
    const result = await response.json();
    if (!result.ok) throw new Error(result.error || "收藏加载失败");
    if (!result.favorites.length) {
      container.innerHTML = '<p class="empty-state">还没有收藏内容。</p>';
      return;
    }
    container.innerHTML = result.favorites.map((item) => `
      <article class="favorite-card">
        <img src="/api/favorites/${item.id}/image" alt="${escapeHtml(item.filename)}" data-favorite-id="${item.id}">
        <div class="favorite-body">
          <div class="favorite-name" title="${escapeHtml(item.filename)}">${escapeHtml(item.filename)}</div>
          <div class="favorite-meta">${item.width || "?"} × ${item.height || "?"} · ${new Date(item.created_at).toLocaleString()}</div>
          <div class="favorite-prompt">${escapeHtml(item.prompt || "未找到提示词")}</div>
          <div class="favorite-actions"><button class="text-button" type="button" data-open-favorite="${item.id}">载入信息</button><button class="text-button" type="button" data-delete-favorite="${item.id}">解除收藏</button></div>
        </div>
      </article>`).join("");
  } catch (error) {
    container.innerHTML = `<p class="empty-state">${escapeHtml(error.message || "收藏加载失败")}</p>`;
  }
}

async function openFavorite(id) {
  try {
    const response = await fetch(`/api/favorites/${id}`);
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || "载入失败");
    state.metadata = result.metadata;
    state.file = null;
    $("#selected-file").textContent = `收藏：${result.favorite.filename}`;
    $("#preview-image").src = `/api/favorites/${id}/image`;
    $("#preview-panel").classList.toggle("is-hidden", !$("#show-image").checked);
    $("#image-size").textContent = `${result.favorite.width} × ${result.favorite.height}`;
    $("#favorite-button").disabled = true;
    renderResults();
    setStatus("已载入收藏信息");
    window.scrollTo({ top: 0, behavior: "smooth" });
  } catch (error) { setStatus(error.message || "载入失败", true); }
}

async function deleteFavorite(id) {
  if (!window.confirm("解除收藏后会删除后端保存的图片和元信息，确定继续吗？")) return;
  const response = await fetch(`/api/favorites/${id}/delete`, { method: "POST" });
  const result = await response.json();
  if (!response.ok || !result.ok) { setStatus(result.error || "解除收藏失败", true); return; }
  setStatus("已解除收藏");
  await loadFavorites();
}

dropZone.addEventListener("click", () => fileInput.click());
dropZone.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") fileInput.click(); });
fileInput.addEventListener("change", () => pickFile(fileInput.files[0]));
["dragenter", "dragover"].forEach((eventName) => dropZone.addEventListener(eventName, (event) => { event.preventDefault(); dropZone.classList.add("dragover"); }));
["dragleave", "drop"].forEach((eventName) => dropZone.addEventListener(eventName, (event) => { event.preventDefault(); dropZone.classList.remove("dragover"); }));
dropZone.addEventListener("drop", (event) => pickFile(event.dataTransfer.files[0]));
$("#read-button").addEventListener("click", readFile);
$("#reset-button").addEventListener("click", resetAll);
$("#favorite-button").addEventListener("click", favoriteCurrent);
$("#show-image").addEventListener("change", () => $("#preview-panel").classList.toggle("is-hidden", !$("#show-image").checked || !state.metadata));
$("#output-mode").addEventListener("change", renderResults);
$("#copy-button").addEventListener("click", async () => {
  const text = $("#output-mode").value === "json" ? $("#json-result").textContent : JSON.stringify(state.metadata, null, 2);
  await navigator.clipboard.writeText(text);
  setStatus("结果已复制");
});
$("#refresh-favorites").addEventListener("click", loadFavorites);
$("#favorites-list").addEventListener("click", (event) => {
  const openButton = event.target.closest("[data-open-favorite]");
  const deleteButton = event.target.closest("[data-delete-favorite]");
  if (openButton) openFavorite(openButton.dataset.openFavorite);
  if (deleteButton) deleteFavorite(deleteButton.dataset.deleteFavorite);
});

loadFavorites();
