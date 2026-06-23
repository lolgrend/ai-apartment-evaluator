// Kopiowanie linku udostępniania
document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-copy]");
  if (!btn) return;
  const input = document.querySelector(btn.dataset.copy);
  if (!input) return;
  const text = input.value;
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(() => flash(btn, "Skopiowano ✓"));
  } else {
    input.select();
    document.execCommand("copy");
    flash(btn, "Skopiowano ✓");
  }
});

function flash(btn, msg) {
  const old = btn.textContent;
  btn.textContent = msg;
  setTimeout(() => (btn.textContent = old), 1500);
}

// Komunikaty błędów można zamknąć bez przeładowania strony.
document.addEventListener("click", (e) => {
  const btn = e.target.closest(".alert-dismiss");
  if (!btn) return;
  btn.closest(".alert")?.remove();
});

// Spinner przy dodawaniu (ocena trwa kilkanaście sekund)
const addForm = document.getElementById("add-form");
if (addForm) {
  const addButton = document.getElementById("submit-btn");
  const addButtonLabel = addButton?.textContent;

  addForm.addEventListener("submit", (e) => {
    if (addForm.dataset.submitting === "true") {
      e.preventDefault();
      return;
    }
    addForm.dataset.submitting = "true";
    addForm.setAttribute("aria-busy", "true");
    if (addButton) {
      addButton.disabled = true;
      addButton.classList.add("is-loading");
      addButton.textContent = "Analizuję…";
    }
  });

  window.addEventListener("pageshow", () => {
    delete addForm.dataset.submitting;
    addForm.removeAttribute("aria-busy");
    if (addButton) {
      addButton.disabled = false;
      addButton.classList.remove("is-loading");
      addButton.textContent = addButtonLabel;
    }
  });
}

// Auto-scroll czatu na dół
const log = document.querySelector(".chat-log");
if (log) log.scrollTop = log.scrollHeight;

// Jedno wysłanie na raz — chroni przed podwójnym kliknięciem i Enterem.
const chatForm = document.querySelector(".chat-form");
if (chatForm) {
  const chatButton = chatForm.querySelector("button[type='submit'], button:not([type])");
  const chatInput = chatForm.querySelector("input[name='message']");
  const originalLabel = chatButton?.textContent;

  chatForm.addEventListener("submit", (e) => {
    if (chatForm.dataset.submitting === "true") {
      e.preventDefault();
      return;
    }
    chatForm.dataset.submitting = "true";
    chatForm.setAttribute("aria-busy", "true");
    if (chatInput) chatInput.readOnly = true;
    if (chatButton) {
      chatButton.disabled = true;
      chatButton.classList.add("is-loading");
      chatButton.textContent = chatForm.dataset.pendingLabel || "Wysyłam…";
    }
  });

  // Safari nie zawsze uruchamia implicit submit formularza z pojedynczym inputem.
  chatInput?.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || e.shiftKey || e.isComposing || e.keyCode === 229) return;
    e.preventDefault();
    if (chatForm.dataset.submitting === "true") return;
    if (typeof chatForm.requestSubmit === "function") {
      chatForm.requestSubmit(chatButton || undefined);
    } else {
      chatButton?.click();
    }
  });

  window.addEventListener("pageshow", () => {
    delete chatForm.dataset.submitting;
    chatForm.removeAttribute("aria-busy");
    if (chatInput) chatInput.readOnly = false;
    if (chatButton) {
      chatButton.disabled = false;
      chatButton.classList.remove("is-loading");
      chatButton.textContent = originalLabel;
    }
  });
}
