/*
 * Testes Supleno — instrumentação de funil compartilhada (ver README > Métricas).
 *
 * Seis eventos de funil, comuns aos três produtos: início, progresso,
 * conclusão, resultado, captura e CTA. Nenhuma tag real é disparada
 * enquanto GA4_ID/META_PIXEL_ID não estiverem confirmados em config.js
 * (o mesmo padrão de "vazio = desligado" usado em WEBHOOK_URL). Mesmo com
 * IDs configurados, exige ANALYTICS.ENABLED=true, respeita "Do Not Track"
 * do navegador e, para o evento de captura (dado pessoal), exige consentimento
 * explícito do formulário antes de disparar qualquer envio externo.
 *
 * Sem IDs configurados, todo evento fica só em memória local
 * (SuplenoFunil._getEventLog()), sem nenhuma chamada de rede.
 */
(function (global) {
  'use strict';

  var injected = { ga4: false, metaPixel: false };
  var eventLog = [];

  function readConfig() {
    var cfg = (global.SUPLENO_CONFIG && global.SUPLENO_CONFIG.ANALYTICS) || {};
    return {
      enabled: cfg.ENABLED === true,
      ga4Id: typeof cfg.GA4_ID === 'string' ? cfg.GA4_ID.trim() : '',
      metaPixelId: typeof cfg.META_PIXEL_ID === 'string' ? cfg.META_PIXEL_ID.trim() : '',
      requireConsent: cfg.REQUIRE_CONSENT !== false
    };
  }

  function hasDoNotTrack() {
    try {
      var nav = global.navigator || {};
      return nav.doNotTrack === '1' || nav.doNotTrack === 'yes' || global.doNotTrack === '1';
    } catch (e) {
      return false;
    }
  }

  function idsConfirmed(config) {
    return !!(config.ga4Id || config.metaPixelId);
  }

  function canDispatch(config, requiresConsent, consentGranted) {
    if (!config.enabled) return false;
    if (!idsConfirmed(config)) return false;
    if (hasDoNotTrack()) return false;
    if (requiresConsent && config.requireConsent && !consentGranted) return false;
    return true;
  }

  function ensureGA4(config) {
    if (injected.ga4 || !config.ga4Id || typeof document === 'undefined') return;
    injected.ga4 = true;
    global.dataLayer = global.dataLayer || [];
    global.gtag = global.gtag || function () { global.dataLayer.push(arguments); };
    global.gtag('js', new Date());
    global.gtag('config', config.ga4Id, { anonymize_ip: true });
    var script = document.createElement('script');
    script.async = true;
    script.src = 'https://www.googletagmanager.com/gtag/js?id=' + encodeURIComponent(config.ga4Id);
    if (document.head) document.head.appendChild(script);
  }

  function ensureMetaPixel(config) {
    if (injected.metaPixel || !config.metaPixelId || typeof document === 'undefined') return;
    injected.metaPixel = true;
    global.fbq = global.fbq || function () { (global.fbq.queue = global.fbq.queue || []).push(arguments); };
    var script = document.createElement('script');
    script.async = true;
    script.src = 'https://connect.facebook.net/en_US/fbevents.js';
    if (document.head) document.head.appendChild(script);
    global.fbq('init', config.metaPixelId);
  }

  function dispatch(eventName, detail, requiresConsent, consentGranted) {
    var config = readConfig();
    var dispatched = canDispatch(config, !!requiresConsent, !!consentGranted);
    if (dispatched) {
      ensureGA4(config);
      ensureMetaPixel(config);
      if (typeof global.gtag === 'function') global.gtag('event', eventName, detail || {});
      if (typeof global.fbq === 'function') global.fbq('trackCustom', eventName, detail || {});
    }
    var record = { event: eventName, detail: detail || {}, dispatched: dispatched, ts: Date.now() };
    eventLog.push(record);
    if (global.console && typeof global.console.debug === 'function') {
      global.console.debug('[SuplenoFunil]', eventName, dispatched ? '(enviado)' : '(local apenas)', detail || {});
    }
    return record;
  }

  var SuplenoFunil = {
    // Início do teste (primeira pergunta exibida).
    trackInicio: function (produto, extra) {
      return dispatch('funil_inicio', Object.assign({ produto: produto }, extra));
    },
    // Progresso ao longo do quiz (a cada pergunta respondida).
    trackProgresso: function (produto, extra) {
      return dispatch('funil_progresso', Object.assign({ produto: produto }, extra));
    },
    // Quiz respondido por completo, antes do resultado ser calculado/exibido.
    trackConclusao: function (produto, extra) {
      return dispatch('funil_conclusao', Object.assign({ produto: produto }, extra));
    },
    // Tela de resultado efetivamente exibida ao usuário.
    trackResultado: function (produto, extra) {
      return dispatch('funil_resultado', Object.assign({ produto: produto }, extra));
    },
    // Envio do formulário opcional de captura — evento com dado pessoal:
    // exige consentGranted=true (checkbox de consentimento) para disparar
    // qualquer tag real, mesmo com IDs configurados.
    trackCaptura: function (produto, extra, consentGranted) {
      return dispatch('funil_captura', Object.assign({ produto: produto }, extra), true, consentGranted);
    },
    // Clique em CTA (link para o Supleno, página completa de resultado etc.).
    trackCTA: function (produto, extra) {
      return dispatch('funil_cta', Object.assign({ produto: produto }, extra));
    },
    // Uso interno/testes: nunca é enviado a lugar nenhum.
    _getEventLog: function () { return eventLog.slice(); },
    _reset: function () { eventLog = []; injected = { ga4: false, metaPixel: false }; }
  };

  global.SuplenoFunil = SuplenoFunil;

  // CTA é medido por delegação, evitando alterar cada template de resultado.
  function bindCTAs() {
    if (typeof document === 'undefined' || !document.addEventListener) return;
    document.addEventListener('click', function (event) {
      var target = event.target && event.target.closest ? event.target.closest('a,button') : null;
      if (!target) return;
      var href = target.getAttribute('href') || '';
      if (target.hasAttribute('data-funil-cta') || /supleno\.com/i.test(href)) {
        SuplenoFunil.trackCTA(document.body && document.body.dataset.produto || 'desconhecido', {
          destino: target.getAttribute('data-funil-cta') || 'link'
        });
      }
    }, { passive: true });
  }
  bindCTAs();
})(typeof window !== 'undefined' ? window : globalThis);
