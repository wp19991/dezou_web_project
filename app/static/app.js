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

let sessionId = "";
let lastEventId = 0;
let pollHandle = null;
let currentState = null;
let selectedActionSpec = null;
let seatNameDrafts = [];

const banner = document.getElementById("banner");
const sessionMeta = document.getElementById("sessionMeta");
const tableArea = document.getElementById("tableArea");
const boardArea = document.getElementById("boardArea");
const actionMeta = document.getElementById("actionMeta");
const actionButtons = document.getElementById("actionButtons");
const amountBox = document.getElementById("amountBox");
const actionAmount = document.getElementById("actionAmount");
const timeline = document.getElementById("timeline");
const historyList = document.getElementById("historyList");
const replayView = document.getElementById("replayView");
const speakerId = document.getElementById("speakerId");
const selectedActionHint = document.getElementById("selectedActionHint");
const submitAmountAction = document.getElementById("submitAmountAction");
const createSessionForm = document.getElementById("createSessionForm");
const seatCountInput = createSessionForm.querySelector('input[name="seat_count"]');
const seatNamesList = document.getElementById("seatNamesList");

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok || data.ok === false) {
    throw new Error(data?.error?.message || "请求失败");
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

function defaultSeatName(index) {
  return `玩家 ${index + 1}`;
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

function syncSeatNameDrafts() {
  Array.from(seatNamesList.querySelectorAll("input[data-seat-index]")).forEach((input) => {
    const seatIndex = Number(input.dataset.seatIndex);
    seatNameDrafts[seatIndex] = input.value.trim() || defaultSeatName(seatIndex);
  });
}

function renderSeatNameInputs() {
  syncSeatNameDrafts();
  const count = Math.min(9, Math.max(2, Number(seatCountInput.value) || 2));
  seatNamesList.innerHTML = Array.from({ length: count }, (_, index) => {
    const value = seatNameDrafts[index] || defaultSeatName(index);
    return `
      <label class="seat-name-item">
        <span>🪑 ${index + 1} 号位</span>
        <input
          type="text"
          maxlength="32"
          value="${escapeHtml(value)}"
          data-seat-index="${index}"
          placeholder="${defaultSeatName(index)}"
        >
      </label>
    `;
  }).join("");
}

function collectSeatNames() {
  syncSeatNameDrafts();
  return Array.from({ length: Math.min(9, Math.max(2, Number(seatCountInput.value) || 2)) }, (_, index) => {
    return seatNameDrafts[index] || defaultSeatName(index);
  });
}

function showActionHint(message) {
  selectedActionHint.textContent = message;
  selectedActionHint.classList.remove("hidden");
}

function hideActionHint() {
  selectedActionHint.textContent = "";
  selectedActionHint.classList.add("hidden");
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
    return `<span class="playing-card"><span class="suit-center">🂠</span></span>`;
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

function renderWinnerBadges(winners, seats = []) {
  return (winners || [])
    .map(
      (winner) =>
        `<span class="badge winner-badge">🏆 ${escapeHtml(seatDisplayName(winner.seat_id, seats))} +${winner.win_amount}</span>`
    )
    .join("");
}

function winnerSummaryText(winners, seats = []) {
  if (!(winners || []).length) {
    return "暂无赢家信息";
  }
  return winners
    .map((winner) => `${seatDisplayName(winner.seat_id, seats)} +${winner.win_amount}`)
    .join(" · ");
}

function setSessionMeta(data) {
  const winnerText =
    data.phase === "hand_ended" && data.current_hand?.winners?.length
      ? ` · 🏆 ${escapeHtml(winnerSummaryText(data.current_hand.winners, data.current_hand.seats || []))}`
      : "";
  const handInfo = data.current_hand
    ? `🃏 第 ${data.current_hand.hand_no} 手 · ${streetLabel(data.current_hand.street)} · 🎲 本手种子 ${data.current_hand.seed}`
    : "🛋️ 暂无进行中牌局";
  sessionMeta.innerHTML = `
    🧭 牌桌 <strong>${escapeHtml(data.session_id)}</strong>
    · 🎲 牌桌种子 <strong>${data.session_seed}</strong>
    · 阶段 <strong>${escapeHtml(phaseLabel(data.phase))}</strong>
    · ${handInfo}
    · 事件 ${data.last_event_id}${winnerText}
  `;
}

function renderState(data) {
  currentState = data;
  lastEventId = data.last_event_id;
  setSessionMeta(data);
  renderBoardAndSeats(data.current_hand);
  renderActions(data.current_hand);
  renderSpeakerOptions(data.current_hand);
  return data;
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
        <div class="seat-title">
          <strong>${escapeHtml(seat.display_name)}</strong>
          <span class="seat-subline">🪑 ${seatNoLabel(seat.seat_no)}</span>
        </div>
        <div class="badge-row">${seatBadges(hand, seat)}</div>
      </div>
      <div class="seat-meta">
        <span class="badge">💵 ${seat.stack}</span>
        <span class="badge">📍 当街 ${seat.contribution_street}</span>
        <span class="badge">🪙 本手 ${seat.contribution_total}</span>
      </div>
      <div class="seat-flags">${seatFlags(seat)}</div>
      ${renderCardRow(seat.hole_cards)}
      ${resultBlock}
    `;
    tableArea.appendChild(seatNode);
  });
}

function renderActions(hand) {
  actionButtons.innerHTML = "";
  resetAmountAction();
  if (!hand) {
    actionMeta.textContent = "🎮 当前没有 hand。";
    return;
  }
  if (!hand.actor_id && !(hand.available_actions || []).length) {
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
  hideActionHint();
  actionMeta.innerHTML = `
    <strong>🎯 当前行动者：</strong> ${escapeHtml(seatDisplayWithNo(hand.actor_id || "", hand.seats || []))}
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
}

function handleActionChoice(actionSpec) {
  if (actionSpec.action === "bet" || actionSpec.action === "raise") {
    selectedActionSpec = actionSpec;
    amountBox.classList.remove("hidden");
    actionAmount.min = actionSpec.min ?? 0;
    actionAmount.max = actionSpec.max ?? "";
    actionAmount.value = actionSpec.default ?? actionSpec.min ?? "";
    selectedActionHint.innerHTML = `🧠 已选择 <strong>${actionLabel(actionSpec.action)}</strong>，请输入 ${actionSpec.min ?? "-"} ~ ${actionSpec.max ?? "-"} 的金额后确认。`;
    selectedActionHint.classList.remove("hidden");
    return;
  }
  submitAction(actionSpec).catch((error) => showBanner(error.message));
}

function resetAmountAction() {
  selectedActionSpec = null;
  amountBox.classList.add("hidden");
  actionAmount.value = "";
  actionAmount.min = 0;
  actionAmount.max = "";
  hideActionHint();
}

async function submitAction(actionSpec, amountOverride = null) {
  if (!sessionId || !currentState?.current_hand?.actor_id) {
    return;
  }
  const payload = {
    actor_id: currentState.current_hand.actor_id,
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
  if (state?.phase === "hand_ended" && state.current_hand?.hand_id) {
    await refreshHistory();
    await loadReplay(state.current_hand.hand_id);
  }
}

function renderSpeakerOptions(hand) {
  const selectedValue = speakerId.value;
  const seats = hand?.seats || [];
  speakerId.innerHTML = seats
    .map(
      (seat) =>
        `<option value="${escapeHtml(seat.seat_id)}">💬 ${escapeHtml(seat.display_name)} · ${seatNoLabel(seat.seat_no)}</option>`
    )
    .join("");
  if (selectedValue && seats.some((seat) => seat.seat_id === selectedValue)) {
    speakerId.value = selectedValue;
  }
}

function eventSummary(event, seats = currentState?.current_hand?.seats || []) {
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

function appendTimeline(event) {
  const meta = EVENT_META[event.event_type] || { emoji: "🎲", label: event.event_type };
  const node = document.createElement("div");
  node.className = "timeline-item";
  node.innerHTML = `
    <div class="timeline-top">
      <span class="timeline-tag">${meta.emoji} ${escapeHtml(meta.label)}</span>
      <span class="timeline-time">#${event.event_id} · ${escapeHtml(formatDateTime(event.created_at))}</span>
    </div>
    <div class="timeline-title">${escapeHtml(channelLabel(event.channel))}</div>
    <div class="event-summary">${escapeHtml(eventSummary(event, currentState?.current_hand?.seats || []))}</div>
    <details class="event-detail-wrap">
      <summary>查看事件详情</summary>
      <pre class="event-detail">${escapeHtml(JSON.stringify(event.payload, null, 2))}</pre>
    </details>
  `;
  timeline.prepend(node);
}

async function refreshState() {
  if (!sessionId) {
    return;
  }
  const data = await api(`/api/v1/sessions/${sessionId}/state`);
  renderState(data);
  return data;
}

async function refreshHistory() {
  if (!sessionId) {
    return;
  }
  const data = await api(`/api/v1/sessions/${sessionId}/hands?limit=20&offset=0`);
  historyList.innerHTML = "";
    if (!data.items.length) {
      historyList.innerHTML = '<div class="empty-state">📚 暂无历史手牌。</div>';
      return;
  }
  data.items.forEach((item) => {
    const winners = (item.winners || [])
      .map(
        (winner) =>
          `${seatDisplayName(winner.seat_id, currentState?.current_hand?.seats || [])} +${winner.win_amount}`
      )
      .join(" · ");
    const row = document.createElement("div");
    row.className = "history-item";
    row.innerHTML = `
      <div class="history-top">
        <div class="history-main">
          <div class="history-title">🃏 第 ${item.hand_no} 手</div>
          <div class="history-subline" title="${escapeHtml(item.hand_id)}">${escapeHtml(item.hand_id)}</div>
        </div>
        <button type="button" data-hand-id="${escapeHtml(item.hand_id)}">🎞️ 查看回放</button>
      </div>
      <div class="chip-line">
        <span class="badge">🏆 赢家 ${escapeHtml(winners || (item.winner_ids || []).join(", ") || "-")}</span>
        <span class="badge">💰 底池 ${item.pot_total}</span>
        <span class="badge">⚡ 动作 ${item.action_count}</span>
        <span class="badge">💬 聊天 ${item.chat_count}</span>
      </div>
      <div class="history-subline">🕒 ${escapeHtml(item.started_at)} → ${escapeHtml(item.ended_at || "-")}</div>
    `;
    row.querySelector("button").addEventListener("click", () => loadReplay(item.hand_id));
    historyList.appendChild(row);
  });
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
      const meta = EVENT_META[item.event_type] || { emoji: "🎲", label: item.event_type };
      return `
        <div class="timeline-item replay-timeline-item">
          <div class="timeline-top">
            <span class="timeline-tag">${meta.emoji} ${escapeHtml(meta.label)}</span>
            <span class="timeline-time">#${item.event_id} · ${escapeHtml(formatDateTime(item.created_at))}</span>
          </div>
          <div class="timeline-title">${escapeHtml(channelLabel(item.channel))}</div>
          <div class="event-summary">${escapeHtml(eventSummary(item, replaySeats))}</div>
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
    const data = await api(`/api/v1/replays/${handId}`);
    renderReplay(data);
    replayView.scrollTop = 0;
  } catch (error) {
    showBanner(error.message);
  }
}

async function pollEvents() {
  if (!sessionId) {
    return;
  }
  try {
    const data = await api(
      `/api/v1/sessions/${sessionId}/events?since_event_id=${lastEventId}&limit=200`
    );
    let needsStateRefresh = false;
    data.events.forEach((event) => {
      appendTimeline(event);
      lastEventId = Math.max(lastEventId, event.event_id);
      if (event.channel !== "chat") {
        needsStateRefresh = true;
      }
      if (event.event_type === "hand_ended") {
        refreshHistory().catch((error) => showBanner(error.message));
      }
    });
    if (needsStateRefresh) {
      const state = await refreshState();
      if (state?.phase === "hand_ended") {
        await refreshHistory();
        if (state.current_hand?.hand_id && replayView.dataset.handId !== state.current_hand.hand_id) {
          await loadReplay(state.current_hand.hand_id);
        }
      }
    }
  } catch (error) {
    showBanner(error.message);
  }
}

function startPolling() {
  clearInterval(pollHandle);
  pollHandle = setInterval(pollEvents, pollInterval);
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
    seat_count: Number(form.get("seat_count")),
    small_blind: Number(form.get("small_blind")),
    big_blind: Number(form.get("big_blind")),
    starting_stack: Number(form.get("starting_stack")),
    seed: form.get("seed") === "" ? null : Number(form.get("seed")),
    seat_names: collectSeatNames(),
  };
  try {
    const data = await api("/api/v1/sessions", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    sessionId = data.session_id;
    timeline.innerHTML = '<div class="empty-state">🕒 新牌桌已创建，等待事件流刷新。</div>';
    replayView.innerHTML = '<div class="empty-state">🪄 选择一手已结束牌局查看回放。</div>';
    replayView.dataset.handId = "";
    await refreshState();
    await refreshHistory();
    startPolling();
  } catch (error) {
    showBanner(error.message);
  }
});

document.getElementById("startHandForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!sessionId) {
    showBanner("请先创建牌桌");
    return;
  }
  const form = new FormData(event.currentTarget);
  const dealerValue = form.get("dealer_seat");
  const payload = {};
  if (dealerValue !== "") {
    payload.dealer_seat = Number(dealerValue);
  }
  try {
    await api(`/api/v1/sessions/${sessionId}/hands`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    await refreshState();
    await refreshHistory();
  } catch (error) {
    showBanner(error.message);
  }
});

document.getElementById("chatForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!sessionId) {
    showBanner("请先创建牌桌");
    return;
  }
  try {
    await api(`/api/v1/sessions/${sessionId}/chat`, {
      method: "POST",
      body: JSON.stringify({
        speaker_id: speakerId.value,
        text: document.getElementById("chatText").value,
      }),
    });
    document.getElementById("chatText").value = "";
  } catch (error) {
    showBanner(error.message);
  }
});

document.getElementById("refreshBtn").addEventListener("click", () => {
  refreshState().catch((error) => showBanner(error.message));
  refreshHistory().catch((error) => showBanner(error.message));
});

seatCountInput.addEventListener("input", renderSeatNameInputs);
seatNamesList.addEventListener("input", syncSeatNameDrafts);
renderSeatNameInputs();
