const TOKEN_KEY = "tourDeByturToken";

const socket = io();
const joinView = document.getElementById("join-view");
const gameView = document.getElementById("game-view");
const nameInput = document.getElementById("name");
const meEl = document.getElementById("me");
const infoEl = document.getElementById("info");
const rollBtn = document.getElementById("roll-btn");
const buyView = document.getElementById("buy-view");
const buyBtn = document.getElementById("buy-btn");
const declineBtn = document.getElementById("decline-btn");
const giveView = document.getElementById("give-view");
const cardView = document.getElementById("card-view");
const cardText = document.getElementById("card-text");
const doneBtn = document.getElementById("done-btn");
const resultEl = document.getElementById("result");
const errorEl = document.getElementById("error");

let token = loadToken();
let myId = null;
let state = null;
let busy = false; // waiting for the server to answer a button press

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
  meEl.textContent = `${me.name} · 🍺 ${me.sips}`;

  const current = state.players.find((p) => p.id === state.current_player_id);
  const myTurn = state.started && current.id === myId;
  const choice = state.pending && state.pending.player_id === myId ? state.pending : null;
  const buying = choice && choice.type === "buy";
  const giving = choice && choice.type === "give";
  const card = choice && choice.type === "card";
  if (!state.started) infoEl.textContent = "Venter på at værten starter spillet…";
  else if (buying) infoEl.textContent = "Baren er ledig. Vil du købe den?";
  else if (giving) infoEl.textContent = `Du passerede start! Hvem skal have ${sipsText(choice.sips)}?`;
  else if (card) infoEl.textContent = "Chance! Læs kortet højt";
  else if (myTurn) infoEl.textContent = "Det er din tur!";
  else infoEl.textContent = `Det er ${current.name}s tur`;

  rollBtn.hidden = Boolean(choice);
  rollBtn.disabled = !myTurn || busy;
  rollBtn.classList.toggle("ready", myTurn);

  buyView.hidden = !buying;
  buyBtn.disabled = declineBtn.disabled = busy;
  if (buying) buyBtn.textContent = `Køb for ${sipsText(state.pending.price)} 🍺`;

  giveView.hidden = !giving;
  giveView.replaceChildren();
  if (giving) {
    for (const player of state.players) {
      if (player.id === myId) continue;
      const button = document.createElement("button");
      button.className = "btn btn-give";
      button.textContent = player.name;
      button.style.background = player.color;
      button.disabled = busy;
      button.addEventListener("click", () => send("give", { target: player.id }));
      giveView.append(button);
    }
  }

  cardView.hidden = !card;
  doneBtn.disabled = busy;
  if (card) cardText.textContent = choice.text;

  // The card itself is on screen, so the message would only repeat it.
  resultEl.textContent = card ? "" : state.message;
}

function sipsText(count) {
  return count === 1 ? "1 tår" : `${count} tårer`;
}

function send(event, extra = {}) {
  busy = true;
  errorEl.textContent = "";
  render();
  if (navigator.vibrate) navigator.vibrate(60);
  socket.emit(event, { token, ...extra }, (result) => {
    busy = false;
    if (!result.ok) errorEl.textContent = result.error;
    render();
  });
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

rollBtn.addEventListener("click", () => send("roll"));
buyBtn.addEventListener("click", () => send("buy"));
declineBtn.addEventListener("click", () => send("decline"));
doneBtn.addEventListener("click", () => send("finish_card"));

socket.on("connect", () => {
  busy = false;
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
