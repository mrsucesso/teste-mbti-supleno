/* Progresso local dos testes Supleno.
 * Não armazena nome, e-mail ou WhatsApp. Guarda só respostas/progresso/resultados.
 * Schema 1, retenção curta de 7 dias e migração explícita de versões conhecidas.
 */
(function (global) {
  'use strict';
  var SCHEMA = 1;
  var TTL_MS = 7 * 24 * 60 * 60 * 1000;
  var KEY_PREFIX = 'supleno:progresso:';
  var MAX_RESPONSES = 100;
  var PRODUCTS = { tipos: true, estilos: true, tracos: true };
  var VALID_TIPOS = { E: true, I: true, S: true, N: true, T: true, F: true, J: true, P: true };
  var VALID_TIPO_RESULTS = { ISTJ: true, ISFJ: true, INFJ: true, INTJ: true, ISTP: true, ISFP: true, INFP: true, INTP: true, ESTP: true, ESFP: true, ENFP: true, ENTP: true, ESTJ: true, ESFJ: true, ENFJ: true, ENTJ: true };
  var VALID_ESTILOS = { D: true, I: true, S: true, C: true };
  var VALID_TRACOS = { 1: true, 2: true, 3: true, 4: true, 5: true };
  var memory = {};

  function storage() {
    try { return global.localStorage; } catch (e) { return null; }
  }
  function key(produto) { return KEY_PREFIX + produto; }
  function isValidRecord(value, produto) {
    if (!value || value.schema !== SCHEMA || value.produto !== produto || !PRODUCTS[produto]) return false;
    if (!Number.isFinite(value.expiresAt) || value.expiresAt <= Date.now()) return false;
    if (!Array.isArray(value.respostas) || value.respostas.length > MAX_RESPONSES) return false;
    if (!Number.isInteger(value.progresso) || value.progresso < 0 || value.progresso > value.respostas.length) return false;
    if (value.ordem !== null) {
      if (!Array.isArray(value.ordem) || value.ordem.length !== value.respostas.length || value.ordem.length > MAX_RESPONSES) return false;
      var indices = {};
      for (var i = 0; i < value.ordem.length; i++) {
        if (!Number.isInteger(value.ordem[i]) || value.ordem[i] < 0 || value.ordem[i] >= value.respostas.length || indices[value.ordem[i]]) return false;
        indices[value.ordem[i]] = true;
      }
    }
    if (!value.respostas.every(function (answer) {
      if (answer === null) return true;
      if (produto === 'tracos') return VALID_TRACOS[answer] === true;
      return (produto === 'tipos' ? VALID_TIPOS : VALID_ESTILOS)[answer] === true;
    })) return false;
    if (value.resultado !== null && !validResult(value.resultado, produto)) return false;
    return true;
  }
  function validResult(result, produto) {
    if (produto === 'tipos') return !!result && Object.keys(result).length === 2 && VALID_TIPO_RESULTS[result.code] === true && (result.gender === 'M' || result.gender === 'F');
    if (produto === 'estilos') return typeof result === 'string' && VALID_ESTILOS[result] === true;
    var dimensions = { SO: true, AN: true, OM: true, TE: true, CO: true };
    if (!result || typeof result !== 'object') return false;
    return Object.keys(result).length === 5 && Object.keys(result).every(function (dim) {
      var item = result[dim];
      return dimensions[dim] === true && item && Object.keys(item).length === 3 && Number.isInteger(item.sum) && item.sum >= 5 && item.sum <= 25 &&
        Number.isInteger(item.percent) && item.percent >= 0 && item.percent <= 100 &&
        (item.faixa === 'baixo' || item.faixa === 'medio' || item.faixa === 'alto');
    });
  }
  function read(produto) {
    var raw = null;
    try { raw = storage() && storage().getItem(key(produto)); } catch (e) { raw = null; }
    if (!raw) raw = memory[produto] ? JSON.stringify(memory[produto]) : null;
    if (!raw) return null;
    try {
      var value = JSON.parse(raw);
      if (value.schema !== SCHEMA) return migrate(value, produto);
      if (!isValidRecord(value, produto)) { remove(produto); return null; }
      return value;
    } catch (e) { remove(produto); return null; }
  }
  function migrate(value, produto) {
    if (value && value.schema === 0 && Array.isArray(value.respostas)) {
      var migrated = { schema: SCHEMA, produto: produto, respostas: value.respostas,
        progresso: value.progresso || 0, resultado: value.resultado || null, ordem: Array.isArray(value.ordem) ? value.ordem.slice() : null,
        expiresAt: Date.now() + TTL_MS };
      if (isValidRecord(migrated, produto)) { save(produto, migrated); return migrated; }
    }
    remove(produto); return null;
  }
  function save(produto, data) {
    var safe = { schema: SCHEMA, produto: produto,
      respostas: Array.isArray(data.respostas) ? data.respostas.slice() : [],
      progresso: Number.isFinite(data.progresso) ? data.progresso : 0,
      resultado: data.resultado || null, ordem: Array.isArray(data.ordem) ? data.ordem.slice() : null,
      expiresAt: Date.now() + TTL_MS };
    if (!isValidRecord(safe, produto)) return null;
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
