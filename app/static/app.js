// Share-link copy helper.
document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-copy]");
  if (!btn) return;
  const input = document.querySelector(btn.dataset.copy);
  if (!input) return;
  const text = input.value;
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(() => flash(btn, "Copied ✓"));
  } else {
    input.select();
    document.execCommand("copy");
    flash(btn, "Copied ✓");
  }
});

function flash(btn, msg) {
  const old = btn.textContent;
  btn.textContent = msg;
  setTimeout(() => (btn.textContent = old), 1500);
}

// Dismiss error messages without reloading the page.
document.addEventListener("click", (e) => {
  const btn = e.target.closest(".alert-dismiss");
  if (!btn) return;
  btn.closest(".alert")?.remove();
});

// Loading state for adding a listing.
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
      addButton.textContent = "Analyzing...";
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

// Auto-scroll chat to the bottom.
const log = document.querySelector(".chat-log");
if (log) log.scrollTop = log.scrollHeight;

// One send at a time to prevent double-click and Enter duplicates.
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
      chatButton.textContent = chatForm.dataset.pendingLabel || "Sending...";
    }
  });

  // Safari does not always trigger implicit submit on single-input forms.
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
