"use strict";

document.querySelectorAll("[data-refresh]").forEach((button) => {
  button.addEventListener("click", () => window.location.reload());
});

document.querySelectorAll("[data-chart]").forEach((container) => {
  const points = JSON.parse(container.dataset.points);
  const svg = container.querySelector("svg");
  if (!svg || !points.length) return;
  const cursor = svg.querySelector(".chart-cursor");
  const selected = svg.querySelector(".chart-selected");
  const readout = container.querySelector(".chart-readout");
  let current = points.length - 1;
  function select(index) {
    current = Math.max(0, Math.min(points.length - 1, index));
    const point = points[current];
    cursor.setAttribute("x1", String(point.x));
    cursor.setAttribute("x2", String(point.x));
    cursor.setAttribute("visibility", "visible");
    selected.setAttribute("cx", String(point.x));
    selected.setAttribute("cy", String(point.y));
    selected.setAttribute("visibility", "visible");
    readout.textContent = `${point.count.toLocaleString("en-US")} concurrent players · ${point.at} · observation ${current + 1} of ${points.length}`;
  }
  svg.addEventListener("pointermove", (event) => {
    const bounds = svg.getBoundingClientRect();
    // SVG's meet scaling can letterbox vertically on narrow screens; x uses the
    // actual viewBox scale and centered offset, not the CSS box alone.
    const scale = Math.min(bounds.width / 880, bounds.height / 260);
    const offset = (bounds.width - 880 * scale) / 2;
    const x = (event.clientX - bounds.left - offset) / scale;
    let nearest = 0;
    points.forEach((point, index) => {
      if (Math.abs(point.x - x) < Math.abs(points[nearest].x - x)) nearest = index;
    });
    select(nearest);
  });
  svg.addEventListener("focus", () => select(current));
  svg.addEventListener("keydown", (event) => {
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      select(current + (event.key === "ArrowLeft" ? -1 : 1));
    } else if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      select(event.key === "Home" ? 0 : points.length - 1);
    }
  });
});

// Poll only the local read API. Leave the user's chart position, search, focus,
// and expanded data table intact; make new stored data an explicit refresh.
const notice = document.querySelector("[data-refresh-notice]");
if (notice) {
  let previous = null;
  async function checkStoredState() {
    if (document.hidden) return;
    try {
      const response = await fetch("/api/v1/apps", {cache: "no-store"});
      if (!response.ok) throw new Error("read-unavailable");
      const body = await response.json();
      const signature = JSON.stringify(body.items.map((item) => [item.app_id, item.observed_at, item.availability, item.last_attempt]));
      if (previous !== null && signature !== previous) {
        notice.textContent = "Stored observations or freshness changed. Refresh this view.";
      }
      previous = signature;
    } catch (_) {
      notice.textContent = "Stored-data refresh check failed. Open Status or refresh to retry.";
    }
  }
  checkStoredState();
  window.setInterval(checkStoredState, Number(document.body.dataset.refreshSeconds) * 1000);
}

document.querySelectorAll('[data-game-image]').forEach((image) => {
  const failed = () => image.classList.add('image-unavailable');
  image.addEventListener('error', failed);
  if (image.complete && !image.naturalWidth) failed();
});
document.querySelectorAll('[data-collect-form]').forEach((form) => {
  form.addEventListener('submit', () => {
    const button = form.querySelector('button');
    button.disabled = true;
    button.textContent = 'Fetching Steam data…';
  });
});
document.querySelectorAll('a[href="#screenshots"]').forEach((link) => {
  link.addEventListener('click', () => {
    const section = document.getElementById('screenshots');
    if (section) section.open = true;
  });
});

const automaticProfile = document.querySelector('[data-auto-details]');
if (automaticProfile) {
  const status = document.querySelector('[data-details-loading]');
  const button = automaticProfile.querySelector('[data-collect-form] button');
  button.disabled = true;
  button.textContent = 'Loading Steam data…';
  fetch(automaticProfile.dataset.autoDetails, {method: 'POST', credentials: 'same-origin'})
    .then((response) => {
      if (!response.ok) throw new Error('Details refresh failed');
      window.location.replace(response.url);
    })
    .catch(() => {
      status.textContent = 'Steam details could not finish loading. Use Refresh details to retry.';
      button.disabled = false;
      button.textContent = 'Refresh details ↻';
    });
}
const completedProfile = document.querySelector('.game-profile');
if (completedProfile) {
  const currentUrl = new URL(window.location.href);
  if (currentUrl.searchParams.has('refreshed')) {
    currentUrl.searchParams.delete('refreshed');
    window.history.replaceState(null, '', currentUrl.pathname + currentUrl.search + currentUrl.hash);
  }
}
