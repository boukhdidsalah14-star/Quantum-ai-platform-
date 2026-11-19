/* HypeLab web banner bootstrap using the publisher embed code. */
(function () {
  "use strict";

  const PROPERTY_SLUG = "858f14de4e";
  const PLACEMENT_SLUG = "d0d059e274";
  const SDK_URL = "https://api.hypelab.com/v1/scripts/hp-sdk.js?v=0";
  const BANNER_ID = "quantum-hypelab-slot";

  function report(event, extra) {
    const payload = Object.assign({
      event: event,
      sdk_loaded: false,
      init_available: false,
      custom_element_defined: false,
      banner_has_content: false,
      adsense_configured: false,
      banner_height: 0
    }, extra || {});
    try {
      fetch("/api/ads/diagnostics", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        keepalive: true
      }).catch(function () {});
    } catch (_) {}
  }

  window.addEventListener("error", function () { report("frontend_error"); });
  window.addEventListener("unhandledrejection", function () { report("frontend_rejection"); });

  function setStatus(message, hidden) {
    const status = document.getElementById("ad-status");
    if (!status) return;
    status.textContent = message;
    status.hidden = !!hidden;
  }

  function inspectBanner() {
    const banner = document.getElementById(BANNER_ID);
    const slot = document.getElementById("quantum-bottom-ad");
    const shadow = banner && banner.shadowRoot;
    const hasHypeContent = !!(banner && (
      banner.childElementCount ||
      (shadow && shadow.childElementCount) ||
      banner.querySelector("img,iframe,a,video") ||
      (shadow && shadow.querySelector("img,iframe,a,video"))
    ));
    const hasGoogleContent = !!(slot && slot.getBoundingClientRect().height > 20 &&
      slot.querySelector("iframe,img"));
    const hasContent = hasHypeContent || hasGoogleContent;
    const height = banner ? Math.round(banner.getBoundingClientRect().height) : 0;

    if (hasContent) {
      setStatus("", true);
      report("banner_rendered", {
        sdk_loaded: true,
        init_available: true,
        banner_has_content: true,
        banner_height: height
      });
    } else {
      setStatus("No sponsored ad available right now.", false);
      report("banner_empty", {
        sdk_loaded: !!window.HypeLab,
        init_available: !!(window.HypeLab && typeof HypeLab.Client === "function"),
        banner_has_content: false,
        banner_height: height
      });
    }
  }

  function initializeHypeLab() {
    const container = document.getElementById(BANNER_ID);
    if (!container) { report("banner_empty"); return; }
    setStatus("Loading sponsored content…", false);
    report("sdk_load_started");
    const script = document.createElement("script");
    script.src = SDK_URL;
    script.defer = true;
    script.onload = function () {
      const api = window.HypeLab;
      const supported = !!(api && typeof api.initialize === "function");
      report("sdk_loaded", { sdk_loaded: !!api, init_available: supported, custom_element_defined: !!(window.customElements && customElements.get("hype-banner")) });
      if (!supported) { report("sdk_api_missing", { sdk_loaded: !!api, init_available: false }); setStatus("Ad provider integration needs attention.", false); return; }
      try {
        api.initialize({ environment: "production", propertySlug: PROPERTY_SLUG });
        report("sdk_initialized", { sdk_loaded: true, init_available: true });
        window.setTimeout(inspectBanner, 5000);
        window.setTimeout(inspectBanner, 12000);
        window.setTimeout(inspectBanner, 30000);
      } catch (_) { report("sdk_init_failed", { sdk_loaded: true, init_available: true }); setStatus("Ad provider could not initialize.", false); }
    };
    script.onerror = function () { report("sdk_load_failed"); setStatus("Ad provider could not be reached.", false); };
    document.head.appendChild(script);
  }

  function initializeAdSense() {
    const slot = document.getElementById("quantum-bottom-ad");
    if (!slot) return;

    fetch("/api/ads/config", { headers: { "Accept": "application/json" } })
      .then(function (response) {
        if (!response.ok) throw new Error("Ad configuration unavailable");
        return response.json();
      })
      .then(function (config) {
        const validClient = /^ca-pub-\\d+$/.test(config.client_id || "");
        const validSlot = /^\\d+$/.test(config.slot_id || "");
        if (!config.enabled || !validClient || !validSlot) {
          report("adsense_disabled");
          return;
        }

        report("adsense_configured", { adsense_configured: true });
        slot.setAttribute("data-ad-client", config.client_id);
        slot.setAttribute("data-ad-slot", config.slot_id);
        slot.style.display = "block";

        const script = document.createElement("script");
        script.async = true;
        script.crossOrigin = "anonymous";
        script.src = "https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=" +
          encodeURIComponent(config.client_id);
        report("adsense_load_started", { adsense_configured: true });
        script.onload = function () {
          try {
            (window.adsbygoogle = window.adsbygoogle || []).push({});
          } catch (_) {
            report("adsense_load_failed", { adsense_configured: true });
          }
        };
        script.onerror = function () {
          report("adsense_load_failed", { adsense_configured: true });
        };
        document.head.appendChild(script);
      })
      .catch(function () { report("adsense_disabled"); });
  }

  function start() {
    initializeHypeLab();
    initializeAdSense();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, { once: true });
  } else {
    start();
  }
})();