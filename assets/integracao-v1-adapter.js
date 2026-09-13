/* Adaptador explícito: borda legada do frontend -> contrato supleno.integracao.v1. */
(function (global) {
  'use strict';
  function adaptarCapturaV1(legado) {
    var product = legado && (legado.product || legado.teste);
    if (!legado || !product || !legado.submission_id) throw new Error('captura inválida');
    var capturedAt = legado.date || new Date().toISOString();
    var result = legado.resultado || legado.result || {};
    if (product === 'estilos' && typeof result === 'string') result = { code: result };
    return {
      contract: 'supleno.integracao.v1',
      submission_id: String(legado.submission_id),
      product: product,
      person: { name: legado.name, email: legado.email, whatsapp: legado.whatsapp || '' },
      result: result,
      scores: legado.pontuacoes || legado.scores || {},
      consent: {
        granted: legado.consentimento === true,
        captured_at: capturedAt,
        purpose: 'resultado_e_sequencia_supleno',
        version: '1'
      },
      attribution: {
        utm_source: legado.utm_source || '',
        utm_medium: legado.utm_medium || '',
        utm_campaign: legado.utm_campaign || '',
        origin: legado.origem || 'local'
      },
      opt_out: false
    };
  }
  global.adaptarCapturaV1 = adaptarCapturaV1;
})(typeof window !== 'undefined' ? window : globalThis);
