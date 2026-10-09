const STEP_MS = 280;

const socket = io();
const fields = BOARD.fields;
const sideLength = fields.length / 4;

const boardEl = document.getElementById("board");
const piecesEl = document.getElementById("pieces");
const diceEl = document.getElementById("dice");
const statusEl = document.getElementById("status");
const rollTextEl = document.getElementById("roll-text");
const playersEl = document.getElementById("players");
const startBtn = document.getElementById("start-btn");
const skipBtn = document.getElementById("skip-btn");
const resetBtn = document.getElementById("reset-btn");

const fieldEls = [];
const pieces = {}; // player id -> { el, shown, slot, timer }
let state = null;
let seenRollSeq = 0;

function sipsText(count) {
  return count === 1 ? "1 tår" : `${count} tårer`;
}

// Field 0 is the bottom right corner, and the ring runs clockwise from there.
function gridPosition(index) {
  const last = sideLength;
  if (index <= sideLength) return [last, last - index];
  if (index <= 2 * sideLength) return [last - (index - sideLength), 0];
  if (index <= 3 * sideLength) return [0, index - 2 * sideLength];
  return [index - 3 * sideLength, last];
}

function buildBoard() {
  boardEl.style.setProperty("--size", sideLength + 1);
  fields.forEach((field, index) => {
    const el = document.createElement("div");
    el.className = `field field-${field.type}`;
    const [row, col] = gridPosition(index);
    el.style.gridRow = row + 1;
    el.style.gridColumn = col + 1;

    if (field.type === "bar") {
      const band = document.createElement("div");
      band.className = "band";
      band.style.background = BOARD.groups[field.group].color;
      el.append(band);
    }
    const icons = { start: "🚀", chance: "❓", brandert: "🥴" };
    if (icons[field.type]) {
      const icon = document.createElement("div");
      icon.className = "icon";
      icon.textContent = icons[field.type];
      el.append(icon);
    }
    const name = document.createElement("div");
    name.className = "name";
    name.textContent = field.name;
    el.append(name);
    if (field.type === "bar") {
      const sips = document.createElement("div");
      sips.className = "sips";
      sips.textContent = `🍺 ${sipsText(field.sips)}`;
      el.append(sips);
    }
    boardEl.insertBefore(el, piecesEl);
    fieldEls.push(el);
  });
}

function placePiece(piece) {
  const field = fieldEls[piece.shown];
  const size = field.offsetWidth * 0.26;
  const x = field.offsetLeft + field.offsetWidth * (0.17 + 0.22 * (piece.slot % 4));
  const y = field.offsetTop + field.offsetHeight * (piece.slot < 4 ? 0.6 : 0.84);
  piece.el.style.width = piece.el.style.height = `${size}px`;
  piece.el.style.fontSize = `${size * 0.55}px`;
  piece.el.style.transform = `translate(${x - size / 2}px, ${y - size / 2}px)`;
}

function walkTo(piece, target) {
  clearInterval(piece.timer);
  piece.timer = setInterval(() => {
    if (piece.shown === target) {
      clearInterval(piece.timer);
      return;
    }
    piece.shown = (piece.shown + 1) % fields.length;
    placePiece(piece);
  }, STEP_MS);
}

function renderPieces() {
  const roll = state.last_roll;
  const newRoll = roll && roll.seq !== seenRollSeq ? roll : null;
  if (roll) seenRollSeq = roll.seq;

  const ids = new Set(state.players.map((p) => String(p.id)));
  for (const id of Object.keys(pieces)) {
    if (!ids.has(id)) {
      pieces[id].el.remove();
      delete pieces[id];
    }
  }

  state.players.forEach((player, slot) => {
    let piece = pieces[player.id];
    if (!piece) {
      const el = document.createElement("div");
      el.className = "piece";
      el.textContent = player.name[0].toUpperCase();
      el.style.background = player.color;
      piecesEl.append(el);
      piece = pieces[player.id] = { el, shown: player.position, timer: null };
    }
    piece.slot = slot;
    piece.el.classList.toggle("active", player.id === state.current_player_id);
    if (newRoll && newRoll.player_id === player.id) {
      piece.shown = newRoll.from;
      walkTo(piece, player.position);
    } else if (piece.shown !== player.position) {
      clearInterval(piece.timer);
      piece.shown = player.position;
    }
    placePiece(piece);
  });
}

function renderCenter() {
  const current = state.players.find((p) => p.id === state.current_player_id);
  if (!state.started) {
    statusEl.textContent = state.players.length
      ? "Tryk på Start, når alle er med"
      : "Scan QR-koden for at være med";
    statusEl.style.color = "";
  } else {
    statusEl.textContent = `${current.name}s tur`;
    statusEl.style.color = current.color;
  }

  const roll = state.last_roll;
  const roller = roll && state.players.find((p) => p.id === roll.player_id);
  if (roller) {
    diceEl.textContent = roll.value <= 6 ? String.fromCodePoint(0x267f + roll.value) : roll.value;
    rollTextEl.textContent = `${roller.name} slog ${roll.value} og landede på ${roll.field}`;
  } else {
    diceEl.textContent = "🎲";
    rollTextEl.textContent = "";
  }
  diceEl.classList.remove("rolled");
  void diceEl.offsetWidth; // restart the animation
  if (roller) diceEl.classList.add("rolled");
}

function renderPlayers() {
  playersEl.replaceChildren();
  for (const player of state.players) {
    const li = document.createElement("li");
    li.classList.toggle("turn", player.id === state.current_player_id);
    li.classList.toggle("offline", !player.connected);

    const dot = document.createElement("span");
    dot.className = "dot";
    dot.style.background = player.color;
    const name = document.createElement("span");
    name.className = "player-name";
    name.textContent = player.name;
    const where = document.createElement("span");
    where.className = "player-where";
    where.textContent = player.connected ? fields[player.position].name : "Ikke forbundet";
    li.append(dot, name, where);
    playersEl.append(li);
  }
}

function render() {
  renderPieces();
  renderCenter();
  renderPlayers();
  startBtn.hidden = state.started;
  startBtn.disabled = state.players.length === 0;
  skipBtn.hidden = !state.started;
  resetBtn.hidden = !state.started;
}

function hostAction(event) {
  socket.emit(event, (result) => {
    if (!result.ok) alert(result.error);
  });
}

startBtn.addEventListener("click", () => hostAction("start"));
skipBtn.addEventListener("click", () => hostAction("skip"));
resetBtn.addEventListener("click", () => {
  if (confirm("Vil du starte et nyt spil? Alle brikker rykker tilbage til start.")) {
    hostAction("reset");
  }
});

window.addEventListener("resize", () => Object.values(pieces).forEach(placePiece));

socket.on("state", (newState) => {
  state = newState;
  render();
});

buildBoard();
