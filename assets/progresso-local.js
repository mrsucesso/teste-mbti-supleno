/* Progresso local dos testes Supleno.
 * Não armazena nome, e-mail ou WhatsApp. Guarda só respostas/progresso/resultados.
 * Schema 1, retenção curta de 7 dias e migração explícita de versões conhecidas.
 */
(function (global) {
  'use strict';
  var SCHEMA = 1;
  var TTL_MS = 7 * 24 * 60 * 60 * 1000;
  var KEY_PREFIX = 'supleno:progresso:';
  var memory = {};

  function storage() {
    try { return global.localStorage; } catch (e) { return null; }
  }
  function key(produto) { return KEY_PREFIX + produto; }
  function read(produto) {
    var raw = null;
    try { raw = storage() && storage().getItem(key(produto)); } catch (e) { raw = null; }
    if (!raw) raw = memory[produto] ? JSON.stringify(memory[produto]) : null;
    if (!raw) return null;
    try {
      var value = JSON.parse(raw);
      if (!value || value.expiresAt <= Date.now()) { remove(produto); return null; }
      if (value.schema !== SCHEMA) return migrate(value, produto);
      return value;
    } catch (e) { remove(produto); return null; }
  }
  function migrate(value, produto) {
    if (value && value.schema === 0 && Array.isArray(value.respostas)) {
      var migrated = { schema: SCHEMA, produto: produto, respostas: value.respostas,
        progresso: value.progresso || 0, resultado: value.resultado || null, ordem: Array.isArray(value.ordem) ? value.ordem.slice() : null,
        expiresAt: Date.now() + TTL_MS };
      save(produto, migrated);
      return migrated;
    }
    remove(produto); return null;
  }
  function save(produto, data) {
    var safe = { schema: SCHEMA, produto: produto,
      respostas: Array.isArray(data.respostas) ? data.respostas.slice() : [],
      progresso: Number.isFinite(data.progresso) ? data.progresso : 0,
      resultado: data.resultado || null, ordem: Array.isArray(data.ordem) ? data.ordem.slice() : null,
      expiresAt: Date.now() + TTL_MS };
    memory[produto] = safe;
    try { if (storage()) storage().setItem(key(produto), JSON.stringify(safe)); } catch (e) {}
    return safe;
  }
  function remove(produto) {
    delete memory[produto];
    try { if (storage()) storage().removeItem(key(produto)); } catch (e) {}
  }
  function bind() {
    if (!global.document) return;
    global.document.querySelectorAll('[data-reset-progress]').forEach(function (button) {
      button.addEventListener('click', function () {
        var produto = document.body.getAttribute('data-produto');
        remove(produto);
        var status = document.querySelector('[data-progress-status]');
        if (status) { status.textContent = 'Progresso apagado. Você pode recomeçar.'; }
        global.dispatchEvent(new CustomEvent('supleno:progresso-apagado'));
      });
    });
  }
  global.SuplenoProgresso = { schema: SCHEMA, ttlDias: 7, ler: read, salvar: save, apagar: remove, migrar: migrate };
  if (global.document) global.document.addEventListener('DOMContentLoaded', bind);
})(typeof window !== 'undefined' ? window : globalThis);
