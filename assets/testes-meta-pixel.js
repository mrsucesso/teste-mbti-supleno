/* Testes Supleno: Meta Pixel somente após consentimento explícito.
   Não envia respostas, resultado, perfil, nome, e-mail ou telefone. */
(function (global) {
  'use strict';
  var PIXEL_ID = '1821967018037838';
  var STORAGE_KEY = 'testes-supleno-meta-consent-v1';
  var consent = null;
  try { consent = global.localStorage.getItem(STORAGE_KEY); } catch (_) {}

  function start() {
    if (global.__testesSuplenoMetaPixelStarted) return;
    global.__testesSuplenoMetaPixelStarted = true;
    global.fbq = global.fbq || function () { (global.fbq.queue = global.fbq.queue || []).push(arguments); };
    var script = document.createElement('script');
    script.async = true;
    script.src = 'https://connect.facebook.net/en_US/fbevents.js';
    document.head.appendChild(script);
    global.fbq('consent', 'grant');
    global.fbq('init', PIXEL_ID);
    global.fbq('track', 'PageView');
  }

  function save(value) {
    consent = value;
    try { global.localStorage.setItem(STORAGE_KEY, value); } catch (_) {}
  }

  function showBanner() {
    if (consent || !document.body) return;
    var banner = document.createElement('section');
    banner.className = 'testes-meta-consent';
    banner.setAttribute('aria-label', 'Preferências de medição');
    banner.innerHTML = '<p>Podemos usar medição de anúncios para entender visitas às páginas públicas dos Testes Supleno? Não enviamos suas respostas, resultado, nome, e-mail ou telefone para a Meta.</p><button type="button" data-meta-choice="yes">Permitir medição</button><button type="button" data-meta-choice="no">Agora não</button>';
    banner.addEventListener('click', function (event) {
      var button = event.target.closest && event.target.closest('button[data-meta-choice]');
      if (!button) return;
      save(button.getAttribute('data-meta-choice'));
      if (consent === 'yes') start();
      banner.remove();
    });
    document.body.appendChild(banner);
  }

  var style = document.createElement('style');
  style.textContent = '.testes-meta-consent{position:fixed;right:16px;bottom:16px;z-index:9999;max-width:500px;padding:16px;border:1px solid #ddd;border-radius:12px;background:#fff;color:#1c2730;box-shadow:0 8px 30px #0003;font:14px/1.5 system-ui,sans-serif}.testes-meta-consent p{margin:0 0 12px}.testes-meta-consent button{margin:0 8px 4px 0;padding:9px 12px;border:1px solid #1f5f4b;border-radius:8px;background:#1f5f4b;color:#fff;cursor:pointer;font:inherit}.testes-meta-consent button[data-meta-choice="no"]{background:#fff;color:#1f5f4b}';
  document.head.appendChild(style);

  if (consent === 'yes') start();
  else if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', showBanner, { once: true });
  else showBanner();
})(window);
