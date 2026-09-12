/*
 * Modelo de configuração do Supleno Tipos.
 *
 * Copie este arquivo para "config.js" (ignorado pelo git — ver .gitignore)
 * e preencha os valores reais antes de publicar em produção.
 *
 * NUNCA edite WEBHOOK_URL ou CONFIG_TOKEN direto no index.html: esses
 * valores não são versionados. Enquanto config.js não existir (ou
 * WEBHOOK_URL estiver vazio), o site funciona em modo aberto/local —
 * o teste roda normalmente, mas nenhum lead é gravado ou enviado por e-mail.
 *
 * CONFIG_TOKEN NÃO é um segredo: ele viaja dentro do HTML/JS do site e
 * qualquer visitante pode lê-lo no código-fonte. Ele serve apenas como
 * filtro casual contra bots genéricos que disparam POSTs direto para a
 * URL do Web App sem nunca ter carregado o site (ver README > Antiabuso).
 * Use o MESMO valor aqui e em ACCESS_TOKEN no apps-script/Code.gs.
 */
window.SUPLENO_CONFIG = {
  CTA_URL: "https://supleno.com",
  WEBHOOK_URL: "",
  CONFIG_TOKEN: "",
  // Métricas ficam desligadas até IDs e consentimento serem confirmados.
  ANALYTICS: { ENABLED: false, GA4_ID: "", META_PIXEL_ID: "", REQUIRE_CONSENT: true }
};
