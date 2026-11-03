// KORNOR site behaviour: mobile menu, smart header, project filter, lightbox, reveal.
(function () {
  var header = document.querySelector("[data-header]");
  var btn = document.querySelector("[data-menu-btn]");
  var panel = document.querySelector("[data-menu]");
  var label = document.querySelector("[data-menu-label]");
  var hero = document.querySelector(".hero");

  // ---- Mobile menu
  function setMenu(open) {
    if (!btn || !panel) return;
    btn.setAttribute("aria-expanded", String(open));
    panel.hidden = !open;
    header.classList.toggle("menu-open", open);
    document.body.classList.toggle("no-scroll", open);
    if (label) label.textContent = open ? "Close" : "Menu";
    if (open) header.classList.add("is-visible");
    else onScroll();
  }
  if (btn) {
    btn.addEventListener("click", function () { setMenu(btn.getAttribute("aria-expanded") !== "true"); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") setMenu(false); });
    window.addEventListener("resize", function () { if (window.innerWidth > 860) setMenu(false); });
  }

  // ---- Header: reveal after the hero (home), hide on scroll down, show on scroll up
  var lastY = window.scrollY;
  function onScroll() {
    if (!header || header.classList.contains("menu-open")) return;
    var y = window.scrollY;
    if (hero) header.classList.toggle("is-visible", y > hero.offsetHeight * 0.6);
    var goingDown = y > lastY + 4, goingUp = y < lastY - 4;
    if (goingDown && y > 120) header.classList.add("is-hidden");
    else if (goingUp || y <= 120) header.classList.remove("is-hidden");
    lastY = y;
  }
  var ticking = false;
  window.addEventListener("scroll", function () {
    if (!ticking) { requestAnimationFrame(function () { onScroll(); ticking = false; }); ticking = true; }
  }, { passive: true });
  onScroll();

  // ---- Project filter
  var filters = document.querySelector("[data-filters]");
  if (filters) {
    var cards = document.querySelectorAll("[data-grid] [data-category]");
    var empty = document.querySelector("[data-empty]");
    filters.addEventListener("click", function (e) {
      var b = e.target.closest("[data-filter]");
      if (!b) return;
      var f = b.getAttribute("data-filter");
      filters.querySelectorAll("[data-filter]").forEach(function (x) { x.setAttribute("aria-pressed", String(x === b)); });
      var shown = 0;
      cards.forEach(function (c) {
        var on = f === "all" || c.getAttribute("data-category") === f;
        c.hidden = !on; if (on) shown++;
      });
      if (empty) empty.hidden = shown > 0;
    });
  }

  // ---- Lightbox for project galleries
  document.addEventListener("click", function (e) {
    var a = e.target.closest("[data-lightbox]");
    if (!a) return;
    e.preventDefault();
    var img = a.querySelector("img");
    var box = document.createElement("div");
    box.className = "lightbox";
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");
    box.innerHTML = '<button type="button" aria-label="Close">×</button>';
    var big = document.createElement("img");
    big.src = a.getAttribute("href");
    big.alt = img ? img.alt : "";
    box.appendChild(big);
    function close() { box.remove(); document.body.classList.remove("no-scroll"); document.removeEventListener("keydown", esc); a.focus(); }
    function esc(ev) { if (ev.key === "Escape") close(); }
    box.addEventListener("click", close);
    document.addEventListener("keydown", esc);
    document.body.appendChild(box);
    document.body.classList.add("no-scroll");
    box.querySelector("button").focus();
  });

  // ---- Gentle reveal on scroll
  if ("IntersectionObserver" in window && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    var els = document.querySelectorAll(".zz-row, .project-card, .service, .person, .cta-band");
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); } });
    }, { rootMargin: "0px 0px -8% 0px" });
    els.forEach(function (el) { el.classList.add("reveal"); io.observe(el); });
  }
})();
