const pollInterval = Number(document.body.dataset.pollInterval || 1000);

const SUIT_META = {
  s: { symbol: "♠", emoji: "♠️", className: "black", name: "黑桃" },
  h: { symbol: "♥", emoji: "♥️", className: "red", name: "红桃" },
  d: { symbol: "♦", emoji: "♦️", className: "red", name: "方片" },
  c: { symbol: "♣", emoji: "♣️", className: "black", name: "梅花" },
};

const ACTION_META = {
  fold: { emoji: "🛑", label: "弃牌" },
  check: { emoji: "👀", label: "过牌" },
  call: { emoji: "📞", label: "跟注" },
  bet: { emoji: "💰", label: "下注" },
  raise: { emoji: "🚀", label: "加注" },
  all_in: { emoji: "🔥", label: "全下" },
};

const EVENT_META = {
  session_created: { emoji: "🆕", label: "创建牌桌" },
  hand_started: { emoji: "🎬", label: "开始新一手" },
  street_changed: { emoji: "🛣️", label: "街道切换" },
  waiting_actor_action: { emoji: "🎯", label: "等待行动" },
  board_dealt: { emoji: "🃏", label: "发公共牌" },
  showdown_started: { emoji: "🪞", label: "进入摊牌" },
  hand_ended: { emoji: "🏁", label: "手牌结束" },
  blind_posted: { emoji: "🪙", label: "盲注入池" },
  action_applied: { emoji: "⚡", label: "动作落地" },
  folded: { emoji: "🛑", label: "弃牌" },
  checked: { emoji: "👀", label: "过牌" },
  called: { emoji: "📞", label: "跟注" },
  bet_to: { emoji: "💰", label: "下注到" },
  raised_to: { emoji: "🚀", label: "加注到" },
  all_in: { emoji: "🔥", label: "全下" },
  pot_awarded: { emoji: "🏆", label: "分配底池" },
  chat_sent: { emoji: "💬", label: "聊天消息" },
};

const STREET_META = {
  preflop: { emoji: "🎴", label: "翻牌前" },
  flop: { emoji: "🃏", label: "翻牌" },
  turn: { emoji: "🎯", label: "转牌" },
  river: { emoji: "🌊", label: "河牌" },
  showdown: { emoji: "🪞", label: "摊牌" },
};

const PHASE_META = {
  waiting_start: "等待开始",
  running: "进行中",
  waiting_actor_action: "等待行动",
  hand_ended: "本手结束",
  closed: "已关闭",
};

const CHANNEL_META = {
  system: "系统",
  action: "动作",
  chat: "聊天",
};

function parseConfiguredBotNames() {
  const node = document.getElementById("botNamesData");
  if (!node?.textContent) {
    return ["阿岚", "老岩", "唐梨", "温策", "小顾"];
  }
  try {
    const parsed = JSON.parse(node.textContent);
    if (Array.isArray(parsed) && parsed.length) {
      return parsed.map((item) => String(item));
    }
  } catch (error) {
    console.error("Failed to parse bot name pool", error);
  }
  return ["阿岚", "老岩", "唐梨", "温策", "小顾"];
}

const configuredBotNames = parseConfiguredBotNames();

let sessionId = "";
let lastEventId = 0;
let pollHandle = null;
let currentState = null;
let selectedActionSpec = null;
let sessionEvents = [];
let recentSeatChats = {};
let handIndex = new Map();
let sessionUserParticipates = false;
let sessionUserName = "";
let botNameOrder = shuffleArray(configuredBotNames);
let renderSignatures = {
  board: "",
  actions: "",
  speaker: "",
  sessionMeta: "",
};

const banner = document.getElementById("banner");
const sessionMeta = document.getElementById("sessionMeta");
const copySessionBtn = document.getElementById("copySessionBtn");
const tableArea = document.getElementById("tableArea");
const boardArea = document.getElementById("boardArea");
const actionMeta = document.getElementById("actionMeta");
const actionButtons = document.getElementById("actionButtons");
const amountBox = document.getElementById("amountBox");
const actionAmount = document.getElementById("actionAmount");
const timeline = document.getElementById("timeline");
const historyList = document.getElementById("historyList");
const replayView = document.getElementById("replayView");
const selectedActionHint = document.getElementById("selectedActionHint");
const submitAmountAction = document.getElementById("submitAmountAction");
const createSessionForm = document.getElementById("createSessionForm");
const seatCountInput = createSessionForm.querySelector('input[name="seat_count"]');
const sessionIdInput = createSessionForm.querySelector('input[name="session_id"]');
const seedInput = createSessionForm.querySelector('input[name="seed"]');
const randomSessionBtn = document.getElementById("randomSessionBtn");
const loadSessionBtn = document.getElementById("loadSessionBtn");
const randomSeedBtn = document.getElementById("randomSeedBtn");
const sessionSetupPanel = document.getElementById("sessionSetupPanel");
const startHandPanel = document.getElementById("startHandPanel");
const startHandBtn = document.getElementById("startHandBtn");
const interactionGrid = document.getElementById("interactionGrid");
const bottomGrid = document.getElementById("bottomGrid");
const timelinePanel = document.getElementById("timelinePanel");
const timelinePanelNote = document.getElementById("timelinePanelNote");
const userParticipatesToggle = document.getElementById("userParticipatesToggle");
const userNameField = document.getElementById("userNameField");
const userNameInput = createSessionForm.querySelector('input[name="user_name"]');
const seatPlanPreview = document.getElementById("seatPlanPreview");
const botNamePool = document.getElementById("botNamePool");
const speakerNameDisplay = document.getElementById("speakerNameDisplay");

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok || data.ok === false) {
    const error = new Error(data?.error?.message || "请求失败");
    error.status = response.status;
    error.code = data?.error?.code || null;
    error.details = data?.error?.details || null;
    throw error;
  }
  return data.data;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function showBanner(message) {
  banner.textContent = message;
  banner.classList.remove("hidden");
  clearTimeout(showBanner.timer);
  showBanner.timer = setTimeout(() => banner.classList.add("hidden"), 2600);
}

function defaultUserName() {
  return "玩家";
}

function shuffleArray(items) {
  const next = [...items];
  for (let index = next.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1));
    [next[index], next[swapIndex]] = [next[swapIndex], next[index]];
  }
  return next;
}

function generateRandomSessionId() {
  const alphabet = "abcdefghjkmnpqrstuvwxyz23456789";
  const suffix = Array.from({ length: 6 }, () => alphabet[Math.floor(Math.random() * alphabet.length)]).join("");
  return `table-${suffix}`;
}

function generateRandomSeed() {
  return String(Math.floor(Math.random() * 2_147_483_647));
}

