"""JavaScript propio del panel en vivo (#53), servido desde el mismo origen."""
from __future__ import annotations

PANEL_LIVE_JS = r"""
(function () {
  "use strict";
  var region = document.getElementById("live-region");
  if (!region) { return; }

  var liveSrc = region.getAttribute("data-live-src");
  var wsPath = region.getAttribute("data-ws");
  var caseId = region.getAttribute("data-case-id") || "";
  var pollSeconds = parseInt(region.getAttribute("data-poll") || "0", 10);
  var BACKOFF_INITIAL_MS = 1000;
  var BACKOFF_MAX_MS = 30000;

  var socket = null;
  var retryDelay = BACKOFF_INITIAL_MS;
  var reconnectTimer = null;
  var pollTimer = null;
  var refreshing = false;
  var isChat = region.classList.contains("chat-log");

  function countMessages() {
    return region.querySelectorAll(".chat-msg").length;
  }

  function scrollToEnd() {
    if (isChat) { region.scrollTop = region.scrollHeight; }
  }

  function pad(value) {
    return value < 10 ? "0" + value : "" + value;
  }

  var MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

  function humanDate(value) {
    var hours = value.getHours();
    var suffix = hours < 12 ? "a. m." : "p. m.";
    return value.getDate() + " " + MONTHS[value.getMonth()] + " " + value.getFullYear() +
      ", " + (hours % 12 || 12) + ":" + pad(value.getMinutes()) + " " + suffix;
  }

  function localizeTimes() {
    var times = region.querySelectorAll("time[datetime]");
    for (var i = 0; i < times.length; i++) {
      var raw = times[i].getAttribute("datetime");
      if (raw.indexOf("T") < 0) { continue; }
      var parsed = new Date(raw);
      if (isNaN(parsed.getTime())) { continue; }
      times[i].textContent = humanDate(parsed);
    }
  }

  function replaceRegion(html) {
    var parsed = new DOMParser().parseFromString(html, "text/html");
    if (!parsed || !parsed.body) { return; }
    var before = countMessages();
    var nodes = Array.prototype.slice.call(parsed.body.childNodes);
    region.replaceChildren.apply(region, nodes);
    localizeTimes();
    if (countMessages() > before) { scrollToEnd(); }
  }

  function refresh() {
    if (refreshing || !liveSrc) { return; }
    refreshing = true;
    fetch(liveSrc, { credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok) { throw new Error("fragment"); }
        return response.text();
      })
      .then(replaceRegion)
      .catch(function () {})
      .then(function () { refreshing = false; });
  }

  function relevant(event) {
    if (!event || typeof event !== "object") { return false; }
    if (event.type === "hello") { return true; }
    if (event.type !== "message" && event.type !== "case_created" &&
        event.type !== "case_updated" && event.type !== "purchase_intent") {
      return false;
    }
    if (!caseId) { return true; }
    return event.case_id === caseId;
  }

  function startPolling() {
    if (pollTimer !== null || pollSeconds <= 0) { return; }
    pollTimer = window.setInterval(refresh, pollSeconds * 1000);
  }

  function stopPolling() {
    if (pollTimer !== null) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function scheduleReconnect() {
    if (reconnectTimer !== null) { return; }
    reconnectTimer = window.setTimeout(function () {
      reconnectTimer = null;
      connect();
    }, retryDelay);
    retryDelay = Math.min(retryDelay * 2, BACKOFF_MAX_MS);
  }

  function connect() {
    if (!wsPath) { return; }
    var scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
    var url = scheme + "//" + window.location.host + wsPath;
    try {
      socket = new WebSocket(url);
    } catch (error) {
      startPolling();
      scheduleReconnect();
      return;
    }
    socket.onopen = function () {
      retryDelay = BACKOFF_INITIAL_MS;
      stopPolling();
    };
    socket.onmessage = function (message) {
      var event = null;
      try { event = JSON.parse(message.data); } catch (error) { return; }
      if (relevant(event)) { refresh(); }
    };
    socket.onerror = function () { startPolling(); };
    socket.onclose = function () { startPolling(); scheduleReconnect(); };
  }

  localizeTimes();
  scrollToEnd();
  connect();
  startPolling();
})();
"""
