/* The "Alert me about this water" control (DECISIONS 0069). Served as
   assets/push.js and loaded, deferred, by the calendar box of a water page
   that has it (_push_subscribe.html.jinja). Plain script, no bundler.

   decide() is the whole policy, kept pure so pipeline/tests/test_site_push.py
   can run it under node: which one view the box shows, from what the browser
   reports. The rest is wiring: the permission prompt behind a tap, the
   service worker at the site root (so its scope covers every water page),
   the subscription, and the two calls to the site's own service.

   Nothing here reads anything but the box's own data attributes, this site's
   localStorage key, and the browser's own permission and subscription state.
   The subscription (endpoint and keys) goes to the service named in the box;
   nothing goes anywhere else. */
(function () {
  "use strict";

  var STORAGE_KEY = "trout-truck:push";

  function isIOS(nav) {
    var ua = nav.userAgent || "";
    // iPadOS reports itself as a Mac with touch points.
    return /iPhone|iPad|iPod/.test(ua) || (nav.platform === "MacIntel" && (nav.maxTouchPoints || 0) > 1);
  }

  /* env: userAgent, platform, maxTouchPoints, standalone (navigator.standalone
     or display-mode: standalone), secureContext, serviceWorker, pushManager,
     notification (the three "in" checks), permission ("default" | "granted" |
     "denied"), saved ({water_id, water_name, endpoint} or null), waterId.
     Returns {view, otherName}. */
  function decide(env) {
    var ios = isIOS({ userAgent: env.userAgent, platform: env.platform, maxTouchPoints: env.maxTouchPoints });
    if (ios && !env.standalone) return { view: "ios" };
    if (!env.secureContext || !env.serviceWorker || !env.pushManager || !env.notification) {
      return { view: "unsupported" };
    }
    if (env.permission === "denied") return { view: "blocked" };
    if (env.saved && env.saved.water_id === env.waterId) return { view: "on" };
    if (env.saved && env.saved.water_id) return { view: "idle", otherName: env.saved.water_name || "another water" };
    return { view: "idle" };
  }

  /* Where keyboard focus goes once a press has been answered. The pressed
     button sits in a view that the press hides, so without this focus falls
     to the top of the page and a screen reader hears nothing. "idle" can be
     pressed again, so focus returns to its button and the status line says
     what happened. Every other view is words that answer the press ("This
     browser gets a notification...", "Notifications ... are blocked"), so
     focus goes to those words and a screen reader reads them. */
  function focusAfter(view) {
    return view === "idle" ? "button" : "view";
  }

  // node (the tests): export the policy and stop.
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { decide: decide, isIOS: isIOS, focusAfter: focusAfter };
    return;
  }
  if (typeof document === "undefined") return;

  var box = document.querySelector(".push-subscribe");
  if (!box) return;
  var cfg = {
    api: box.getAttribute("data-push-api"),
    key: box.getAttribute("data-push-public"),
    water: box.getAttribute("data-push-water"),
    waterName: box.getAttribute("data-push-water-name"),
    worker: box.getAttribute("data-push-worker"),
    scope: box.getAttribute("data-push-scope")
  };
  if (!cfg.api || !cfg.key || !cfg.water || !cfg.worker) return;

  function readSaved() {
    try {
      var raw = window.localStorage.getItem(STORAGE_KEY);
      var parsed = raw ? JSON.parse(raw) : null;
      return parsed && typeof parsed === "object" && parsed.water_id ? parsed : null;
    } catch (e) {
      return null;
    }
  }
  function writeSaved(value) {
    try {
      if (value) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
      else window.localStorage.removeItem(STORAGE_KEY);
    } catch (e) {
      // Nothing to do: the server copy is what sends, and the page re-reads
      // the browser's own subscription on the next visit.
    }
  }

  function env() {
    var saved = readSaved();
    return {
      userAgent: navigator.userAgent,
      platform: navigator.platform,
      maxTouchPoints: navigator.maxTouchPoints,
      standalone: navigator.standalone === true ||
        !!(window.matchMedia && window.matchMedia("(display-mode: standalone)").matches),
      secureContext: window.isSecureContext !== false,
      serviceWorker: "serviceWorker" in navigator,
      pushManager: "PushManager" in window,
      notification: "Notification" in window,
      permission: ("Notification" in window) ? Notification.permission : "default",
      saved: saved,
      waterId: cfg.water
    };
  }

  var status = box.querySelector("[data-push-status]");
  function say(message) {
    if (status) status.textContent = message || "";
  }
  function show(view, otherName) {
    var views = box.querySelectorAll("[data-push-view]");
    for (var i = 0; i < views.length; i++) {
      views[i].hidden = views[i].getAttribute("data-push-view") !== view;
    }
    var other = box.querySelector("[data-push-other]");
    var name = box.querySelector("[data-push-other-name]");
    if (other) other.hidden = !otherName;
    if (name) name.textContent = otherName || "";
    box.hidden = false;
  }
  // After a press only (never on load): put focus on what answers the press,
  // unless the visitor has already moved it somewhere else on the page.
  function moveFocus(view) {
    var active = document.activeElement;
    if (active && active !== document.body && active !== document.documentElement && !box.contains(active)) return;
    var shown = box.querySelector('[data-push-view="' + view + '"]');
    if (!shown) return;
    var target = shown;
    if (focusAfter(view) === "button") target = shown.querySelector("[data-push-action]") || shown;
    // Focusable from script only: the words are not a Tab stop.
    if (target === shown) shown.setAttribute("tabindex", "-1");
    target.focus();
  }
  function render(message, pressed) {
    var d = decide(env());
    show(d.view, d.otherName);
    say(message);
    if (pressed) moveFocus(d.view);
  }
  // A press hides the button that was pressed. Focus goes to the "Setting it
  // up" words, so it is never left on nothing and a screen reader reads them.
  function working() {
    show("busy");
    say("");
    moveFocus("busy");
  }

  function toKey(base64url) {
    var padding = "=".repeat((4 - (base64url.length % 4)) % 4);
    var raw = window.atob((base64url + padding).replace(/-/g, "+").replace(/_/g, "/"));
    var out = new Uint8Array(raw.length);
    for (var i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
    return out;
  }

  function registration() {
    return navigator.serviceWorker.register(cfg.worker, { scope: cfg.scope }).then(function (reg) {
      if (reg.active) return reg;
      var worker = reg.installing || reg.waiting;
      // A worker that fails to install turns "redundant" and never
      // "activated"; without the reject the box would say "Setting it up"
      // for good.
      return new Promise(function (resolve, reject) {
        if (!worker) return resolve(reg);
        function settle() {
          if (worker.state === "activated") resolve(reg);
          else if (worker.state === "redundant") reject(new Error("this browser did not finish setting up notifications"));
        }
        worker.addEventListener("statechange", settle);
        settle();
      });
    });
  }

  function post(path, body) {
    return window.fetch(cfg.api + path, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body)
    });
  }

  function reason(err) {
    return err && err.message ? err.message : "unknown error";
  }

  function subscribe() {
    working();
    var created = null;
    return Notification.requestPermission().then(function (permission) {
      if (permission !== "granted") {
        render(permission === "denied" ? "" : "No notification was set up. Press the button again when you want one.", true);
        return null;
      }
      return registration().then(function (reg) {
        return reg.pushManager.getSubscription().then(function (existing) {
          if (existing) return existing;
          return reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: toKey(cfg.key) })
            .then(function (sub) { created = sub; return sub; });
        });
      }).then(function (sub) {
        var json = sub.toJSON();
        return post("/subscribe", {
          water_id: cfg.water,
          subscription: { endpoint: sub.endpoint, keys: json.keys }
        }).then(function (res) {
          if (!res.ok) throw new Error("the sign-up was refused (" + res.status + ")");
          writeSaved({ water_id: cfg.water, water_name: cfg.waterName, endpoint: sub.endpoint });
          render("", true);
        });
      });
    }).catch(function (err) {
      // A subscription this tap created but could not register is undone,
      // so no browser is left subscribed to nothing.
      var undo = created ? created.unsubscribe().catch(function () {}) : Promise.resolve();
      return undo.then(function () {
        render("That did not work: " + reason(err) + ". The calendar options above still work.", true);
      });
    });
  }

  function unsubscribe() {
    working();
    var saved = readSaved();
    return navigator.serviceWorker.getRegistration(cfg.scope).then(function (reg) {
      return reg ? reg.pushManager.getSubscription() : null;
    }).then(function (sub) {
      var endpoint = sub ? sub.endpoint : (saved ? saved.endpoint : null);
      var server = endpoint ? post("/unsubscribe", { endpoint: endpoint }).then(function (res) { return res.ok; }, function () { return false; }) : Promise.resolve(true);
      return server.then(function (serverOk) {
        var local = sub ? sub.unsubscribe().catch(function () { return false; }) : Promise.resolve(true);
        return local.then(function () {
          writeSaved(null);
          render(serverOk
            ? "Stopped. Nothing about this browser is kept."
            : "Stopped in this browser. The server copy goes when its next delivery fails.", true);
        });
      });
    }).catch(function (err) {
      // Without this a failed lookup (a browser that refuses service
      // workers here, say) left the box on "Setting it up" for good.
      render("Stopping did not work: " + reason(err) + ". Try again, or turn off notifications for this site in your browser's settings.", true);
    });
  }

  // The browser's own subscription is the truth; the saved note only names
  // the water. A saved note with no subscription behind it is dropped.
  function reconcile() {
    var saved = readSaved();
    var e = env();
    if (!saved || !e.serviceWorker || !e.pushManager) return Promise.resolve();
    return navigator.serviceWorker.getRegistration(cfg.scope).then(function (reg) {
      return reg ? reg.pushManager.getSubscription() : null;
    }).then(function (sub) {
      if (!sub || sub.endpoint !== saved.endpoint) writeSaved(null);
    }).catch(function () {});
  }

  box.addEventListener("click", function (event) {
    var t = event.target;
    var button = t && t.closest ? t.closest("[data-push-action]") : null;
    if (!button) return;
    if (button.getAttribute("data-push-action") === "subscribe") subscribe();
    else if (button.getAttribute("data-push-action") === "unsubscribe") unsubscribe();
  });

  render("");
  reconcile().then(function () { render(""); });
})();