function formatDateTime(value) {
  if (!value) {
    return "-";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString("zh-CN", {
    hour12: false,
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function actionLabel(action) {
  const meta = ACTION_META[action] || { emoji: "🎲", label: action };
  return `${meta.emoji} ${meta.label}`;
}

function streetLabel(street) {
  return STREET_META[street]?.label || street || "-";
}

function phaseLabel(phase) {
  return PHASE_META[phase] || phase || "-";
}

function channelLabel(channel) {
  return CHANNEL_META[channel] || channel || "-";
}

function seatNoLabel(seatNo) {
  return `${Number(seatNo) + 1} 号位`;
}

function seatById(seatId, seats = []) {
  return (seats || []).find((seat) => seat.seat_id === seatId) || null;
}

function seatDisplayName(seatId, seats = []) {
  const seat = seatById(seatId, seats);
  return seat ? seat.display_name : seatId;
}

function seatDisplayWithNo(seatId, seats = []) {
  const seat = seatById(seatId, seats);
  return seat ? `${seat.display_name} · ${seatNoLabel(seat.seat_no)}` : seatId;
}

function allKnownSeats() {
  const seatMap = new Map();
  (currentState?.seats || []).forEach((seat) => seatMap.set(seat.seat_id, seat));
  (currentState?.current_hand?.seats || []).forEach((seat) => seatMap.set(seat.seat_id, seat));
  return Array.from(seatMap.values()).sort((left, right) => left.seat_no - right.seat_no);
}

function seatLimitForMode(userParticipates = userParticipatesToggle.checked) {
  return userParticipates ? 6 : 5;
}

function clampSeatCount(value, userParticipates = userParticipatesToggle.checked) {
  const limit = seatLimitForMode(userParticipates);
  return Math.max(2, Math.min(limit, Number(value) || 2));
}

function currentDraftUserName() {
  return (userNameInput.value || "").trim() || defaultUserName();
}

function participantSeatFromState(data) {
  return [...(data?.seats || [])]
    .sort((left, right) => left.seat_no - right.seat_no)
    .find((seat) => Number(seat.seat_no) === 0) || null;
}

function resolveUserNameFromState(data) {
  return participantSeatFromState(data)?.display_name || data?.viewer?.viewer_name || defaultUserName();
}

function applySessionContext(data) {
  sessionUserParticipates = Boolean(data?.user_participates);
  sessionUserName = sessionUserParticipates ? resolveUserNameFromState(data) : "";
}

function buildStatePath(targetSessionId, userParticipates = sessionUserParticipates, viewerName = sessionUserName) {
  const base = `/api/v1/sessions/${targetSessionId}/state`;
  if (!userParticipates || !viewerName) {
    return base;
  }
  return `${base}?viewer_name=${encodeURIComponent(viewerName)}`;
}

function buildReplayPath(handId, userParticipates = sessionUserParticipates, viewerName = sessionUserName) {
  const base = `/api/v1/replays/${handId}`;
  if (!userParticipates || !viewerName) {
    return base;
  }
  return `${base}?viewer_name=${encodeURIComponent(viewerName)}`;
}

function resetReplayPlaceholder(message = "🪄 选择一手已结束牌局查看回放。") {
  replayView.innerHTML = `<div class="empty-state">${message}</div>`;
  replayView.dataset.handId = "";
}

function resetRenderSignatures() {
  renderSignatures = {
    board: "",
    actions: "",
    speaker: "",
    sessionMeta: "",
  };
}

function updateHandIndex(items = []) {
  items.forEach((item) => {
    if (!item?.hand_id) {
      return;
    }
    handIndex.set(item.hand_id, {
      hand_no: item.hand_no,
      phase: item.phase || "ended",
      started_at: item.started_at,
      ended_at: item.ended_at,
    });
  });
  if (currentState?.current_hand?.hand_id) {
    handIndex.set(currentState.current_hand.hand_id, {
      hand_no: currentState.current_hand.hand_no,
      phase: currentState.phase === "waiting_actor_action" ? "running" : "ended",
      started_at: currentState.current_hand.started_at || null,
      ended_at: currentState.current_hand.ended_at || null,
    });
  }
}

function rememberSessionEvents(events, replace = false) {
  const existing = replace ? [] : sessionEvents.slice();
  const byId = new Map(existing.map((event) => [event.event_id, event]));
  (events || []).forEach((event) => byId.set(event.event_id, event));
  sessionEvents = Array.from(byId.values())
    .sort((left, right) => left.event_id - right.event_id)
    .slice(-240);
}

function renderBotPool() {
  botNamePool.innerHTML = configuredBotNames
    .map((name) => `<span class="badge">🎭 ${escapeHtml(name)}</span>`)
    .join("");
}

function previewSeatNames() {
  const userParticipates = userParticipatesToggle.checked;
  const seatCount = clampSeatCount(seatCountInput.value, userParticipates);
  const botCount = seatCount - (userParticipates ? 1 : 0);
  const bots = botNameOrder.slice(0, botCount);
  return userParticipates ? [currentDraftUserName(), ...bots] : bots;
}

function renderSeatPlanPreview() {
  const seatNames = previewSeatNames();
  const userParticipates = userParticipatesToggle.checked;
  seatPlanPreview.innerHTML = seatNames
    .map((name, index) => {
      const isUser = userParticipates && index === 0;
      return `
        <div class="seat-plan-item ${isUser ? "user" : ""}">
          <span class="seat-plan-role">${isUser ? "🙋 用户位" : "🎭 系统角色"} · ${seatNoLabel(index)}</span>
          <span class="seat-plan-name">${escapeHtml(name)}</span>
        </div>
      `;
    })
    .join("");
}

function renderCreationForm() {
  const userParticipates = userParticipatesToggle.checked;
  const nextLimit = seatLimitForMode(userParticipates);
  seatCountInput.max = String(nextLimit);
  seatCountInput.value = String(clampSeatCount(seatCountInput.value, userParticipates));
  userNameField.classList.toggle("hidden", !userParticipates);
  renderSeatPlanPreview();
  renderBotPool();
}

function syncLayoutVisibility() {
  const hasSession = Boolean(sessionId);
  sessionSetupPanel.classList.toggle("hidden", hasSession);
  startHandPanel.classList.toggle("hidden", !hasSession);
  interactionGrid.classList.toggle("hidden", hasSession && !sessionUserParticipates);
  timelinePanel.classList.toggle("hidden", hasSession && sessionUserParticipates);
  bottomGrid.classList.toggle("participant-bottom-grid", hasSession && sessionUserParticipates);
  timelinePanelNote.textContent = sessionUserParticipates
    ? "玩家参与模式不显示当前手时间线，历史手请到右侧查看回放"
    : "仅显示当前手事件，历史手请到右侧历史手牌查看";
}

function hydrateSessionForm(data) {
  if (!data) {
    return;
  }
  sessionIdInput.value = data.session_id || "";
  seatCountInput.value = String(data.seat_count ?? seatCountInput.value);
  createSessionForm.querySelector('input[name="small_blind"]').value =
    data.small_blind ?? createSessionForm.querySelector('input[name="small_blind"]').value;
  createSessionForm.querySelector('input[name="big_blind"]').value =
    data.big_blind ?? createSessionForm.querySelector('input[name="big_blind"]').value;
  createSessionForm.querySelector('input[name="starting_stack"]').value =
    data.starting_stack ?? createSessionForm.querySelector('input[name="starting_stack"]').value;
  seedInput.value = data.session_seed ?? seedInput.value;
  userParticipatesToggle.checked = Boolean(data.user_participates);
  userNameInput.value = Boolean(data.user_participates) ? resolveUserNameFromState(data) : defaultUserName();
  renderCreationForm();
}

function winnerSummaryText(winners, seats = []) {
  if (!(winners || []).length) {
    return "暂无赢家信息";
  }
  return winners
    .map((winner) => `${seatDisplayName(winner.seat_id, seats)} +${winner.win_amount}`)
    .join(" · ");
}

function renderWinnerBadges(winners, seats = []) {
  return (winners || [])
    .map(
      (winner) =>
        `<span class="badge winner-badge">🏆 ${escapeHtml(seatDisplayName(winner.seat_id, seats))} +${winner.win_amount}</span>`
    )
    .join("");
}

function sessionModeLabel() {
  return sessionUserParticipates ? "用户参与" : "旁观模式";
}

function isAmountAction(action) {
  return action === "bet" || action === "raise";
}

function normalizeActionNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  return Number(value);
}

function sameActionSpec(left, right) {
  if (!left || !right) {
    return false;
  }
  return left.action === right.action
    && normalizeActionNumber(left.min) === normalizeActionNumber(right.min)
    && normalizeActionNumber(left.max) === normalizeActionNumber(right.max)
    && normalizeActionNumber(left.default) === normalizeActionNumber(right.default);
}

function findMatchingActionSpec(hand, actionSpec) {
  if (!hand || !actionSpec) {
    return null;
  }
  return (hand.available_actions || []).find((candidate) => sameActionSpec(candidate, actionSpec)) || null;
}

function actionRenderSignature(data) {
  const hand = data?.current_hand;
  return JSON.stringify({
    userParticipates: sessionUserParticipates,
    userName: sessionUserName,
    viewer: data?.viewer
      ? {
          viewer_name: data.viewer.viewer_name,
          can_act: data.viewer.can_act,
          is_folded: data.viewer.is_folded,
        }
      : null,
    hand: hand
      ? {
          hand_id: hand.hand_id,
          actor_id: hand.actor_id,
          to_call: hand.to_call,
          min_bet_to: hand.min_bet_to,
          min_raise_to: hand.min_raise_to,
          available_actions: hand.available_actions || [],
          winners: hand.winners || [],
          showdown_seat_ids: hand.showdown_seat_ids || [],
        }
      : null,
  });
}

function boardRenderSignature(hand) {
  return JSON.stringify(hand || null);
}

function sessionMetaSignature(data) {
  const hand = data?.current_hand;
  return JSON.stringify({
    session_id: data?.session_id || "",
    user_participates: Boolean(data?.user_participates),
    user_name: sessionUserName,
    session_seed: data?.session_seed ?? null,
    phase: data?.phase || "",
    last_event_id: data?.last_event_id ?? 0,
    hand: hand
      ? {
          hand_id: hand.hand_id,
          hand_no: hand.hand_no,
          street: hand.street,
          seed: hand.seed,
          winners: hand.winners || [],
          seats: hand.seats || [],
        }
      : null,
  });
}

function speakerRenderSignature() {
  return JSON.stringify({
    sessionId: sessionId || "",
    sessionUserParticipates,
    sessionUserName,
  });
}

function participantPollSignature(data) {
  return JSON.stringify({
    session_id: data?.session_id || "",
    phase: data?.phase || "",
    last_event_id: data?.last_event_id ?? 0,
    hand_id: data?.current_hand?.hand_id || "",
    user_participates: Boolean(data?.user_participates),
    user_name: resolveUserNameFromState(data),
  });
}

function updateStartHandButton(data) {
  if (!data || !sessionId) {
    startHandBtn.disabled = true;
    startHandBtn.textContent = "🃏 开始新一手";
    startHandBtn.title = "请先创建或载入牌桌";
    return;
  }
  startHandBtn.disabled = data.phase === "waiting_actor_action";
  startHandBtn.textContent =
    data.phase === "waiting_actor_action" ? "⏳ 当前手未结束" : "🃏 开始新一手";
  startHandBtn.title =
    data.phase === "waiting_actor_action"
      ? "当前有未完成手牌，请继续完成本手"
      : `系统会自动轮到 ${seatNoLabel(data.next_dealer_seat)} 当庄`;
}

function setSessionMeta(data) {
  if (!data) {
    sessionMeta.textContent = "🧭 未创建牌桌";
    copySessionBtn.classList.add("hidden");
    copySessionBtn.disabled = true;
    copySessionBtn.title = "当前没有可复制的牌桌编号";
    return;
  }
  const winnerText =
    data.phase === "hand_ended" && data.current_hand?.winners?.length
      ? ` · 🏆 ${escapeHtml(winnerSummaryText(data.current_hand.winners, data.current_hand.seats || []))}`
      : "";
  const handInfo = data.current_hand
    ? `🃏 第 ${data.current_hand.hand_no} 手 · ${streetLabel(data.current_hand.street)} · 🎲 本手种子 ${data.current_hand.seed}`
    : "🛋️ 暂无进行中牌局";
  const userInfo = sessionUserParticipates ? ` · 🙋 ${escapeHtml(sessionUserName)}` : "";
  sessionMeta.innerHTML = `
    🧭 牌桌 <strong>${escapeHtml(data.session_id)}</strong>
    · 模式 <strong>${escapeHtml(sessionModeLabel())}</strong>${userInfo}
    · 🎲 牌桌种子 <strong>${data.session_seed}</strong>
    · 阶段 <strong>${escapeHtml(phaseLabel(data.phase))}</strong>
    · ${handInfo}
    · 事件 ${data.last_event_id}${winnerText}
  `;
  copySessionBtn.classList.toggle("hidden", !sessionId);
  copySessionBtn.disabled = !sessionId;
  copySessionBtn.title = sessionId ? `复制牌桌编号 ${sessionId}` : "当前没有可复制的牌桌编号";
}

function showActionHint(message) {
  selectedActionHint.innerHTML = message;
  selectedActionHint.classList.remove("hidden");
}

function hideActionHint() {
  selectedActionHint.textContent = "";
  selectedActionHint.classList.add("hidden");
}

function resetAmountAction() {
  selectedActionSpec = null;
  amountBox.classList.add("hidden");
  actionAmount.value = "";
  actionAmount.min = 0;
  actionAmount.max = "";
  hideActionHint();
}

function showAmountAction(actionSpec, draftValue) {
  selectedActionSpec = actionSpec;
  amountBox.classList.remove("hidden");
  actionAmount.min = actionSpec.min ?? 0;
  actionAmount.max = actionSpec.max ?? "";
  actionAmount.value = draftValue !== undefined
    ? draftValue
    : String(actionSpec.default ?? actionSpec.min ?? "");
  selectedActionHint.innerHTML = `🧠 已选择 <strong>${actionLabel(actionSpec.action)}</strong>，请输入 ${actionSpec.min ?? "-"} ~ ${actionSpec.max ?? "-"} 的金额后确认。`;
  selectedActionHint.classList.remove("hidden");
}

function parseCard(cardCode) {
  if (!cardCode || cardCode.length < 2) {
    return null;
  }
  const rawRank = cardCode.slice(0, -1);
  const suitKey = cardCode.slice(-1).toLowerCase();
  const suit = SUIT_META[suitKey];
  const rankMap = { T: "10", J: "J", Q: "Q", K: "K", A: "A" };
  const rank = rankMap[rawRank] || rawRank;
  return {
    code: cardCode,
    rank,
    suit,
  };
}

function renderCard(cardCode) {
  const parsed = parseCard(cardCode);
  if (!parsed) {
    return `
      <span class="playing-card card-back" aria-label="背面牌">
        <img src="/static/card-back.svg" alt="" loading="lazy" decoding="async">
      </span>
    `;
  }
  return `
    <span class="playing-card ${parsed.suit.className}" title="${escapeHtml(parsed.suit.name)} ${escapeHtml(parsed.rank)}">
      <span class="corner">${escapeHtml(parsed.rank)}<span>${parsed.suit.symbol}</span></span>
      <span class="suit-center">${parsed.suit.emoji}</span>
      <span class="corner bottom">${escapeHtml(parsed.rank)}<span>${parsed.suit.symbol}</span></span>
      <span class="card-note">${escapeHtml(parsed.code)}</span>
    </span>
  `;
}

function renderCardRow(cards, extraClass = "") {
  const classes = ["playing-cards", extraClass].filter(Boolean).join(" ");
  return `<div class="${classes}">${(cards || []).map((card) => renderCard(card)).join("")}</div>`;
}

function renderFaceDownCardRow(count = 2, extraClass = "") {
  return renderCardRow(Array.from({ length: count }, () => null), extraClass);
}

function seatBadges(hand, seat) {
  const badges = [];
  if (seat.seat_no === hand.dealer_seat) {
    badges.push("🎩 庄");
  }
  if (seat.seat_no === hand.small_blind_seat) {
    badges.push("🪙 小盲");
  }
  if (seat.seat_no === hand.big_blind_seat) {
    badges.push("🪙 大盲");
  }
  if (seat.seat_id === hand.actor_id) {
    badges.push("🎯 行动中");
  }
  if (seat.is_winner) {
    badges.push(`🏆 +${seat.win_amount}`);
  }
  return badges.map((badge) => `<span class="badge">${badge}</span>`).join("");
}

function seatFlags(seat) {
  const flags = [];
  if (seat.is_folded) {
    flags.push("🛑 已弃牌");
  }
  if (seat.is_all_in) {
    flags.push("🔥 已全下");
  }
  if (seat.in_hand && !seat.is_folded) {
    flags.push("🫶 仍在手");
  }
  if (seat.showdown_competing) {
    flags.push("🪞 参与比牌");
  }
  return flags.map((flag) => `<span class="badge">${flag}</span>`).join("");
}

function chatStreetLabel(value) {
  if (!value) {
    return "牌局中";
  }
  return streetLabel(value);
}

function chatContextLabel(item) {
  const handText = item.hand_no ? `第 ${item.hand_no} 手` : "最近对话";
  return `${handText} · ${chatStreetLabel(item.street)}`;
}

function renderSeatSpeechItem(item, extraClass = "") {
  return `
    <div class="seat-chat-item ${extraClass}">
      <div class="seat-chat-meta">${escapeHtml(chatContextLabel(item))} · ${escapeHtml(formatDateTime(item.created_at))}</div>
      <div class="seat-chat-text">${escapeHtml(item.text)}</div>
    </div>
  `;
}

function renderSeatSpeech(seatId) {
  const chats = recentSeatChats[seatId] || [];
  if (!chats.length) {
    return `
      <div class="seat-chat-panel seat-chat-empty">
        <div class="seat-chat-head">💬 最近发言</div>
        <div class="seat-chat-placeholder">最近还没有发言</div>
      </div>
    `;
  }
  return `
    <div class="seat-chat-panel">
      <div class="seat-chat-head">💬 最近发言</div>
      <div class="seat-chat-scroll">
        ${chats.map((item, index) => renderSeatSpeechItem(item, index === 0 ? "latest" : "")).join("")}
      </div>
    </div>
  `;
}

function rebuildSeatChatsFromSessionEvents() {
  const handMeta = new Map();
  const currentHand = currentState?.current_hand;
  if (currentHand?.hand_id) {
    handMeta.set(currentHand.hand_id, {
      hand_no: currentHand.hand_no,
      street: currentHand.street,
    });
  }
  handIndex.forEach((item, handId) => {
    if (!handMeta.has(handId)) {
      handMeta.set(handId, { hand_no: item.hand_no, street: null });
    }
  });

  const bySeat = {};
  sessionEvents.forEach((event) => {
    if (!event.hand_id) {
      return;
    }

    const nextMeta = handMeta.get(event.hand_id) || { hand_no: null, street: null };
    if (event.event_type === "hand_started") {
      nextMeta.hand_no = event.payload?.hand_no ?? nextMeta.hand_no;
      nextMeta.street = "preflop";
      handMeta.set(event.hand_id, nextMeta);
    }
    if (event.event_type === "street_changed") {
      nextMeta.street = event.payload?.street ?? nextMeta.street;
      handMeta.set(event.hand_id, nextMeta);
    }
    if (event.event_type === "showdown_started") {
      nextMeta.street = "showdown";
      handMeta.set(event.hand_id, nextMeta);
    }
    if (event.event_type !== "chat_sent") {
      return;
    }

    const speakerId = event.payload?.speaker_id;
    if (!speakerId) {
      return;
    }
    if (!bySeat[speakerId]) {
      bySeat[speakerId] = [];
    }
    bySeat[speakerId].push({
      event_id: event.event_id,
      hand_id: event.hand_id,
      hand_no: nextMeta.hand_no,
      street: nextMeta.street,
      created_at: event.created_at,
      text: event.payload?.text || "",
    });
  });

  Object.keys(bySeat).forEach((seatId) => {
    bySeat[seatId] = bySeat[seatId].reverse();
  });
  recentSeatChats = bySeat;
}

function rebuildSeatChatsFromCurrentState() {
  const hand = currentState?.current_hand;
  const bySeat = {};
  (hand?.chat_messages || []).forEach((item) => {
    if (!item.speaker_id) {
      return;
    }
    if (!bySeat[item.speaker_id]) {
      bySeat[item.speaker_id] = [];
    }
    bySeat[item.speaker_id].push({
      event_id: item.event_id,
      hand_id: hand?.hand_id,
      hand_no: hand?.hand_no,
      street: hand?.street,
      created_at: item.created_at,
      text: item.text || "",
    });
  });
  Object.keys(bySeat).forEach((seatId) => {
    bySeat[seatId] = bySeat[seatId].reverse();
  });
  recentSeatChats = bySeat;
}

function renderBoardAndSeats(hand) {
  boardArea.innerHTML = "";
  tableArea.innerHTML = "";
  tableArea.className = "table-grid";
  if (!hand) {
    boardArea.innerHTML = '<div class="empty-state">🪑 还没有开始 hand。</div>';
    return;
  }

  tableArea.className = `table-grid seats-${Math.min(hand.seats.length, 9)}`;
  const actorText = hand.actor_id
    ? `🎯 轮到 ${escapeHtml(seatDisplayWithNo(hand.actor_id, hand.seats || []))}`
    : "🏁 本手已结束";
  const winnerStrip = (hand.winners || []).length
    ? `
      <div class="winner-strip">
        <div class="winner-headline">🏆 本手赢家</div>
        <div class="badge-row">${renderWinnerBadges(hand.winners, hand.seats || [])}</div>
      </div>
    `
    : "";
  const showdownStrip = (hand.showdown_seat_ids || []).length
    ? `
      <div class="showdown-strip">
        <span class="info-chip">🪞 比牌玩家 ${(hand.showdown_seat_ids || [])
          .map((seatId) => escapeHtml(seatDisplayName(seatId, hand.seats || [])))
          .join(" · ")}</span>
      </div>
    `
    : "";
  const bettingInfo = hand.actor_id
    ? `
      <div class="chip-line">
        <span class="info-chip">📞 需跟注 ${hand.to_call ?? "-"}</span>
        <span class="info-chip">💰 最小下注 ${hand.min_bet_to ?? "-"}</span>
        <span class="info-chip">🚀 最小加注 ${hand.min_raise_to ?? "-"}</span>
      </div>
    `
    : "";
  boardArea.innerHTML = `
    <div class="table-overview">
      <div class="overview-main">
        <div class="chip-line">
          <span class="info-chip">🃏 第 ${hand.hand_no} 手</span>
          <span class="info-chip">${STREET_META[hand.street]?.emoji || "🛣️"} ${streetLabel(hand.street)}</span>
          <span class="info-chip">💰 底池 ${hand.pot_total}</span>
          <span class="info-chip">🎲 本手种子 ${hand.seed}</span>
        </div>
        <div class="chip-line">
          <span class="info-chip">🎩 庄位 ${seatNoLabel(hand.dealer_seat)}</span>
          <span class="info-chip">🪙 小盲 ${seatNoLabel(hand.small_blind_seat)}</span>
          <span class="info-chip">🪙 大盲 ${seatNoLabel(hand.big_blind_seat)}</span>
        </div>
      </div>
      <div class="overview-main">
        <div class="chip-line">
          <span class="info-chip">${actorText}</span>
        </div>
        ${bettingInfo}
      </div>
    </div>
    ${winnerStrip}
    ${showdownStrip}
    <div class="board-cards">
      ${renderCardRow(hand.board_cards)}
    </div>
  `;

  hand.seats.forEach((seat) => {
    const seatNode = document.createElement("div");
    const seatClasses = ["seat"];
    if (seat.seat_id === hand.actor_id) {
      seatClasses.push("active");
    }
    if (seat.is_winner) {
      seatClasses.push("winner");
    } else if (seat.showdown_competing) {
      seatClasses.push("showdown");
    }
    if (seat.is_folded) {
      seatClasses.push("folded");
    }
    const resultBlock = seat.showdown_competing
      ? `
        <div class="seat-result">
          <div class="seat-result-line">🪞 ${escapeHtml(seat.best_hand_label || "已参与比牌")}</div>
          ${renderCardRow(seat.best_hand_cards || [], "compact")}
        </div>
      `
      : seat.is_winner
        ? `<div class="seat-result"><div class="seat-result-line">🏆 赢得 ${seat.win_amount}</div></div>`
        : "";
    seatNode.className = seatClasses.join(" ");
    seatNode.innerHTML = `
      <div class="seat-header">
        <div class="seat-header-main">
          <div class="seat-title">
            <strong>${escapeHtml(seat.display_name)}</strong>
            <span class="seat-subline">🪑 ${seatNoLabel(seat.seat_no)}</span>
          </div>
          <div class="seat-summary">
            <span class="badge">💵 ${seat.stack}</span>
            <span class="badge">📍 当街 ${seat.contribution_street}</span>
            <span class="badge">🪙 本手 ${seat.contribution_total}</span>
            ${seatFlags(seat)}
          </div>
        </div>
        <div class="badge-row">${seatBadges(hand, seat)}</div>
      </div>
      <div class="seat-body">
        ${seat.hole_cards_visible === false ? renderFaceDownCardRow() : renderCardRow(seat.hole_cards)}
        ${renderSeatSpeech(seat.seat_id)}
      </div>
      ${resultBlock}
    `;
    tableArea.appendChild(seatNode);
  });
}

function renderActions(hand) {
  const preservedAmountDraft = !amountBox.classList.contains("hidden") ? actionAmount.value : undefined;
  const preservedActionSpec = findMatchingActionSpec(hand, selectedActionSpec);
  actionButtons.innerHTML = "";

  if (!hand) {
    resetAmountAction();
    actionMeta.textContent = "🎮 当前没有 hand。";
    return;
  }

  if (!sessionUserParticipates && sessionId) {
    resetAmountAction();
    actionMeta.textContent = "👀 当前为旁观模式，这个页面不提供动作操作。";
    showActionHint("旁观模式下可查看当前对局与历史回放，但不能在本页面提交动作。");
    return;
  }

  if (!hand.actor_id && !(hand.available_actions || []).length) {
    resetAmountAction();
    actionMeta.innerHTML = `
      <strong>🏁 本手已结束</strong>
      <br>
      <strong>🏆 赢家：</strong> ${escapeHtml(winnerSummaryText(hand.winners || [], hand.seats || []))}
    `;
    showActionHint(
      (hand.showdown_seat_ids || []).length
        ? `🪞 已完成比牌：${(hand.showdown_seat_ids || [])
          .map((seatId) => seatDisplayName(seatId, hand.seats || []))
          .join(" · ")}。历史手牌与回放已可查看。`
        : "📚 本手已经归档到历史手牌，可直接查看回放。"
    );
    return;
  }

  const viewer = currentState?.viewer;
  if (!viewer) {
    resetAmountAction();
    actionMeta.textContent = "🎮 当前未绑定玩家视角。";
    showActionHint("请使用“用户参与”模式创建或载入会话后，再在这里操作。");
    return;
  }

  if (!viewer.can_act) {
    resetAmountAction();
    actionMeta.innerHTML = `
      <strong>🙋 当前用户：</strong> ${escapeHtml(sessionUserName)}
      <br>
      <strong>🎯 当前行动者：</strong> ${escapeHtml(seatDisplayWithNo(hand.actor_id || "", hand.seats || []))}
    `;
    if (viewer.is_folded) {
      showActionHint("你已在本手弃牌，当前只能继续聊天并等待本手结束。");
    } else {
      showActionHint("当前还没有轮到你行动，等待其它玩家通过外部客户端或 API 继续推进。");
    }
    return;
  }

  if (!preservedActionSpec) {
    resetAmountAction();
  }
  actionMeta.innerHTML = `
    <strong>🙋 当前用户：</strong> ${escapeHtml(sessionUserName)}
    <br>
    <strong>📞 需跟注：</strong> ${hand.to_call ?? "-"}
    · <strong>💰 最小下注：</strong> ${hand.min_bet_to ?? "-"}
    · <strong>🚀 最小加注：</strong> ${hand.min_raise_to ?? "-"}
  `;
  (hand.available_actions || []).forEach((action) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = actionLabel(action.action);
    button.addEventListener("click", () => handleActionChoice(action));
    actionButtons.appendChild(button);
  });
  if (preservedActionSpec && isAmountAction(preservedActionSpec.action)) {
    showAmountAction(preservedActionSpec, preservedAmountDraft);
    return;
  }
  hideActionHint();
}

function renderSpeakerDisplay() {
  if (!sessionUserParticipates || !sessionId) {
    speakerNameDisplay.textContent = "💬 当前没有用户参与";
    return;
  }
  speakerNameDisplay.textContent = `💬 当前发言人：${sessionUserName}`;
}

function handleActionChoice(actionSpec) {
  if (isAmountAction(actionSpec.action)) {
    showAmountAction(actionSpec);
    return;
  }
  submitAction(actionSpec).catch((error) => showBanner(error.message));
}

async function submitAction(actionSpec, amountOverride = null) {
  if (!sessionId || !sessionUserParticipates || !sessionUserName) {
    return;
  }
  const payload = {
    actor_name: sessionUserName,
    action: actionSpec.action,
  };
  if (actionSpec.action === "bet" || actionSpec.action === "raise") {
    payload.amount = Number(amountOverride ?? actionAmount.value ?? actionSpec.default ?? 0);
  }
  await api(`/api/v1/sessions/${sessionId}/actions`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  resetAmountAction();
  const state = await refreshState();
  await refreshHistory();
  if (state?.phase === "hand_ended" && state.current_hand?.hand_id) {
    await loadReplay(state.current_hand.hand_id);
  }
}

function eventSummary(event, seats = allKnownSeats()) {
  const payload = event.payload || {};
  switch (event.event_type) {
    case "session_created":
      return `🪑 新牌桌已创建，座位数 ${payload.seat_count}，盲注 ${payload.small_blind}/${payload.big_blind}，牌桌种子=${payload.session_seed}。`;
    case "hand_started":
      return `🃏 第 ${payload.hand_no} 手开始，庄位 ${seatNoLabel(payload.dealer_seat)}，本手种子=${payload.seed}。`;
    case "waiting_actor_action":
      return `🎯 轮到 ${seatDisplayName(payload.actor_id, seats)} 在 ${streetLabel(payload.street)} 行动，需跟注 ${payload.to_call}。`;
    case "board_dealt":
      return `🃏 ${streetLabel(payload.street)} 发牌：${(payload.cards || []).join(" ")}。`;
    case "street_changed":
      return `🛣️ 进入 ${streetLabel(payload.street)}。`;
    case "showdown_started":
      return "🪞 进入摊牌阶段。";
    case "hand_ended":
      return `🏁 本手结束，底池 ${payload.pot_total}，赢家：${winnerSummaryText(payload.winners || [], seats)}。`;
    case "blind_posted":
      return `🪙 ${seatDisplayName(payload.actor_id, seats)} 投入盲注 ${payload.amount}。`;
    case "action_applied":
      return `${actionLabel(payload.action)} · ${seatDisplayName(payload.actor_id, seats)} 在 ${streetLabel(payload.street)} 执行动作${payload.amount ? ` ${payload.amount}` : ""}。`;
    case "pot_awarded":
      return `🏆 ${seatDisplayName(payload.seat_id, seats)} 获得 ${payload.amount}。`;
    case "chat_sent":
      return `💬 ${seatDisplayName(payload.speaker_id, seats)}: ${payload.text}`;
    default:
      return `${EVENT_META[event.event_type]?.emoji || "🎲"} ${EVENT_META[event.event_type]?.label || event.event_type}`;
  }
}

function timelineItemMarkup(event, seats = allKnownSeats(), includeDetails = false) {
  const meta = EVENT_META[event.event_type] || { emoji: "🎲", label: event.event_type };
  return `
    <div class="timeline-top">
      <div class="timeline-head">
        <span class="timeline-tag">${meta.emoji} ${escapeHtml(meta.label)}</span>
        <span class="timeline-channel">${escapeHtml(channelLabel(event.channel))}</span>
      </div>
      <span class="timeline-time">#${event.event_id} · ${escapeHtml(formatDateTime(event.created_at))}</span>
    </div>
    <div class="event-summary">${escapeHtml(eventSummary(event, seats))}</div>
    ${includeDetails
      ? `
        <details class="event-detail-wrap">
          <summary>查看事件详情</summary>
          <pre class="event-detail">${escapeHtml(JSON.stringify(event.payload, null, 2))}</pre>
        </details>
      `
      : ""}
  `;
}

function appendTimeline(event) {
  const node = document.createElement("div");
  node.className = "timeline-item";
  node.innerHTML = timelineItemMarkup(event, allKnownSeats(), true);
  timeline.prepend(node);
}

function currentTimelineEvents() {
  const currentHandId = currentState?.current_hand?.hand_id;
  if (!currentHandId) {
    return [];
  }
  return sessionEvents.filter((event) => event.hand_id === currentHandId);
}

function renderTimeline() {
  timeline.innerHTML = "";
  if (sessionUserParticipates && sessionId) {
    timeline.innerHTML = '<div class="empty-state">🙈 用户参与模式下不显示当前手时间线。</div>';
    return;
  }
  const events = currentTimelineEvents();
  if (!events.length) {
    timeline.innerHTML = currentState?.current_hand?.hand_id
      ? '<div class="empty-state">🕒 当前手暂时时间线为空，后续动作和聊天会显示在这里。</div>'
      : '<div class="empty-state">🕒 当前只显示本手时间线，开始新一手后会在这里展示进展。</div>';
    return;
  }
  events.forEach((event) => appendTimeline(event));
}

function isReplayableHand(item) {
  if (!item) {
    return false;
  }
  const phase = String(item.phase || "").toLowerCase();
  return phase === "ended"
    || phase === "hand_ended"
    || Boolean(item.ended_at)
    || Boolean((item.winners || []).length);
}

function renderState(data) {
  currentState = data;
  applySessionContext(data);
  lastEventId = data.last_event_id;
  updateHandIndex();
  if (sessionUserParticipates) {
    rebuildSeatChatsFromCurrentState();
  }
  syncLayoutVisibility();
  const nextSessionMetaSignature = sessionMetaSignature(data);
  if (renderSignatures.sessionMeta !== nextSessionMetaSignature) {
    setSessionMeta(data);
    renderSignatures.sessionMeta = nextSessionMetaSignature;
  }
  updateStartHandButton(data);
  const nextBoardSignature = boardRenderSignature(data.current_hand);
  if (renderSignatures.board !== nextBoardSignature) {
    renderBoardAndSeats(data.current_hand);
    renderSignatures.board = nextBoardSignature;
  }
  const nextActionSignature = actionRenderSignature(data);
  if (renderSignatures.actions !== nextActionSignature) {
    renderActions(data.current_hand);
    renderSignatures.actions = nextActionSignature;
  }
  const nextSpeakerSignature = speakerRenderSignature();
  if (renderSignatures.speaker !== nextSpeakerSignature) {
    renderSpeakerDisplay();
    renderSignatures.speaker = nextSpeakerSignature;
  }
  return data;
}

async function refreshState() {
  if (!sessionId) {
    return null;
  }
  const data = await api(buildStatePath(sessionId));
  renderState(data);
  return data;
}

async function refreshHistory() {
  if (!sessionId) {
    return null;
  }
  const data = await api(`/api/v1/sessions/${sessionId}/hands?limit=20&offset=0`);
  updateHandIndex(data.items || []);
  historyList.innerHTML = "";
  if (!data.items.length) {
    historyList.innerHTML = '<div class="empty-state">📚 暂无历史手牌。</div>';
    return data;
  }
  data.items.forEach((item) => {
    const knownSeats = allKnownSeats();
    const winners = (item.winners || [])
      .map(
        (winner) =>
          `${seatDisplayName(winner.seat_id, knownSeats)} +${winner.win_amount}`
      )
      .join(" · ");
    const canReplay = isReplayableHand(item);
    const row = document.createElement("div");
    row.className = "history-item";
    row.innerHTML = `
      <div class="history-top">
        <div class="history-main">
          <div class="history-title">🃏 第 ${item.hand_no} 手</div>
          <div class="history-subline" title="${escapeHtml(item.hand_id)}">${escapeHtml(item.hand_id)}</div>
        </div>
        <button type="button" data-hand-id="${escapeHtml(item.hand_id)}" ${canReplay ? "" : "disabled"}>
          ${canReplay ? "🎞️ 查看回放" : "⏳ 进行中"}
        </button>
      </div>
      <div class="chip-line">
        <span class="badge">${canReplay ? "✅ 已结束" : "🟢 进行中"}</span>
        <span class="badge">🏆 赢家 ${escapeHtml(winners || (item.winner_ids || []).join(", ") || "-")}</span>
        <span class="badge">💰 底池 ${item.pot_total}</span>
        <span class="badge">⚡ 动作 ${item.action_count}</span>
        <span class="badge">💬 聊天 ${item.chat_count}</span>
      </div>
      <div class="history-subline">🕒 ${escapeHtml(item.started_at)} → ${escapeHtml(item.ended_at || "-")}</div>
    `;
    if (canReplay) {
      row.querySelector("button").addEventListener("click", () => loadReplay(item.hand_id));
    }
    historyList.appendChild(row);
  });
  return data;
}

async function loadRecentEvents() {
  if (!sessionId || sessionUserParticipates) {
    renderTimeline();
    return [];
  }
  const sinceEventId = Math.max(0, lastEventId - 200);
  const data = await api(
    `/api/v1/sessions/${sessionId}/events?since_event_id=${sinceEventId}&limit=200`
  );
  rememberSessionEvents(data.events, true);
  renderTimeline();
  rebuildSeatChatsFromSessionEvents();
  renderBoardAndSeats(currentState?.current_hand);
  return data.events || [];
}

async function activateSession(targetSessionId, successMessage = "") {
  const normalized = String(targetSessionId || "").trim();
  if (!normalized) {
    showBanner("请输入牌桌编号");
    return null;
  }

  const bootstrap = await api(`/api/v1/sessions/${normalized}/state`);
  const initialUserParticipates = Boolean(bootstrap.user_participates);
  const initialUserName = initialUserParticipates ? resolveUserNameFromState(bootstrap) : "";
  const state = initialUserParticipates
    ? await api(buildStatePath(normalized, initialUserParticipates, initialUserName))
    : bootstrap;

  handIndex = new Map();
  sessionEvents = [];
  recentSeatChats = {};
  sessionId = normalized;
  resetRenderSignatures();
  renderState(state);
  hydrateSessionForm(state);
  await refreshHistory();
  await loadRecentEvents();
  startPolling();

  if (state.phase === "hand_ended" && state.current_hand?.hand_id) {
    await loadReplay(state.current_hand.hand_id);
  } else {
    resetReplayPlaceholder("🪄 选择一手已结束牌局查看回放。");
  }

  if (successMessage) {
    showBanner(successMessage);
  }
  return state;
}

function renderReplay(data) {
  const replaySeats = data.final_state?.seats || [];
  const winners = (data.winners || [])
    .map(
      (winner) =>
        `<span class="badge">🏆 ${escapeHtml(seatDisplayName(winner.seat_id, replaySeats))} +${winner.win_amount}</span>`
    )
    .join("");
  const showdownSeats = replaySeats
    .filter((seat) => seat.showdown_competing)
    .map(
      (seat) => `
        <div class="replay-card replay-seat-card ${seat.is_winner ? "winner" : "showdown"}">
          <div class="replay-section-head">
            <strong>${seat.is_winner ? "🏆" : "🪞"} ${escapeHtml(seat.display_name || seat.seat_id)}</strong>
            <span class="replay-meta">${escapeHtml(seatNoLabel(seat.seat_no))}${seat.win_amount ? ` · +${seat.win_amount}` : ""}</span>
          </div>
          <div class="action-line">${escapeHtml(seat.best_hand_label || "进入摊牌比较")}</div>
          ${renderCardRow(seat.hole_cards || [], "compact")}
          ${seat.best_hand_cards?.length ? renderCardRow(seat.best_hand_cards, "compact") : ""}
        </div>
      `
    )
    .join("");
  const replayTimeline = (data.timeline || [])
    .map((item) => {
      return `
        <div class="timeline-item replay-timeline-item">
          ${timelineItemMarkup(item, replaySeats)}
        </div>
      `;
    })
    .join("");

  const stacks = Object.entries(data.final_stacks || {})
    .map(
      ([seatId, stack]) => `
        <div class="replay-card">
          <div class="stack-line">💵 <strong>${escapeHtml(seatDisplayName(seatId, replaySeats))}</strong> · ${stack}</div>
        </div>
      `
    )
    .join("");

  replayView.innerHTML = `
    <div class="replay-card">
      <div class="replay-section-head">
        <div>
          <div class="replay-headline">🎞️ 第 ${data.hand_no} 手</div>
          <div class="replay-meta" title="${escapeHtml(data.hand_id)}">${escapeHtml(data.hand_id)}</div>
        </div>
        <div class="badge-row">
          <span class="badge">🎩 庄位 ${seatNoLabel(data.dealer_seat)}</span>
          <span class="badge">🎲 牌桌种子 ${data.session_seed}</span>
          <span class="badge">🌱 本手种子 ${data.seed}</span>
        </div>
      </div>
      <div class="chip-line">${winners || '<span class="badge">🏆 暂无赢家信息</span>'}</div>
      ${renderCardRow(data.board_cards)}
    </div>
    <div class="replay-card">
      <div class="replay-section-head">
        <strong>🪞 摊牌对比</strong>
        <span class="replay-meta">${showdownSeats ? "已展示参与比较座位" : "无摊牌比较"}</span>
      </div>
      <div class="replay-list">${showdownSeats || '<div class="empty-state">本手未进入比牌阶段。</div>'}</div>
    </div>
    <div class="replay-card">
      <div class="replay-section-head">
        <strong>🕒 对局时间线</strong>
        <span class="replay-meta">${(data.timeline || []).length} 条事件</span>
      </div>
      <div class="replay-list replay-timeline">${replayTimeline || '<div class="empty-state">暂无回放事件。</div>'}</div>
    </div>
    <div class="replay-card">
      <div class="replay-section-head">
        <strong>💼 最终筹码</strong>
        <span class="replay-meta">结算后</span>
      </div>
      <div class="replay-list">${stacks}</div>
    </div>
  `;
  replayView.dataset.handId = data.hand_id;
}

async function loadReplay(handId) {
  try {
    const data = await api(buildReplayPath(handId));
    renderReplay(data);
    replayView.scrollTop = 0;
  } catch (error) {
    showBanner(error.message);
  }
}

async function pollPublicEvents() {
  if (!sessionId) {
    return;
  }
  try {
    const data = await api(
      `/api/v1/sessions/${sessionId}/events?since_event_id=${lastEventId}&limit=200`
    );
    if (!(data.events || []).length) {
      return;
    }
    let needsStateRefresh = false;
    data.events.forEach((event) => {
      lastEventId = Math.max(lastEventId, event.event_id);
      if (event.channel !== "chat") {
        needsStateRefresh = true;
      }
    });
    rememberSessionEvents(data.events);
    if (needsStateRefresh) {
      const state = await refreshState();
      await refreshHistory();
      if (state?.phase === "hand_ended" && state.current_hand?.hand_id) {
        if (replayView.dataset.handId !== state.current_hand.hand_id) {
          await loadReplay(state.current_hand.hand_id);
        }
      }
    }
    renderTimeline();
    rebuildSeatChatsFromSessionEvents();
    renderBoardAndSeats(currentState?.current_hand);
  } catch (error) {
    showBanner(error.message);
  }
}

async function pollParticipantView() {
  if (!sessionId) {
    return;
  }
  try {
    const data = await api(buildStatePath(sessionId));
    if (participantPollSignature(currentState) === participantPollSignature(data)) {
      return;
    }
    const state = renderState(data);
    await refreshHistory();
    if (state?.phase === "hand_ended" && state.current_hand?.hand_id) {
      if (replayView.dataset.handId !== state.current_hand.hand_id) {
        await loadReplay(state.current_hand.hand_id);
      }
    }
  } catch (error) {
    showBanner(error.message);
  }
}

function startPolling() {
  clearInterval(pollHandle);
  if (!sessionId) {
    return;
  }
  pollHandle = setInterval(() => {
    if (sessionUserParticipates) {
      pollParticipantView();
      return;
    }
    pollPublicEvents();
  }, pollInterval);
}

submitAmountAction.addEventListener("click", () => {
  if (!selectedActionSpec) {
    showBanner("请先选择一个金额动作");
    return;
  }
  submitAction(selectedActionSpec, Number(actionAmount.value)).catch((error) => showBanner(error.message));
});

createSessionForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = {
    session_id: form.get("session_id") || null,
    seat_count: clampSeatCount(form.get("seat_count"), userParticipatesToggle.checked),
    small_blind: Number(form.get("small_blind")),
    big_blind: Number(form.get("big_blind")),
    starting_stack: Number(form.get("starting_stack")),
    seed: form.get("seed") === "" ? null : Number(form.get("seed")),
    user_participates: userParticipatesToggle.checked,
    seat_names: previewSeatNames(),
  };
  try {
    const data = await api("/api/v1/sessions", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    await activateSession(data.session_id, "新牌桌已创建");
  } catch (error) {
    if (payload.session_id && error.status === 409) {
      activateSession(payload.session_id, "已载入现有牌桌").catch((loadError) =>
        showBanner(loadError.message)
      );
      return;
    }
    showBanner(error.message);
  }
});

document.getElementById("startHandForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!sessionId) {
    showBanner("请先创建或载入牌桌");
    return;
  }
  if (currentState?.phase === "waiting_actor_action") {
    showBanner("当前有未完成手牌，请继续完成本手");
    return;
  }
  try {
    await api(`/api/v1/sessions/${sessionId}/hands`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    await refreshState();
    await refreshHistory();
    await loadRecentEvents();
    resetReplayPlaceholder("🪄 当前手正在进行，回放会在本手结束后生成。");
  } catch (error) {
    showBanner(error.message);
  }
});

document.getElementById("chatForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!sessionId || !sessionUserParticipates || !sessionUserName) {
    showBanner("当前模式不支持在本页面发送聊天");
    return;
  }
  try {
    await api(`/api/v1/sessions/${sessionId}/chat`, {
      method: "POST",
      body: JSON.stringify({
        speaker_name: sessionUserName,
        text: document.getElementById("chatText").value,
      }),
    });
    document.getElementById("chatText").value = "";
    await refreshState();
  } catch (error) {
    showBanner(error.message);
  }
});

