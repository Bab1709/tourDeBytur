const TOKEN_KEY = "tourDeByturToken";

const socket = io();
const joinView = document.getElementById("join-view");
const gameView = document.getElementById("game-view");
const nameInput = document.getElementById("name");
const meEl = document.getElementById("me");
const infoEl = document.getElementById("info");
const rollBtn = document.getElementById("roll-btn");
const resultEl = document.getElementById("result");
const errorEl = document.getElementById("error");

let token = loadToken();
let myId = null;
let state = null;
let rolling = false;

// Storage can be blocked in private browsing; the game still works without it.
function loadToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function saveToken(value) {
  token = value;
  try {
    if (value) localStorage.setItem(TOKEN_KEY, value);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {}
}

function render() {
  if (!state) return;
  const me = state.players.find((p) => p.id === myId);
  joinView.hidden = Boolean(me);
  gameView.hidden = !me;
  if (!me) return;

  document.body.style.setProperty("--me", me.color);
  meEl.textContent = me.name;

  const current = state.players.find((p) => p.id === state.current_player_id);
  const myTurn = state.started && current.id === myId;
  if (!state.started) infoEl.textContent = "Venter på at værten starter spillet…";
  else if (myTurn) infoEl.textContent = "Det er din tur!";
  else infoEl.textContent = `Det er ${current.name}s tur`;

  rollBtn.disabled = !myTurn || rolling;
  rollBtn.classList.toggle("ready", myTurn);

  const roll = state.last_roll;
  resultEl.textContent =
    roll && roll.player_id === myId ? `Du slog ${roll.value} og landede på ${roll.field}` : "";
}

joinView.addEventListener("submit", (event) => {
  event.preventDefault();
  errorEl.textContent = "";
  socket.emit("join", { name: nameInput.value }, (result) => {
    if (!result.ok) {
      errorEl.textContent = result.error;
      return;
    }
    saveToken(result.token);
    myId = result.id;
    render();
  });
});

rollBtn.addEventListener("click", () => {
  rolling = true;
  errorEl.textContent = "";
  render();
  if (navigator.vibrate) navigator.vibrate(60);
  socket.emit("roll", { token }, (result) => {
    rolling = false;
    if (!result.ok) errorEl.textContent = result.error;
    render();
  });
});

socket.on("connect", () => {
  rolling = false;
  if (!token) return;
  socket.emit("rejoin", { token }, (result) => {
    if (result.ok) {
      myId = result.id;
    } else {
      saveToken(null);
      myId = null;
    }
    render();
  });
});

socket.on("state", (newState) => {
  state = newState;
  render();
});
