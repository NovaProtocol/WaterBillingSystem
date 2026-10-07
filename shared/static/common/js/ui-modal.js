/* Bootstrap's JS, re-supplied in miniature.
   The page JS calls `openModal(el)` / `closeModal(el)`; markup keeps Bootstrap's
   `data-bs-toggle` / `data-bs-target` / `data-bs-dismiss` attributes, so no template
   needed rewriting. Covers what WBS actually used: modal open/close, collapse, and
   alert dismiss. No dropdowns or tabs are used anywhere in the app. */
(function () {
  var backdrop = null;

  function resolve(target) {
    return typeof target === "string" ? document.querySelector(target) : target;
  }

  function syncBackdrop() {
    if (document.querySelector(".modal.show")) {
      if (!backdrop) {
        backdrop = document.createElement("div");
        backdrop.className = "modal-backdrop fade";
        document.body.appendChild(backdrop);
        void backdrop.offsetHeight;
      }
      backdrop.classList.add("show");
      document.body.style.overflow = "hidden";
    } else {
      if (backdrop) {
        backdrop.remove();
        backdrop = null;
      }
      document.body.style.overflow = "";
    }
  }

  function openModal(target) {
    var modal = resolve(target);
    if (!modal) return;
    modal.style.display = "block";
    void modal.offsetHeight; // let the .fade opacity transition run
    modal.classList.add("show");
    modal.setAttribute("aria-hidden", "false");
    modal.setAttribute("aria-modal", "true");
    if (!modal.getAttribute("role")) modal.setAttribute("role", "dialog");
    syncBackdrop();
  }

  function closeModal(target) {
    var modal = resolve(target);
    if (!modal) return;
    modal.classList.remove("show");
    modal.style.display = "";
    modal.setAttribute("aria-hidden", "true");
    modal.removeAttribute("aria-modal");
    syncBackdrop();
  }

  function collapseToggle(toggle) {
    var sel = toggle.getAttribute("data-bs-target") || toggle.getAttribute("href");
    var panel = resolve(sel);
    if (!panel) return;
    var open = panel.classList.toggle("show");
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function collapseShow(target) {
    var panel = resolve(target);
    if (panel) panel.classList.add("show");
  }

  function collapseHide(target) {
    var panel = resolve(target);
    if (panel) panel.classList.remove("show");
  }

  document.addEventListener("click", function (ev) {
    var toggler = ev.target.closest('[data-bs-toggle="modal"]');
    if (toggler) {
      ev.preventDefault();
      openModal(toggler.getAttribute("data-bs-target"));
      return;
    }
    var collapser = ev.target.closest('[data-bs-toggle="collapse"]');
    if (collapser) {
      ev.preventDefault();
      collapseToggle(collapser);
      return;
    }
    var dismiss = ev.target.closest("[data-bs-dismiss]");
    if (dismiss) {
      var kind = dismiss.getAttribute("data-bs-dismiss");
      if (kind === "modal") {
        ev.preventDefault();
        closeModal(dismiss.closest(".modal"));
        return;
      }
      if (kind === "alert") {
        var alert = dismiss.closest(".alert");
        if (alert) alert.remove();
        return;
      }
    }
    if (ev.target.classList && ev.target.classList.contains("modal") &&
        ev.target.getAttribute("data-backdrop") !== "static") {
      closeModal(ev.target);
    }
  });

  document.addEventListener("keydown", function (ev) {
    if (ev.key !== "Escape") return;
    var open = document.querySelector(".modal.show");
    if (open && open.getAttribute("data-backdrop") !== "static") closeModal(open);
  });

  window.openModal = openModal;
  window.closeModal = closeModal;
  window.collapseShow = collapseShow;
  window.collapseHide = collapseHide;
})();