document.getElementById("refreshBtn").addEventListener("click", () => {
  refreshState().catch((error) => showBanner(error.message));
  refreshHistory().catch((error) => showBanner(error.message));
  loadRecentEvents().catch((error) => showBanner(error.message));
});

copySessionBtn.addEventListener("click", async () => {
  if (!sessionId) {
    showBanner("当前没有可复制的牌桌编号");
    return;
  }
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(sessionId);
    } else {
      const fallbackInput = document.createElement("input");
      fallbackInput.value = sessionId;
      fallbackInput.setAttribute("readonly", "readonly");
      fallbackInput.style.position = "fixed";
      fallbackInput.style.opacity = "0";
      document.body.appendChild(fallbackInput);
      fallbackInput.select();
      document.execCommand("copy");
      fallbackInput.remove();
    }
    showBanner(`已复制牌桌编号 ${sessionId}`);
  } catch (error) {
    showBanner("复制失败，请手动复制牌桌编号");
  }
});

randomSessionBtn.addEventListener("click", () => {
  sessionIdInput.value = generateRandomSessionId();
});

randomSeedBtn.addEventListener("click", () => {
  seedInput.value = generateRandomSeed();
});

loadSessionBtn.addEventListener("click", () => {
  activateSession(sessionIdInput.value, "已载入现有牌桌").catch((error) =>
    showBanner(error.message)
  );
});

seatCountInput.addEventListener("input", renderCreationForm);
userParticipatesToggle.addEventListener("change", () => {
  botNameOrder = shuffleArray(configuredBotNames);
  renderCreationForm();
});
userNameInput.addEventListener("input", renderCreationForm);

renderCreationForm();
syncLayoutVisibility();
updateStartHandButton(null);
renderActions(null);
renderSpeakerDisplay();
renderTimeline();
