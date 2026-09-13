/* Compartilhamento local, sem PII. Inclui Web Share, Clipboard e fallback acessível. */
(function (global) {
  'use strict';
  function status(message) {
    var node = global.document && global.document.querySelector('[data-progress-status]');
    if (node) { node.setAttribute('aria-live', 'polite'); node.textContent = message; }
  }
  function resultText() {
    var body = global.document && global.document.body;
    var produto = body ? body.getAttribute('data-produto') : 'Supleno';
    var result = global.document && global.document.querySelector('.result-type, #resScores, #resDetails');
    return 'Meu resultado no Supleno ' + produto + ': ' + (result ? result.textContent.replace(/\s+/g, ' ').trim() : 'Confira meu resultado');
  }
  function copy(text) {
    if (global.navigator && global.navigator.clipboard && global.navigator.clipboard.writeText) {
      return global.navigator.clipboard.writeText(text).then(function () {
        status('Texto do resultado copiado.');
        return true;
      }).catch(function () { return fallbackCopy(text); });
    }
    return fallbackCopy(text);
  }
  function fallbackCopy(text) {
    var area = global.document.createElement('textarea');
    area.value = text; area.setAttribute('readonly', ''); area.className = 'visually-hidden';
    global.document.body.appendChild(area); area.select();
    var copied = false;
    try { copied = global.document.execCommand('copy'); } catch (e) {}
    area.remove();
    if (!copied && global.document) {
      var fallback = global.document.querySelector('[data-share-fallback]');
      if (!fallback) {
        fallback = global.document.createElement('textarea');
        fallback.setAttribute('data-share-fallback', ''); fallback.setAttribute('aria-label', 'Texto do resultado para copiar');
        fallback.className = 'share-fallback'; global.document.querySelector('.result-actions').appendChild(fallback);
      }
      fallback.value = text; fallback.hidden = false; fallback.focus(); fallback.select();
    }
    status(copied ? 'Texto do resultado copiado.' : 'Não foi possível copiar automaticamente. Selecione e copie o texto abaixo.');
    return Promise.resolve(copied);
  }
  function share() {
    var text = resultText();
    if (global.navigator && typeof global.navigator.share === 'function') {
      return global.navigator.share({ title: 'Meu resultado no Supleno', text: text, url: global.location.href })
        .then(function () { status('Resultado compartilhado.'); })
        .catch(function (error) { if (error && error.name !== 'AbortError') return copy(text); });
    }
    return copy(text);
  }
  function bind() {
    if (!global.document) return;
    global.document.querySelectorAll('[data-share-result]').forEach(function (button) { button.addEventListener('click', share); });
    global.document.querySelectorAll('[data-print-result]').forEach(function (button) { button.addEventListener('click', function () { window.print(); }); });
  }
  global.SuplenoCompartilhamento = { compartilhar: share, copiar: copy, textoResultado: resultText };
  if (global.document) global.document.addEventListener('DOMContentLoaded', bind);
})(typeof window !== 'undefined' ? window : globalThis);
