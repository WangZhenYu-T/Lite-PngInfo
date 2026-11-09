const state = { file: null, metadata: null, previewUrl: null, request: 0, canFavorite: false };
const $ = (selector) => document.querySelector(selector);
const fileInput = $("#file-input");
const dropZone = $("#drop-zone");
let sessionQueue = Promise.resolve();
let favoritesRequest = 0;

function setStatus(message, isError = false) {
  $("#status").textContent = message;
  $("#status").classList.toggle("error", isError);
}

function escapeHtml(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

async function api(path, options) {
  const response = await fetch(path, options);
  const result = await response.json();
  if (!response.ok || !result.ok) throw new Error(result.error || "请求失败");
  return result;
}

// Serialize session writes: Reset/new reads must not overtake an earlier upload or favorite.
function sessionAction(action) {
  const task = sessionQueue.then(action);
  sessionQueue = task.catch(() => {});
  return task;
}

function clearResult() {
  state.metadata = null;
  state.canFavorite = false;
  if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
  state.previewUrl = null;
  $("#preview-image").removeAttribute("src");
  $("#image-size").textContent = "";
  $("#preview-panel").classList.add("is-hidden");
  $("#result-section").classList.add("is-hidden");
  $("#categorized-result").replaceChildren();
  $("#json-result").replaceChildren();
  $("#source-label").textContent = "";
  $("#favorite-button").disabled = true;
}

function pickFile(file) {
  if (!file) return;
  ++state.request;
  clearResult();
  state.file = null;
  $("#read-button").disabled = false;
  $("#selected-file").textContent = `${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MB`;
  if (file.type !== "image/png" && !file.name.toLowerCase().endsWith(".png")) {
    setStatus("请选择 PNG 图片", true);
    return;
  }
  if (file.size > 30 * 1024 * 1024) {
    setStatus("图片不能超过 30 MB", true);
    return;
  }
  state.file = file;
  setStatus("已选择，点击读取");
}

function renderFieldGrid(values) {
  return `<div class="info-grid">${Object.entries(values)
    .filter(([, value]) => value !== null && value !== undefined && value !== "")
    .map(([key, value]) => `<div class="info-key">${escapeHtml(key)}</div><div class="info-value">${escapeHtml(typeof value === "object" ? JSON.stringify(value, null, 2) : value)}</div>`)
    .join("")}</div>`;
}

function card(title, body, wide = false) {
  return `<article class="info-card${wide ? " wide" : ""}"><h3>${escapeHtml(title)}</h3>${body}</article>`;
}

function promptCard(title, text, key) {
  if (!text) return "";
  return card(title, `<button class="text-button copy-prompt" type="button" data-copy-prompt="${key}">复制</button><div class="prompt-box">${escapeHtml(text)}</div>`, true);
}

function renderCategorized(metadata) {
  const { file, generation, prompts, models, loras } = metadata;
  let html = card("图片信息", renderFieldGrid({ "文件名": file.filename, "格式": file.format,
    "色彩模式": file.mode, "尺寸": `${file.width} × ${file.height}`, "宽高比": file.aspect_ratio,
    "文件大小": `${(file.file_size_bytes / 1024 / 1024).toFixed(2)} MB` }));
  const labels = { seed: "种子", steps: "步数", scale: "CFG / Scale", cfg_rescale: "CFG 重采样",
    sampler: "采样器", noise_schedule: "噪声计划", width: "生成宽度", height: "生成高度",
    n_samples: "样本数", request_type: "请求类型", version: "版本" };
  const parameters = Object.fromEntries(Object.entries(generation)
    .filter(([key]) => !["model_name", "model_hash", "Model", "Model hash", "Lora hashes"].includes(key))
    .map(([key, value]) => [labels[key] || key, value]));
  if (Object.keys(parameters).length) html += card("生成参数", renderFieldGrid(parameters));
  html += promptCard("正向提示词", prompts.prompt, "prompt");
  html += promptCard("负向提示词", prompts.negative_prompt, "negative_prompt");
  prompts.characters.forEach((role, index) => {
    html += promptCard(`角色 ${index + 1} · 正向提示词`, role.prompt, `characters.${index}.prompt`);
    html += promptCard(`角色 ${index + 1} · 负向提示词`, role.negative_prompt, `characters.${index}.negative_prompt`);
  });
  if (models.length) html += card("模型 / Checkpoint", models.map((model) =>
    renderFieldGrid({ "类型": model.type, "名称": model.name, "哈希": model.hash })).join(""), true);
  if (loras.length) html += card("LoRA", loras.map((lora) =>
    `<div class="model-item">${renderFieldGrid({ "名称": lora.name, "权重": lora.weight, "哈希": lora.hash })}</div>`).join(""), true);
  let message = "";
  if (metadata.status === "empty") message = "未发现生成元信息。可以预览或收藏这张图片。";
  else if (metadata.status === "unclassified") message = "存在元信息，暂无法分类。请选择 JSON 模式查看。";
  else if (!prompts.prompt && !prompts.negative_prompt && !Object.keys(generation).length && !models.length) {
    message = "未找到可分类的生成参数。请选择 JSON 模式查看已有字段。";
  }
  if (message) html += card("读取说明", `<p class="empty-state">${escapeHtml(message)}</p>`, true);
  if (metadata.notes.length) html += card("备注", metadata.notes.map((note) => `<p>${escapeHtml(note)}</p>`).join(""), true);
  return html;
}

function renderJson(metadata) {
  const fields = metadata.entries.map((entry) => {
    const archived = entry.kind === "archived";
    const label = entry.kind === "invalid-json" ? "无效 JSON · 显示原文" : archived ? "历史结果" : entry.kind === "json" ? "JSON" : "文本";
    return `<article class="info-card"><div class="field-heading"><h3>${escapeHtml(entry.key)} <span class="field-kind">#${entry.index + 1} · ${label}</span></h3>
      ${archived ? "" : `<button class="text-button" type="button" data-copy-entry="${entry.index}">复制原文</button>`}</div>
      <pre class="json-result">${escapeHtml(entry.formatted ?? entry.text)}</pre></article>`;
  }).join("");
  const info = Object.keys(metadata.image_info).length
    ? card("图片附属信息", `<pre class="json-result">${escapeHtml(JSON.stringify(metadata.image_info, null, 2))}</pre>`) : "";
  return (fields || '<p class="empty-state">无可展示的文本元信息。</p>') + info;
}

function renderResults() {
  if (!state.metadata) return;
  const isJson = $("#output-mode").value === "json";
  $("#result-section").classList.remove("is-hidden");
  $("#source-label").textContent = state.metadata.source.label;
  $("#categorized-result").classList.toggle("is-hidden", isJson);
  $("#json-result").classList.toggle("is-hidden", !isJson);
  $("#categorized-result").innerHTML = renderCategorized(state.metadata);
  $("#json-result").innerHTML = renderJson(state.metadata);
  $("#copy-button").textContent = isJson ? "导出原始字段集合" : "复制分类结果";
  $("#copy-button").disabled = isJson && (!state.metadata.entries.length || state.metadata.entries.some((e) => e.kind === "archived"));
}

async function readFile() {
  if (!state.file) return setStatus("请先拖入或选择 PNG 图片", true);
  const file = state.file;
  const request = ++state.request;
  clearResult();
  setStatus("正在读取…");
  $("#read-button").disabled = true;
  try {
    const result = await sessionAction(() => api("/api/inspect", { method: "POST", body: file,
      headers: { "Content-Type": "image/png", "X-Filename": encodeURIComponent(file.name) } }));
    if (request !== state.request) return;
    state.metadata = result.metadata;
    state.canFavorite = true;
    state.previewUrl = URL.createObjectURL(file);
    $("#preview-image").src = state.previewUrl;
    $("#image-size").textContent = `${result.metadata.file.width} × ${result.metadata.file.height}`;
    $("#preview-panel").classList.toggle("is-hidden", !$("#show-image").checked);
    $("#favorite-button").disabled = false;
    renderResults();
    setStatus(result.metadata.status === "empty" ? "读取完成 · 无生成元信息" : "读取完成");
  } catch (error) {
    if (request === state.request) setStatus(error.message, true);
  } finally {
    if (request === state.request) $("#read-button").disabled = false;
  }
}

async function resetAll() {
  const request = ++state.request;
  clearResult();
  state.file = null;
  fileInput.value = "";
  $("#selected-file").textContent = "尚未选择文件";
  $("#read-button").disabled = false;
  setStatus("正在重置…");
  try {
    await sessionAction(() => api("/api/reset", { method: "POST" }));
    if (request === state.request) setStatus("已重置");
  } catch (error) {
    if (request === state.request) setStatus(`页面已清空，服务端重置失败：${error.message}`, true);
  }
}

async function favoriteCurrent() {
  if (!state.canFavorite) return;
  const request = state.request;
  $("#favorite-button").disabled = true;
  try {
    const result = await sessionAction(() => api("/api/favorites", { method: "POST" }));
    if (request === state.request) setStatus(result.already_exists ? "这张图片已经收藏过" : "已收藏");
    await loadFavorites();
  } catch (error) {
    if (request === state.request) setStatus(error.message, true);
  } finally {
    if (request === state.request) $("#favorite-button").disabled = !state.canFavorite;
  }
}

async function loadFavorites() {
  const request = ++favoritesRequest;
  const container = $("#favorites-list");
  try {
    const result = await api("/api/favorites");
    if (request !== favoritesRequest) return;
    container.innerHTML = result.favorites.length ? result.favorites.map((item) => `
      <article class="favorite-card">
        <img src="/api/favorites/${item.id}/image" alt="${escapeHtml(item.filename)}" loading="lazy">
        <div class="favorite-body"><div class="favorite-name">${escapeHtml(item.filename)}</div>
          <span class="source-badge">${escapeHtml(item.source.label)}</span>
          <div class="favorite-meta">${item.width || "?"} × ${item.height || "?"} · ${new Date(item.created_at).toLocaleString()}</div>
          <div class="favorite-prompt">${escapeHtml(item.prompt || (item.status === "empty" ? "无生成元信息" : "未记录或无法可靠提取提示词"))}</div>
          <div class="favorite-actions"><button class="text-button" type="button" data-open-favorite="${item.id}">载入信息</button>
            <button class="text-button" type="button" data-delete-favorite="${item.id}">解除收藏</button></div>
        </div></article>`).join("") : '<p class="empty-state">还没有收藏内容。</p>';
  } catch (error) {
    if (request === favoritesRequest) container.innerHTML = `<p class="empty-state">${escapeHtml(error.message)}</p>`;
  }
}

async function openFavorite(id) {
  const request = ++state.request;
  clearResult();
  state.file = null;
  fileInput.value = "";
  $("#read-button").disabled = false;
  $("#selected-file").textContent = "正在读取收藏…";
  try {
    const result = await api(`/api/favorites/${id}`);
    if (request !== state.request) return;
    state.metadata = result.metadata;
    $("#selected-file").textContent = `收藏：${result.favorite.filename}`;
    $("#preview-image").src = `/api/favorites/${id}/image`;
    $("#preview-panel").classList.toggle("is-hidden", !$("#show-image").checked);
    $("#image-size").textContent = `${result.metadata.file.width} × ${result.metadata.file.height}`;
    renderResults();
    setStatus("已载入收藏信息");
    await loadFavorites();
  } catch (error) {
    if (request === state.request) setStatus(error.message, true);
  }
}

async function deleteFavorite(id) {
  if (!window.confirm("解除收藏后会删除保存的图片和元信息，确定继续吗？")) return;
  try {
    await api(`/api/favorites/${id}/delete`, { method: "POST" });
    setStatus("已解除收藏");
    await loadFavorites();
  } catch (error) { setStatus(error.message, true); }
}

async function copyText(text) {
  try { await navigator.clipboard.writeText(text); setStatus("已复制"); }
  catch (_) { setStatus("复制失败，请检查浏览器剪贴板权限。", true); }
}

dropZone.addEventListener("click", () => fileInput.click());
dropZone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") { event.preventDefault(); fileInput.click(); }
});
fileInput.addEventListener("change", () => pickFile(fileInput.files[0]));
["dragenter", "dragover"].forEach((name) => dropZone.addEventListener(name, (event) => { event.preventDefault(); dropZone.classList.add("dragover"); }));
["dragleave", "drop"].forEach((name) => dropZone.addEventListener(name, (event) => { event.preventDefault(); dropZone.classList.remove("dragover"); }));
dropZone.addEventListener("drop", (event) => pickFile(event.dataTransfer.files[0]));
$("#read-button").addEventListener("click", readFile);
$("#reset-button").addEventListener("click", resetAll);
$("#favorite-button").addEventListener("click", favoriteCurrent);
$("#show-image").addEventListener("change", () => $("#preview-panel").classList.toggle("is-hidden", !$("#show-image").checked || !state.metadata));
$("#output-mode").addEventListener("change", renderResults);
$("#copy-button").addEventListener("click", () => {
  if (!state.metadata) return;
  const { entries, image_info, ...categorized } = state.metadata;
  copyText(JSON.stringify($("#output-mode").value === "json"
    ? entries.map(({ key, text }) => ({ key, text })) : categorized, null, 2));
});
$("#result-section").addEventListener("click", (event) => {
  const entry = event.target.closest("[data-copy-entry]");
  const prompt = event.target.closest("[data-copy-prompt]");
  if (entry) copyText(state.metadata.entries[Number(entry.dataset.copyEntry)].text);
  if (prompt) copyText(prompt.dataset.copyPrompt.split(".").reduce((value, key) => value[key], state.metadata.prompts));
});
$("#refresh-favorites").addEventListener("click", loadFavorites);
$("#favorites-list").addEventListener("click", (event) => {
  const open = event.target.closest("[data-open-favorite]");
  const remove = event.target.closest("[data-delete-favorite]");
  if (open) openFavorite(open.dataset.openFavorite);
  if (remove) deleteFavorite(remove.dataset.deleteFavorite);
});
loadFavorites();
