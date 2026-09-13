/**
 * TESTES SUPLENO — backend compartilhado em Google Apps Script
 * ---------------------------------------------------------
 * O que este script faz quando alguém termina o teste:
 *   1) Grava uma linha na planilha "Leads MBTI" (Nome, E-mail, Sigla, Data, WhatsApp)
 *   2) Envia um e-mail para o lead com o resultado COMPLETO (descrição,
 *      pontos fortes e caminhos de desenvolvimento) usando a conta Google
 *      responsável pela implantação
 *
 * COMO INSTALAR (uma vez só):
 *   1. Abra a planilha "Leads MBTI" (dentro da pasta "Testes de Perfil" no Drive)
 *   2. Menu Extensões > Apps Script
 *   3. Apague o conteúdo padrão e cole este arquivo inteiro
 *   4. Clique em "Implantar" > "Nova implantação"
 *      - Tipo: "App da Web"
 *      - Executar como: "Eu"
 *      - Quem pode acessar: "Qualquer pessoa"
 *   5. Autorize as permissões pedidas (Planilhas + Gmail)
 *   6. Copie a URL do app da web gerada e cole em WEBHOOK_URL no config.js
 *      do site (ver config.example.js), NUNCA direto no index.html versionado
 *      (e sempre que reimplantar, a URL pode mudar se você criar uma NOVA
 *      implantação em vez de atualizar a existente)
 *   7. (Opcional, recomendado antes de ir ao ar) defina o mesmo valor em
 *      ACCESS_TOKEN aqui embaixo e em CONFIG_TOKEN no config.js — reduz abuso
 *      casual. Veja "Antiabuso" no README para o racional completo.
 */

// Se a planilha "Leads MBTI" NÃO estiver vinculada a este script
// (ou seja, se você criou o script separadamente), cole o ID dela aqui.
// Deixe em branco ("") se o script já está vinculado à planilha
// (Extensões > Apps Script a partir de dentro da própria planilha).
const SHEET_ID = "";
const SHEET_NAME = "Leads MBTI";

// E-mail que aparece como remetente (deve ser o dono da conta que implantou o script)
const FROM_NAME = "Supleno Tipos";

// Link do botão final do e-mail
const CTA_URL = "https://supleno.com";

// Base do site publicado (para montar o link da página completa no e-mail).
// A partir da Fase 2, o teste vive em /tipos dentro do domínio da família
// Testes Supleno — troque para "https://testes.supleno.com" quando o DNS
// final estiver no ar; enquanto isso, aponte para a URL de protótipo do
// GitHub Pages (ex.: "https://usuario.github.io/repositorio").
const SITE_BASE_URL = "https://testes.supleno.com";

/* ============================================================
   ANTIABUSO — ver seção "Antiabuso" no README para o racional
   ============================================================ */
// Token de configuração NÃO SECRETO: o index.html envia este valor em todo
// envio. Ele fica visível no código-fonte do site (qualquer pessoa pode lê-lo),
// então NÃO protege contra um atacante determinado — apenas filtra bots
// genéricos que disparam POSTs para a URL do Web App sem ter visto o site.
// Configure o MESMO valor em cada config.js. Se estiver ausente, o backend
// recusa a captura: o token continua sendo apenas defesa complementar.
// Configure no Script Properties; nunca deixe um relay público em produção.
const ACCESS_TOKEN = PropertiesService.getScriptProperties().getProperty("ACCESS_TOKEN") || "";

// Limites explícitos de taxa (ver README > Antiabuso). Ajuste com cautela:
// limites baixos demais bloqueiam envios legítimos de uma mesma família/rede.
const RATE_LIMIT_PER_EMAIL_PER_DAY = 5;   // mesmo e-mail, janela de 24h
const RATE_LIMIT_GLOBAL_PER_MINUTE = 30;  // todos os envios somados, janela de 60s

// Limite de tamanho do payload recebido (proteção simples contra abuso/DoS trivial)
const MAX_PAYLOAD_BYTES = 8000;

/* ============================================================
   OPT-OUT — token HMAC assinado e opaco (ver README > "Opt-out")
   ============================================================ */
// Segredo usado para assinar o token de opt-out (HMAC-SHA256). Sem ele, nenhum
// token é gerado nem aceito: opt-out fica indisponível de forma segura
// (fail-closed) em vez de aceitar tokens forjáveis com chave vazia. Configure
// em Script Properties antes de ir ao ar — nunca deixe um valor fixo no código.
const OPTOUT_SECRET = PropertiesService.getScriptProperties().getProperty("OPTOUT_SECRET") || "";

/* ============================================================
   OUTBOX — fila persistente de e-mails (ver README > "Fila de envio (outbox)")
   ============================================================ */
// Prazo máximo que uma submissão pode ficar "processing" (idempotência) ou um
// item da outbox "sending" antes de ser elegível para reconciliação. Não é
// garantia de que o efeito externo não ocorreu — é só o momento em que
// paramos de esperar por uma confirmação que não chegou.
const PROCESSING_LEASE_MS = 2 * 60 * 1000;
const OUTBOX_LEASE_MS = 5 * 60 * 1000;

// A outbox vive numa aba dedicada da mesma Spreadsheet (uma linha por item),
// nunca em Script Properties — ver getOutboxSheet. PropertiesService guarda
// só um cursor escalar (OUTBOX_CURSOR_ROW_PROPERTY), nunca o payload da fila.
const OUTBOX_SHEET_NAME = "Outbox";
// Máximo de linhas visitadas por chamada de processarOutbox — mantém cada
// execução do gatilho de tempo curta e previsível mesmo com a aba grande.
const OUTBOX_BATCH_SIZE = 25;
// Máximo de linhas "pending" canceladas por chamada de opt-out — protege
// contra uma aba enorme travar a confirmação de cancelamento.
const OUTBOX_CANCEL_LIMIT = 500;
const OUTBOX_CURSOR_ROW_PROPERTY = "OUTBOX_CURSOR_ROW";

const VALID_GENDERS = ["M", "F"];
const NAME_PATTERN = /^[\p{L}\p{M} '.\-]{1,100}$/u;
const EMAIL_PATTERN = /^[^\s@]{1,64}@[^\s@]{1,190}\.[^\s@]{2,24}$/;
const WHATSAPP_PATTERN = /^[0-9 ()+\-]{0,20}$/;

/* ============================================================
   DADOS DOS 16 TIPOS (mesmo conteúdo do site, em formato Apps Script)
   ============================================================ */
const PROFILES = {
  "INTJ": {
    "name_m": "O Planejador Estratégico",
    "name_f": "A Planejadora Estratégica",
    "desc_m": "Você enxerga sistemas e padrões onde outros veem eventos isolados. Prefere construir uma visão de longo prazo e trilhar o caminho até ela com autonomia e método, e escolhe com cuidado quando e com quem interagir.",
    "desc_f": "Você enxerga sistemas e padrões onde outras pessoas veem eventos isolados. Prefere construir uma visão de longo prazo e trilhar o caminho até ela com autonomia e método, e escolhe com cuidado quando e com quem interagir.",
    "strengths": [
      "Pensamento estratégico e visão de longo prazo",
      "Independência para tomar decisões difíceis",
      "Alto padrão de exigência consigo e com o trabalho"
    ],
    "growth": [
      "Praticar paciência com processos e pessoas mais lentas",
      "Comunicar o raciocínio, não só a conclusão",
      "Abrir espaço para a dimensão emocional nas decisões"
    ],
    "img": "uma coruja antropomórfica de óculos, debruçada sobre um mapa estelar com linhas estratégicas e peças de xadrez"
  },
  "INTP": {
    "name_m": "O Pensador Analítico",
    "name_f": "A Pensadora Analítica",
    "desc_m": "Movido pela curiosidade, você gosta de desmontar ideias para entender como funcionam por dentro. Prefere explorar possibilidades a seguir regras prontas, e se sente mais à vontade debatendo conceitos do que cumprindo rotinas.",
    "desc_f": "Movida pela curiosidade, você gosta de desmontar ideias para entender como funcionam por dentro. Prefere explorar possibilidades a seguir regras prontas, e se sente mais à vontade debatendo conceitos do que cumprindo rotinas.",
    "strengths": [
      "Raciocínio lógico e capacidade de análise profunda",
      "Criatividade para encontrar soluções não óbvias",
      "Honestidade intelectual, mesmo quando incômoda"
    ],
    "growth": [
      "Levar ideias à prática, não só à teoria",
      "Comunicar-se de forma mais acessível",
      "Dar mais atenção a prazos e compromissos concretos"
    ],
    "img": "uma raposa antropomórfica cercada por engrenagens flutuantes, quadros-negros com fórmulas e um globo giratório"
  },
  "ENTJ": {
    "name_m": "O Líder Estratégico",
    "name_f": "A Líder Estratégica",
    "desc_m": "Você tem facilidade para organizar pessoas e recursos em torno de um objetivo claro. Decide rápido, cobra resultado e não tem medo de assumir a liderança em situações complexas.",
    "desc_f": "Você tem facilidade para organizar pessoas e recursos em torno de um objetivo claro. Decide rápido, cobra resultado e não tem medo de assumir a liderança em situações complexas.",
    "strengths": [
      "Capacidade natural de liderança e organização",
      "Clareza de objetivos e senso de urgência",
      "Disposição para tomar decisões difíceis"
    ],
    "growth": [
      "Ouvir mais antes de decidir",
      "Validar o impacto emocional das próprias decisões",
      "Delegar em vez de concentrar todas as responsabilidades"
    ],
    "img": "um leão antropomórfico em trajes executivos modernos, à frente de uma mesa com um gráfico de crescimento e uma bússola"
  },
  "ENTP": {
    "name_m": "O Provocador de Ideias",
    "name_f": "A Provocadora de Ideias",
    "desc_m": "Você gosta de questionar o óbvio e testar novas possibilidades, muitas vezes provocando o debate só para ver até onde a ideia se sustenta. Rotina e certezas fechadas tendem a te sufocar.",
    "desc_f": "Você gosta de questionar o óbvio e testar novas possibilidades, muitas vezes provocando o debate só para ver até onde a ideia se sustenta. Rotina e certezas fechadas tendem a te sufocar.",
    "strengths": [
      "Criatividade para gerar alternativas inesperadas",
      "Facilidade para debater e defender pontos de vista",
      "Adaptação rápida a mudanças"
    ],
    "growth": [
      "Levar projetos até o fim, não só até a ideia inicial",
      "Cuidar do impacto do debate nas relações",
      "Desenvolver constância em rotinas necessárias"
    ],
    "img": "um macaco antropomórfico com uma lâmpada de ideia acesa, cercado por balões de pensamento e setas em espiral"
  },
  "INFJ": {
    "name_m": "O Idealista Silencioso",
    "name_f": "A Idealista Silenciosa",
    "desc_m": "Você combina intuição apurada com profundo senso de propósito. Observa as pessoas e situações com atenção, buscando significado por trás do que é dito, e prefere poucos vínculos, mas intensos.",
    "desc_f": "Você combina intuição apurada com profundo senso de propósito. Observa as pessoas e situações com atenção, buscando significado por trás do que é dito, e prefere poucos vínculos, mas intensos.",
    "strengths": [
      "Empatia combinada com visão de longo prazo",
      "Capacidade de perceber o não dito",
      "Compromisso genuíno com valores e propósito"
    ],
    "growth": [
      "Evitar o desgaste por assumir demandas alheias como próprias",
      "Expressar necessidades antes de chegar ao limite",
      "Tolerar imperfeição no processo, não só no resultado"
    ],
    "img": "uma coruja antropomórfica serena, envolta em uma névoa de constelações suaves, segurando uma lanterna acesa"
  },
  "INFP": {
    "name_m": "O Sonhador Autêntico",
    "name_f": "A Sonhadora Autêntica",
    "desc_m": "Guiado por valores pessoais fortes, você busca coerência entre o que sente e o que faz. Tem uma vida interior rica e criativa, e se importa profundamente com autenticidade.",
    "desc_f": "Guiada por valores pessoais fortes, você busca coerência entre o que sente e o que faz. Tem uma vida interior rica e criativa, e se importa profundamente com autenticidade.",
    "strengths": [
      "Criatividade e sensibilidade estética",
      "Coerência entre valores e ações",
      "Empatia genuína pelas causas em que acredita"
    ],
    "growth": [
      "Tornar planos e ideais em passos concretos",
      "Lidar melhor com críticas diretas",
      "Estabelecer limites em relações desgastantes"
    ],
    "img": "um cervo antropomórfico jovem cercado por borboletas e aquarelas flutuantes, em um campo ao entardecer"
  },
  "ENFJ": {
    "name_m": "O Mobilizador",
    "name_f": "A Mobilizadora",
    "desc_m": "Você tem talento para inspirar e organizar pessoas em torno de um propósito comum. Sensível ao clima emocional do grupo, costuma ser a pessoa que os outros procuram para orientação e apoio.",
    "desc_f": "Você tem talento para inspirar e organizar pessoas em torno de um propósito comum. Sensível ao clima emocional do grupo, costuma ser a pessoa que os outros procuram para orientação e apoio.",
    "strengths": [
      "Facilidade para engajar e inspirar pessoas",
      "Empatia combinada com senso de organização",
      "Comunicação calorosa e persuasiva"
    ],
    "growth": [
      "Preservar a própria disposição antes de cuidar das necessidades dos outros",
      "Aceitar quando nem todos podem ser agradados",
      "Tolerar conflitos sem tentar resolvê-los de imediato"
    ],
    "img": "um golfinho antropomórfico carismático, gesticulando diante de um grupo de outros animais reunidos ao redor de uma fogueira"
  },
  "ENFP": {
    "name_m": "O Entusiasta Criativo",
    "name_f": "A Entusiasta Criativa",
    "desc_m": "Curioso e caloroso, você se conecta rápido com pessoas e ideias novas. Vê possibilidades em quase tudo e se entusiasma com projetos que unem criatividade e propósito.",
    "desc_f": "Curiosa e calorosa, você se conecta rápido com pessoas e ideias novas. Vê possibilidades em quase tudo e se entusiasma com projetos que unem criatividade e propósito.",
    "strengths": [
      "Entusiasmo contagiante e criatividade",
      "Facilidade para se conectar com pessoas diferentes",
      "Abertura genuína a novas experiências"
    ],
    "growth": [
      "Sustentar o foco até a conclusão dos projetos",
      "Organizar prioridades entre tantas possibilidades",
      "Lidar com tarefas repetitivas sem perder a motivação"
    ],
    "img": "uma raposa antropomórfica saltitante, cercada por confetes coloridos e um leque de ideias em forma de balões"
  },
  "ISTJ": {
    "name_m": "O Guardião Prático",
    "name_f": "A Guardiã Prática",
    "desc_m": "Confiável e metódico, você valoriza compromissos cumpridos e processos bem estabelecidos. É a pessoa em quem outros confiam para que as coisas aconteçam como planejado.",
    "desc_f": "Confiável e metódica, você valoriza compromissos cumpridos e processos bem estabelecidos. É a pessoa em quem outros confiam para que as coisas aconteçam como planejado.",
    "strengths": [
      "Responsabilidade e senso de compromisso",
      "Atenção a detalhes e organização",
      "Estabilidade em momentos de pressão"
    ],
    "growth": [
      "Abrir espaço para mudanças e novas abordagens",
      "Expressar emoções em vez de só sustentar a rotina",
      "Delegar tarefas em vez de concentrar todas as responsabilidades"
    ],
    "img": "um urso antropomórfico robusto em pé diante de uma estante organizada, segurando uma prancheta e um relógio de bolso"
  },
  "ISFJ": {
    "name_m": "O Cuidador Dedicado",
    "name_f": "A Cuidadora Dedicada",
    "desc_m": "Você presta atenção genuína às necessidades das pessoas ao seu redor e se doa para que elas se sintam amparadas. Discreto e leal, prefere agir nos bastidores a chamar atenção para si.",
    "desc_f": "Você presta atenção genuína às necessidades das pessoas ao seu redor e se doa para que elas se sintam amparadas. Discreta e leal, prefere agir nos bastidores a chamar atenção para si.",
    "strengths": [
      "Lealdade e cuidado consistente com os outros",
      "Atenção prática às necessidades alheias",
      "Constância em compromissos assumidos"
    ],
    "growth": [
      "Pedir ajuda antes de se esgotar cuidando dos outros",
      "Expressar as próprias necessidades com mais clareza",
      "Tolerar mudanças fora do esperado"
    ],
    "img": "um coelho antropomórfico gentil, servindo chá em uma mesa aconchegante rodeada de plantas e mantas"
  },
  "ESTJ": {
    "name_m": "O Organizador Nato",
    "name_f": "A Organizadora Nata",
    "desc_m": "Você tem talento para transformar planos em execução, com clareza de regras e responsabilidades. Direto e eficiente, prefere agir logo a ficar analisando possibilidades indefinidamente.",
    "desc_f": "Você tem talento para transformar planos em execução, com clareza de regras e responsabilidades. Direta e eficiente, prefere agir logo a ficar analisando possibilidades indefinidamente.",
    "strengths": [
      "Capacidade de organizar e executar com eficiência",
      "Clareza ao definir responsabilidades",
      "Firmeza em manter padrões e prazos"
    ],
    "growth": [
      "Flexibilizar regras quando o contexto pede",
      "Considerar o impacto emocional das decisões",
      "Ouvir pontos de vista divergentes antes de agir"
    ],
    "img": "um elefante antropomórfico em trajes de gestor, diante de um quadro branco com cronogramas e caixas de tarefas marcadas"
  },
  "ESFJ": {
    "name_m": "O Anfitrião Social",
    "name_f": "A Anfitriã Social",
    "desc_m": "Caloroso e atento aos outros, você cuida para que todos se sintam bem-vindos e incluídos. Valoriza harmonia, tradições e vínculos estáveis.",
    "desc_f": "Calorosa e atenta aos outros, você cuida para que todos se sintam bem-vindos e incluídos. Valoriza harmonia, tradições e vínculos estáveis.",
    "strengths": [
      "Facilidade para criar vínculos e acolher pessoas",
      "Senso de responsabilidade social",
      "Organização a serviço do coletivo"
    ],
    "growth": [
      "Tolerar desaprovação sem se abalar excessivamente",
      "Expressar discordância mesmo quando gera desconforto",
      "Cuidar de si com a mesma dedicação que cuida dos outros"
    ],
    "img": "um cachorro antropomórfico afável recebendo convidados em uma mesa farta, decorada com luzes quentes"
  },
  "ISTP": {
    "name_m": "O Artesão Prático",
    "name_f": "A Artesã Prática",
    "desc_m": "Você aprende fazendo, testando e ajustando na prática. Prefere resolver problemas concretos com as próprias mãos, e valoriza a liberdade para agir no seu próprio ritmo.",
    "desc_f": "Você aprende fazendo, testando e ajustando na prática. Prefere resolver problemas concretos com as próprias mãos, e valoriza a liberdade para agir no seu próprio ritmo.",
    "strengths": [
      "Habilidade prática para resolver problemas",
      "Calma sob pressão em situações concretas",
      "Independência e adaptabilidade"
    ],
    "growth": [
      "Compartilhar mais o próprio raciocínio com os outros",
      "Sustentar compromissos de longo prazo",
      "Considerar o impacto emocional das próprias ações"
    ],
    "img": "um lobo antropomórfico em uma oficina, com ferramentas penduradas e as mãos sujas de graxa consertando uma engrenagem"
  },
  "ISFP": {
    "name_m": "O Artista Sensível",
    "name_f": "A Artista Sensível",
    "desc_m": "Sensível e autêntico, você se expressa mais por ações e estética do que por grandes discursos. Vive o presente com intensidade e valoriza a liberdade para seguir o próprio ritmo.",
    "desc_f": "Sensível e autêntica, você se expressa mais por ações e estética do que por grandes discursos. Vive o presente com intensidade e valoriza a liberdade para seguir o próprio ritmo.",
    "strengths": [
      "Sensibilidade estética e criativa",
      "Autenticidade nas escolhas pessoais",
      "Adaptabilidade a novos contextos"
    ],
    "growth": [
      "Expressar opiniões mesmo quando geram atrito",
      "Planejar prazos além do curto prazo",
      "Lidar com estruturas rígidas sem desconforto excessivo"
    ],
    "img": "um gato antropomórfico com tinta nas patas, pintando um mural colorido ao ar livre sob luz suave"
  },
  "ESTP": {
    "name_m": "O Realizador Dinâmico",
    "name_f": "A Realizadora Dinâmica",
    "desc_m": "Você age rápido, resolve problemas em tempo real e se sente à vontade sob pressão. Prefere a experiência direta à teoria, e costuma inspirar confiança pela capacidade de resolver o que está na sua frente.",
    "desc_f": "Você age rápido, resolve problemas em tempo real e se sente à vontade sob pressão. Prefere a experiência direta à teoria, e costuma inspirar confiança pela capacidade de resolver o que está na sua frente.",
    "strengths": [
      "Agilidade para agir e resolver problemas",
      "Facilidade de adaptação a situações imprevistas",
      "Pragmatismo e senso de oportunidade"
    ],
    "growth": [
      "Considerar consequências de longo prazo antes de agir",
      "Ter mais paciência com processos lentos",
      "Refletir antes de reagir em momentos de tensão"
    ],
    "img": "um guepardo antropomórfico em pleno movimento, com uma prancha de skate e linhas de movimento ao redor"
  },
  "ESFP": {
    "name_m": "O Animador Espontâneo",
    "name_f": "A Animadora Espontânea",
    "desc_m": "Caloroso e espontâneo, você traz leveza e entusiasmo para onde está. Vive o momento presente com intensidade e tem facilidade para deixar as pessoas ao redor mais à vontade.",
    "desc_f": "Calorosa e espontânea, você traz leveza e entusiasmo para onde está. Vive o momento presente com intensidade e tem facilidade para deixar as pessoas ao redor mais à vontade.",
    "strengths": [
      "Entusiasmo contagiante",
      "Facilidade para se conectar com pessoas",
      "Flexibilidade diante de mudanças de última hora"
    ],
    "growth": [
      "Planejar com mais antecedência quando necessário",
      "Lidar com críticas sem levar para o lado pessoal",
      "Sustentar foco em tarefas menos estimulantes"
    ],
    "img": "um papagaio antropomórfico vibrante, cantando em um palco improvisado com luzes coloridas e confete no ar"
  }
};

/**
 * doGet só serve a página de confirmação de opt-out (ou "não encontrado").
 * Nunca lê nem grava estado de opt-out — resolve o token apenas para exibir
 * a confirmação. A supressão em si só acontece em handleOptOutConfirm, via
 * POST explícito do usuário (ver README > "Opt-out").
 */
function doGet(e) {
  try {
    const params = (e && e.parameter) || {};
    if (params.action === "optout") {
      return handleOptOutShow((params.token || "").toString());
    }
    return htmlResponse(notFoundPage());
  } catch (err) {
    Logger.log("doGet error: " + err);
    return htmlResponse(optoutInvalidPage());
  }
}

/** Tamanho real em bytes UTF-8 — `.length` de uma string JS conta unidades
 * UTF-16, não bytes, e subestima o tamanho real de payloads com acentuação
 * (comum em português) ou outros caracteres multibyte. */
function utf8ByteLength(str) {
  return Utilities.newBlob(str || "").getBytes().length;
}

/**
 * Decodifica manualmente application/x-www-form-urlencoded. Usado só para
 * ler o corpo bruto de POST (ver extractPostBodyFields) — nunca para
 * confiar em query string.
 */
function parseFormUrlEncoded(raw) {
  const result = {};
  (raw || "").split("&").forEach(function (pair) {
    if (!pair) return;
    const idx = pair.indexOf("=");
    const rawKey = idx === -1 ? pair : pair.slice(0, idx);
    const rawValue = idx === -1 ? "" : pair.slice(idx + 1);
    try {
      const key = decodeURIComponent(rawKey.replace(/\+/g, " "));
      const value = decodeURIComponent(rawValue.replace(/\+/g, " "));
      result[key] = value;
    } catch (err) {
      // par malformado (escape inválido): ignora em vez de derrubar o parse inteiro
    }
  });
  return result;
}

/**
 * Extrai os campos do corpo bruto da requisição — nunca de `e.parameter`.
 * `e.parameter` no Apps Script mistura query string e corpo de POST, então
 * um POST com corpo vazio ainda herdaria `action`/`token` da URL. Ações que
 * mudam estado (como confirmar opt-out) exigem um corpo real e explícito.
 */
function extractPostBodyFields(e) {
  if (!e || !e.postData || !e.postData.contents) return {};
  const contentType = (e.postData.type || "").toLowerCase();
  if (contentType.indexOf("application/x-www-form-urlencoded") !== -1) {
    return parseFormUrlEncoded(e.postData.contents);
  }
  if (contentType.indexOf("application/json") !== -1 || contentType.indexOf("text/plain") !== -1) {
    try {
      const parsed = JSON.parse(e.postData.contents);
      return (parsed && typeof parsed === "object" && !Array.isArray(parsed)) ? parsed : {};
    } catch (err) {
      return {};
    }
  }
  return {};
}

function doPost(e) {
  try {
    const bodyFields = extractPostBodyFields(e);
    if (bodyFields.action === "optout_confirm") {
      return handleOptOutConfirm((bodyFields.token || "").toString());
    }
    if (!e || !e.postData || !e.postData.contents) {
      return errorResponse();
    }
    if (utf8ByteLength(e.postData.contents) > MAX_PAYLOAD_BYTES) {
      return errorResponse();
    }

    let data;
    try {
      data = JSON.parse(e.postData.contents);
    } catch (parseErr) {
      return errorResponse();
    }
    if (!data || typeof data !== "object") {
      return errorResponse();
    }

    const isV1 = data.contract === "supleno.integracao.v1";
    const v1SubmissionId = isV1 ? (data.submission_id || "").toString().trim() : "";
    if (isV1) {
      data = normalizeV1Input(data);
      if (!data) return v1ErrorResponse(v1SubmissionId, "invalid_request");
    }

    // Consentimento é uma regra do servidor, não uma promessa do frontend.
    if (data.consentimento !== true) {
      return isV1 ? v1ErrorResponse(v1SubmissionId, "consent_required") : errorResponse();
    }

    // Honeypot: campo invisível no formulário que humanos nunca preenchem.
    // Bots que preenchem todos os campos automaticamente costumam cair aqui.
    // Respondemos "ok" para não sinalizar ao bot que foi filtrado.
    const honeypot = (data.website || "").toString().trim();
    if (honeypot) {
      return jsonResponse({ ok: true });
    }

    // Token de configuração não secreto — ver comentário em ACCESS_TOKEN.
    if (!ACCESS_TOKEN) {
      if (!isV1) {
        Logger.log("ACCESS_TOKEN ausente: rejeitando configuração insegura");
        return errorResponse();
      }
    }
    {
      const token = (data.token || "").toString();
      if (!isV1 && token !== ACCESS_TOKEN) {
        return errorResponse();
      }
    }

    const validated = validateInput(data);
    if (!validated) {
      return isV1 ? v1ErrorResponse(v1SubmissionId, "invalid_request") : errorResponse();
    }

    const submissionId = (data.submission_id || "").toString().trim();
    if (!submissionId || submissionId.length > 128) {
      return errorResponse();
    }
    if (isV1) { validated.v1 = true; validated.v1SubmissionId = submissionId; }
    const fingerprint = computeSubmissionFingerprint(validated);
    return processSubmissionAtomically(validated, submissionId, fingerprint);
  } catch (err) {
    // Nunca expor a exceção crua ao cliente — só no log do servidor.
    Logger.log("doPost error: " + err);
    return errorResponse();
  }
}

function normalizeV1Input(data) {
  if (data.contract !== "supleno.integracao.v1" || !data.submission_id || !data.person || !data.result || !data.scores || !data.consent || !data.attribution || data.opt_out !== false) return null;
  if (["tipos", "estilos", "tracos"].indexOf(data.product) === -1) return null;
  if (data.consent.granted !== true || typeof data.consent.captured_at !== "string" || data.consent.purpose !== "resultado_e_sequencia_supleno" || typeof data.consent.version !== "string") return null;
  const result = data.product === "estilos" ? (data.result.code || "") : data.result;
  return { name: data.person.name, email: data.person.email, whatsapp: data.person.whatsapp || "",
    teste: data.product, resultado: result, pontuacoes: data.scores, consentimento: true,
    submission_id: data.submission_id, website: "", token: "" };
}

function v1ErrorResponse(submissionId, code) {
  return jsonResponse({ contract: "supleno.integracao.v1", status: "error", submission_id: submissionId || "invalid",
    error: { code: code, message: "Não foi possível processar sua solicitação." } });
}

function v1RejectedResponse(submissionId, code) {
  return jsonResponse({ contract: "supleno.integracao.v1", status: "rejected", submission_id: submissionId,
    error: { code: code, message: "A solicitação foi rejeitada." } });
}

/**
 * Validação server-side estrita. Retorna um objeto normalizado ou null.
 * A sigla NUNCA é aceita do cliente — é sempre recalculada a partir de
 * code + gender, para impedir dados inconsistentes ou injetados na planilha.
 */
function validateInput(data) {
  const teste = (data.teste || "").toString().trim().toLowerCase();
  const name = (data.name || "").toString().trim();
  const email = (data.email || "").toString().trim();
  const whatsapp = (data.whatsapp || "").toString().trim();
  let code = (data.code || "").toString().trim().toUpperCase();
  let gender = (data.gender || "").toString().trim().toUpperCase();

  if (!NAME_PATTERN.test(name)) return null;
  if (!EMAIL_PATTERN.test(email)) return null;
  if (whatsapp && !WHATSAPP_PATTERN.test(whatsapp)) return null;
  if (["tipos", "estilos", "tracos"].indexOf(teste) === -1) return null;
  if (!validateScores(teste, data.pontuacoes)) return null;

  if (teste === "tipos") {
    if (!PROFILES[code]) return null;
    if (VALID_GENDERS.indexOf(gender) === -1) return null;
    const calculatedCode = (data.pontuacoes.E >= data.pontuacoes.I ? "E" : "I") +
      (data.pontuacoes.S >= data.pontuacoes.N ? "S" : "N") +
      (data.pontuacoes.T >= data.pontuacoes.F ? "T" : "F") +
      (data.pontuacoes.J >= data.pontuacoes.P ? "J" : "P");
    if (code !== calculatedCode) return null;
    if (!data.resultado || data.resultado.code !== code || data.resultado.gender !== gender) return null;
  } else if (teste === "estilos") {
    code = (data.resultado || "").toString().trim().toUpperCase();
    gender = "";
    if (["D", "I", "S", "C"].indexOf(code) === -1) return null;
    const expectedStyle = ["D", "I", "S", "C"].reduce((best, key) =>
      data.pontuacoes[key] > data.pontuacoes[best] ? key : best, "D");
    if (code !== expectedStyle) return null;
  } else {
    code = "TRACOS";
    gender = "";
    if (!data.resultado || typeof data.resultado !== "object") return null;
    const sameScores = ["SO", "AN", "OM", "TE", "CO"].every(key =>
      data.resultado[key] && data.resultado[key].sum === data.pontuacoes[key].sum &&
      data.resultado[key].percent === data.pontuacoes[key].percent &&
      data.resultado[key].faixa === data.pontuacoes[key].faixa);
    if (!sameScores) return null;
  }

  let sigla;
  if (teste === "tipos") {
    sigla = code + "-" + gender;
  } else {
    sigla = teste.toUpperCase() + "-" + code;
  }
  return { name, email, whatsapp, code, gender, sigla, teste, resultado: data.resultado, pontuacoes: data.pontuacoes };
}

function validateScores(teste, scores) {
  if (!scores || typeof scores !== "object" || Array.isArray(scores)) return false;
  const expected = teste === "tipos" ? ["E", "I", "S", "N", "T", "F", "J", "P"]
    : teste === "estilos" ? ["D", "I", "S", "C"] : ["SO", "AN", "OM", "TE", "CO"];
  if (Object.keys(scores).sort().join(",") !== expected.slice().sort().join(",")) return false;
  const valuesAreValid = expected.every(key => {
    const value = scores[key];
    if (teste !== "tracos") {
      const limit = teste === "tipos" ? 7 : 24;
      return Number.isInteger(value) && value >= 0 && value <= limit;
    }
    const expectedPercent = value && Number.isInteger(value.sum)
      ? Math.round(((value.sum - 5) / 20) * 100) : -1;
    const expectedRange = expectedPercent < 34 ? "baixo" : expectedPercent < 67 ? "medio" : "alto";
    return value && typeof value === "object" &&
      Number.isInteger(value.sum) && value.sum >= 5 && value.sum <= 25 &&
      value.percent === expectedPercent && value.faixa === expectedRange;
  });
  if (!valuesAreValid) return false;
  if (teste === "tipos") {
    return scores.E + scores.I === 7 && scores.S + scores.N === 7 &&
      scores.T + scores.F === 7 && scores.J + scores.P === 7;
  }
  if (teste === "estilos") return expected.reduce((sum, key) => sum + scores[key], 0) === 24;
  return true;
}

/** Serializa um valor em JSON com chaves de objeto ordenadas recursivamente,
 * para que o mesmo payload sempre produza a mesma string, independente da
 * ordem em que os campos chegaram. Arrays preservam a ordem (são posicionais). */
function canonicalJsonValue(value) {
  if (Array.isArray(value)) {
    return "[" + value.map(canonicalJsonValue).join(",") + "]";
  }
  if (value && typeof value === "object") {
    const keys = Object.keys(value).sort();
    return "{" + keys.map(k => JSON.stringify(k) + ":" + canonicalJsonValue(value[k])).join(",") + "}";
  }
  return JSON.stringify(value);
}

/** Fingerprint SHA-256 determinístico do payload já validado: identifica se
 * duas submissões com o mesmo submission_id carregam o mesmo conteúdo, ou se
 * o id está sendo reaproveitado para outro payload (o que nunca deve ser
 * tratado como duplicata silenciosa). */
function computeSubmissionFingerprint(validated) {
  const canonical = canonicalJsonValue(validated);
  return Utilities.base64EncodeWebSafe(
    Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, canonical)
  );
}

/* ============================================================
   OPT-OUT — criptografia do token e handlers de GET/POST
   ============================================================ */

/** Converte um array de bytes (com sinal, como retornado por Utilities) em hex. */
function bytesToHex(bytes) {
  return bytes.map(b => ((b < 0 ? b + 256 : b).toString(16).padStart(2, "0"))).join("");
}

/** Comparação em tempo constante para evitar timing attack na validação do token. */
function timingSafeEqualHex(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}

// Validade do vínculo nonce → e-mail guardado em PropertiesService. Um valor
// generoso porque o link vive dentro de e-mails já enviados (não é renovável
// pelo destinatário) — ver README > "Opt-out".
const OPTOUT_TOKEN_TTL_MS = 180 * 24 * 60 * 60 * 1000;

function optoutTokenPropertyKey(nonce) {
  return "optout_token_" + nonce;
}

/**
 * Deriva um identificador opaco e determinístico do e-mail: hex(HMAC-SHA256(
 * e-mail, OPTOUT_SECRET)) truncado a 128 bits. Por ser HMAC (função de mão
 * única), não existe forma de recuperar o e-mail a partir do nonce — nem
 * mesmo quem conhece OPTOUT_SECRET consegue invertê-lo, só recalculá-lo a
 * partir de um e-mail já conhecido. Ser determinístico (mesmo e-mail sempre
 * gera o mesmo nonce) evita acumular uma entrada nova em PropertiesService a
 * cada envio: reenvios para o mesmo e-mail reaproveitam a mesma chave.
 */
function optoutNonceForEmail(normalizedEmail) {
  const mac = Utilities.computeHmacSha256Signature(normalizedEmail, OPTOUT_SECRET);
  return bytesToHex(mac).slice(0, 32);
}

/**
 * Gera o token opaco de opt-out: um nonce (derivado por HMAC do e-mail, ver
 * optoutNonceForEmail) sem NENHUM dado do e-mail codificado dentro dele — só
 * um identificador de 128 bits. A ligação nonce → e-mail fica guardada em
 * PropertiesService (por chave direta, nunca varrida) e é o único lugar de
 * onde o e-mail pode ser recuperado. A URL do e-mail carrega só o nonce.
 */
function gerarOptoutToken(email) {
  if (!OPTOUT_SECRET) {
    throw new Error("OPTOUT_SECRET não configurado: opt-out indisponível");
  }
  const normalizado = (email || "").toString().trim().toLowerCase();
  const nonce = optoutNonceForEmail(normalizado);
  const props = PropertiesService.getScriptProperties();
  props.setProperty(optoutTokenPropertyKey(nonce), JSON.stringify({
    email: normalizado,
    expires_at: new Date(Date.now() + OPTOUT_TOKEN_TTL_MS).toISOString(),
  }));
  return nonce;
}

/**
 * Resolve o e-mail a partir do nonce opaco. Funciona mesmo que nunca tenha
 * existido um lead local (linha na planilha) para esse e-mail — só depende
 * do vínculo nonce → e-mail criado em gerarOptoutToken, nunca de
 * SpreadsheetApp. Confere expiração e recomputa o nonce esperado a partir do
 * e-mail guardado (optoutNonceForEmail) como verificação de integridade:
 * se o registro em PropertiesService foi corrompido ou adulterado por
 * qualquer via, o nonce recalculado diverge do nonce da URL e a resolução
 * falha. Retorna null em qualquer caso de dúvida (fail-closed).
 */
function resolverEmailPorToken(token) {
  if (!OPTOUT_SECRET || !token) return null;
  const nonce = token.toString().trim().toLowerCase();
  if (!/^[0-9a-f]{32}$/.test(nonce)) return null;
  const props = PropertiesService.getScriptProperties();
  const raw = props.getProperty(optoutTokenPropertyKey(nonce));
  if (!raw) return null;
  try {
    const record = JSON.parse(raw);
    if (!record || typeof record.email !== "string" || typeof record.expires_at !== "string") return null;
    if (new Date(record.expires_at).getTime() < Date.now()) return null;
    const expectedNonce = optoutNonceForEmail(record.email);
    if (!timingSafeEqualHex(nonce, expectedNonce)) return null;
    return record.email;
  } catch (err) {
    return null;
  }
}

function optoutPropertyKey(email) {
  const normalizado = (email || "").toString().trim().toLowerCase();
  return "optout_" + Utilities.base64EncodeWebSafe(
    Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, normalizado)
  );
}

/** Consultado antes de aceitar recadastro e antes de qualquer envio da outbox. */
function estaOptOut(email) {
  const props = PropertiesService.getScriptProperties();
  return props.getProperty(optoutPropertyKey(email)) === "1";
}

/**
 * Persiste a supressão do e-mail e cancela envios ainda pendentes na outbox.
 * Chamado somente por handleOptOutConfirm (POST explícito) — nunca por GET.
 */
function registrarOptOut(email) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) throw new Error("não foi possível obter lock para opt-out");
  try {
    const props = PropertiesService.getScriptProperties();
    props.setProperty(optoutPropertyKey(email), "1");
    cancelarOutboxPendentePorEmail(email);
  } finally {
    lock.releaseLock();
  }
}

function handleOptOutShow(token) {
  const email = resolverEmailPorToken(token);
  if (!email) return htmlResponse(optoutInvalidPage());
  return htmlResponse(optoutConfirmPage(token));
}

function handleOptOutConfirm(token) {
  const email = resolverEmailPorToken(token);
  if (!email) return htmlResponse(optoutInvalidPage());
  registrarOptOut(email);
  return htmlResponse(optoutDonePage());
}

function htmlResponse(html) {
  return HtmlService.createHtmlOutput(html).setTitle("Supleno — Cancelamento de e-mails");
}

function notFoundPage() {
  return "<!doctype html><html lang=\"pt-BR\"><meta charset=\"utf-8\"><title>Supleno</title><h1>Rota não encontrada.</h1></html>";
}

function optoutInvalidPage() {
  return "<!doctype html><html lang=\"pt-BR\"><meta charset=\"utf-8\"><title>Supleno</title><h1>Link de cancelamento inválido.</h1></html>";
}

function optoutDonePage() {
  return "<!doctype html><html lang=\"pt-BR\"><meta charset=\"utf-8\"><title>Supleno</title><h1>Recebimento de e-mails cancelado.</h1></html>";
}

/** Página de confirmação: a supressão só ocorre no POST deste formulário. */
function optoutConfirmPage(token) {
  const safeToken = escapeHtml(token);
  const actionUrl = escapeHtml(ScriptApp.getService().getUrl());
  return "<!doctype html><html lang=\"pt-BR\"><meta charset=\"utf-8\"><title>Supleno</title>" +
    "<h1>Confirmar cancelamento</h1>" +
    "<p>Deseja realmente parar de receber nossos e-mails?</p>" +
    "<form method=\"POST\" action=\"" + actionUrl + "\">" +
    "<input type=\"hidden\" name=\"action\" value=\"optout_confirm\">" +
    "<input type=\"hidden\" name=\"token\" value=\"" + safeToken + "\">" +
    "<button type=\"submit\">Sim, confirmar cancelamento</button>" +
    "</form></html>";
}

/* ============================================================
   OUTBOX — fila persistente de e-mails, numa aba dedicada da Spreadsheet
   ============================================================ */

// Única fonte de verdade para as colunas da aba "Outbox": usada tanto para
// escrever o cabeçalho quanto para ler/gravar cada linha, para as duas nunca
// divergirem. Uma linha por item da fila — nunca payload em Script Properties.
const OUTBOX_HEADERS = [
  "submission_id", "fingerprint", "state", "lease_until", "attempts",
  "email", "name", "code", "gender", "teste", "resultado", "pontuacoes",
  "enqueued_at", "sent_at", "reconciled_at"
];

// Campos de texto que podem conter dado do usuário (ou reaproveitar
// caracteres de controle) passam por sanitizeForSheet antes de virar célula,
// igual a appendLeadIdempotente — proteção contra injeção de fórmula.
const OUTBOX_SANITIZED_FIELDS = [
  "submission_id", "fingerprint", "email", "name", "code", "gender", "teste", "resultado", "pontuacoes"
];

function outboxColumnIndex(headerName) {
  const idx = OUTBOX_HEADERS.indexOf(headerName);
  if (idx === -1) throw new Error("coluna de outbox desconhecida: " + headerName);
  return idx + 1; // Sheets é 1-indexado
}

/** Cria a aba "Outbox" se não existir e valida o cabeçalho se já existir —
 * nunca assume silenciosamente que colunas fora de ordem são as esperadas. */
function getOutboxSheet() {
  const ss = SHEET_ID ? SpreadsheetApp.openById(SHEET_ID) : SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(OUTBOX_SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(OUTBOX_SHEET_NAME);
  }
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(OUTBOX_HEADERS);
    SpreadsheetApp.flush();
  } else {
    if (sheet.getLastColumn() !== OUTBOX_HEADERS.length) {
      throw new Error('aba "' + OUTBOX_SHEET_NAME + '" com quantidade de colunas inesperada; verifique manualmente antes de continuar');
    }
    const existingHeaders = sheet.getRange(1, 1, 1, OUTBOX_HEADERS.length).getValues()[0];
    if (existingHeaders.join("") !== OUTBOX_HEADERS.join("")) {
      throw new Error('aba "' + OUTBOX_SHEET_NAME + '" com cabeçalho inesperado; verifique manualmente antes de continuar');
    }
  }
  return sheet;
}

function outboxEntryToRowValues(entry) {
  return OUTBOX_HEADERS.map(function (header) {
    let value = entry[header];
    if (header === "resultado" || header === "pontuacoes") {
      value = (value === undefined || value === null || value === "") ? "" : JSON.stringify(value);
    } else if (header === "attempts") {
      return Number(value || 0);
    } else {
      value = (value === undefined || value === null) ? "" : String(value);
    }
    if (value !== "" && OUTBOX_SANITIZED_FIELDS.indexOf(header) !== -1) {
      value = sanitizeForSheet(value);
    }
    return value;
  });
}

function outboxRowValuesToEntry(rowValues, rowNumber) {
  const entry = { _row: rowNumber };
  OUTBOX_HEADERS.forEach(function (header, i) {
    const raw = rowValues[i];
    if (header === "resultado" || header === "pontuacoes") {
      entry[header] = raw ? JSON.parse(raw) : null;
    } else if (header === "attempts") {
      entry[header] = Number(raw || 0);
    } else if (header === "lease_until" || header === "sent_at" || header === "reconciled_at") {
      entry[header] = raw ? String(raw) : null;
    } else {
      entry[header] = raw === undefined || raw === null ? "" : String(raw);
    }
  });
  return entry;
}

/** Leitura limitada: uma única linha (nunca a aba inteira). */
function readOutboxRow(sheet, rowNumber) {
  const values = sheet.getRange(rowNumber, 1, 1, OUTBOX_HEADERS.length).getValues()[0];
  return outboxRowValuesToEntry(values, rowNumber);
}

function writeOutboxRow(sheet, entry) {
  sheet.getRange(entry._row, 1, 1, OUTBOX_HEADERS.length).setValues([outboxEntryToRowValues(entry)]);
}

/** Localiza a linha de um submission_id via TextFinder restrito à coluna
 * (nunca varredura de Script Properties nem leitura da aba inteira). */
function findOutboxRowBySubmissionId(sheet, submissionId) {
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return null;
  const col = outboxColumnIndex("submission_id");
  const range = sheet.getRange(2, col, lastRow - 1, 1);
  const found = range.createTextFinder(submissionId).matchEntireCell(true).findNext();
  if (!found) return null;
  return readOutboxRow(sheet, found.getRow());
}

/**
 * Persiste a intenção de envio antes de qualquer efeito externo. Chamada de
 * dentro do ScriptLock já mantido por processSubmissionAtomically. Idempotente
 * por submissionId: uma segunda chamada para o mesmo id não duplica a linha;
 * se o mesmo id aparecer com um fingerprint diferente (reuso indevido do id,
 * já devia ter sido barrado mais acima), rejeita em vez de mascarar o conflito.
 */
function enqueueOutbox(submissionId, validated, fingerprint) {
  const sheet = getOutboxSheet();
  const existing = findOutboxRowBySubmissionId(sheet, submissionId);
  if (existing) {
    if (existing.fingerprint !== fingerprint) {
      throw new Error("outbox: submission_id " + submissionId + " já existe com fingerprint diferente");
    }
    return;
  }
  const now = new Date().toISOString();
  sheet.appendRow(outboxEntryToRowValues({
    submission_id: submissionId,
    fingerprint: fingerprint,
    state: "pending",
    lease_until: "",
    attempts: 0,
    email: validated.email,
    name: validated.name,
    code: validated.code,
    gender: validated.gender,
    teste: validated.teste,
    resultado: validated.resultado,
    pontuacoes: validated.pontuacoes,
    enqueued_at: now,
    sent_at: "",
    reconciled_at: "",
  }));
  SpreadsheetApp.flush();
}

/** Chamada sob o lock externo de registrarOptOut — nunca adquire lock próprio.
 * Busca por e-mail restrita à coluna correspondente (TextFinder, case
 * insensitive), nunca getProperties nem varredura global. */
function cancelarOutboxPendentePorEmail(email) {
  const normalizado = (email || "").toString().trim().toLowerCase();
  if (!normalizado) return;
  const sheet = getOutboxSheet();
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return;
  const col = outboxColumnIndex("email");
  const range = sheet.getRange(2, col, lastRow - 1, 1);
  const matches = range.createTextFinder(normalizado).matchEntireCell(true).matchCase(false).findAll()
    .slice(0, OUTBOX_CANCEL_LIMIT);
  const now = new Date().toISOString();
  matches.forEach(function (match) {
    const entry = readOutboxRow(sheet, match.getRow());
    if (entry.state === "pending") {
      entry.state = "cancelled";
      entry.reconciled_at = now;
      writeOutboxRow(sheet, entry);
    }
  });
  if (matches.length) SpreadsheetApp.flush();
}

/**
 * Processa a outbox: tenta enviar itens "pending" e reconcilia itens
 * "sending" cuja lease expirou. Não deve ser chamado pelo caminho de
 * submissão — apenas por um gatilho de tempo configurado separadamente
 * (ver README > "Fila de envio (outbox)").
 *
 * Visita no máximo OUTBOX_BATCH_SIZE linhas por chamada, a partir de um
 * cursor circular pequeno (um único inteiro em Script Properties — nunca o
 * payload da fila) para que cada execução do gatilho de tempo permaneça
 * curta mesmo com a aba grande, e para que chamadas sucessivas cubram toda a
 * aba ao longo do tempo em vez de sempre revisitar as primeiras linhas.
 *
 * Garantia honesta: MailApp não aceita chave de idempotência, então uma
 * exceção durante o envio não prova ausência de entrega. Por isso, tanto uma
 * falha de envio quanto uma lease "sending" expirada viram "uncertain" — não
 * "pending" — para nunca reenviar às cegas. Sair de "uncertain" exige uma
 * decisão humana explícita via outboxMarcarComoEnviadoManualmente ou
 * outboxMarcarComoPendenteManualmente.
 */
function processarOutbox() {
  if (!OPTOUT_SECRET) {
    Logger.log("processarOutbox: OPTOUT_SECRET não configurado; envio bloqueado até a configuração ser concluída.");
    return { processados: 0, bloqueado: true };
  }
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) return { processados: 0 };
  try {
    const sheet = getOutboxSheet();
    const lastRow = sheet.getLastRow();
    if (lastRow < 2) return { processados: 0 };
    const totalDataRows = lastRow - 1;
    const batchSize = Math.min(OUTBOX_BATCH_SIZE, totalDataRows);

    const props = PropertiesService.getScriptProperties();
    let cursor = parseInt(props.getProperty(OUTBOX_CURSOR_ROW_PROPERTY) || "0", 10);
    if (!Number.isFinite(cursor) || cursor < 0) cursor = 0;
    let offset = cursor % totalDataRows;

    const now = new Date();
    let processados = 0;
    for (let i = 0; i < batchSize; i++) {
      const rowNumber = offset + 2; // linha 1 é cabeçalho
      const entry = readOutboxRow(sheet, rowNumber);

      if (entry.state === "sending") {
        const leaseUntil = entry.lease_until ? new Date(entry.lease_until) : null;
        if (!leaseUntil || leaseUntil < now) {
          entry.state = "uncertain";
          writeOutboxRow(sheet, entry);
        }
      } else if (entry.state === "pending") {
        if (estaOptOut(entry.email)) {
          entry.state = "cancelled";
          entry.reconciled_at = now.toISOString();
          writeOutboxRow(sheet, entry);
        } else {
          entry.state = "sending";
          entry.attempts = (entry.attempts || 0) + 1;
          entry.lease_until = new Date(now.getTime() + OUTBOX_LEASE_MS).toISOString();
          writeOutboxRow(sheet, entry);
          SpreadsheetApp.flush();

          try {
            sendResultEmail(entry.name, entry.email, entry.code, entry.gender,
              entry.teste, entry.resultado, entry.pontuacoes);
            entry.state = "sent";
            entry.sent_at = new Date().toISOString();
            writeOutboxRow(sheet, entry);
            processados++;
          } catch (err) {
            Logger.log("processarOutbox: falha ao enviar " + entry.submission_id + ": " + err);
            entry.state = "uncertain";
            writeOutboxRow(sheet, entry);
          }
        }
      }
      offset = (offset + 1) % totalDataRows;
    }
    props.setProperty(OUTBOX_CURSOR_ROW_PROPERTY, String(offset));
    return { processados: processados };
  } finally {
    lock.releaseLock();
  }
}

/** Reconciliação manual: confirma envio de um item "uncertain" sem reenviar.
 * Adquire o próprio ScriptLock (é um ponto de entrada independente, chamado
 * manualmente pelo operador — não herda o lock de nenhum outro caminho). */
function outboxMarcarComoEnviadoManualmente(submissionId) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) throw new Error("não foi possível obter lock para reconciliação manual");
  try {
    const sheet = getOutboxSheet();
    const entry = findOutboxRowBySubmissionId(sheet, submissionId);
    if (!entry) throw new Error("outbox não encontrada para " + submissionId);
    if (entry.state !== "uncertain") {
      throw new Error("só é possível confirmar manualmente a partir do estado 'uncertain'");
    }
    entry.state = "sent";
    entry.sent_at = new Date().toISOString();
    entry.reconciled_at = new Date().toISOString();
    writeOutboxRow(sheet, entry);
    SpreadsheetApp.flush();
  } finally {
    lock.releaseLock();
  }
}

/** Reconciliação manual: reabre um item "uncertain" para nova tentativa, só
 * depois de confirmação humana de que o envio anterior não ocorreu. Também
 * adquire o próprio ScriptLock, pelo mesmo motivo do marcar-como-enviado. */
function outboxMarcarComoPendenteManualmente(submissionId) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) throw new Error("não foi possível obter lock para reconciliação manual");
  try {
    const sheet = getOutboxSheet();
    const entry = findOutboxRowBySubmissionId(sheet, submissionId);
    if (!entry) throw new Error("outbox não encontrada para " + submissionId);
    if (entry.state !== "uncertain") {
      throw new Error("só é possível reabrir manualmente a partir do estado 'uncertain'");
    }
    entry.state = "pending";
    entry.lease_until = "";
    entry.reconciled_at = new Date().toISOString();
    writeOutboxRow(sheet, entry);
    SpreadsheetApp.flush();
  } finally {
    lock.releaseLock();
  }
}

/* ============================================================
   SUBMISSÃO — idempotência com lease e outbox
   ============================================================ */

/**
 * Mantém consulta, efeitos e marca de idempotência sob um único lock.
 * O status "processing" carrega uma lease (prazo de validade) e flags de
 * progresso (lead_appended/outbox_enqueued): se o processo cair no meio do
 * caminho, uma nova requisição com o mesmo submissionId, após a lease
 * expirar, retoma exatamente de onde parou — nunca duplica appendLead nem
 * a entrada da outbox, e nunca deixa o lead se perder silenciosamente.
 * Nenhum e-mail é enviado aqui: apenas a intenção é enfileirada (outbox);
 * o envio de fato acontece em processarOutbox, fora do caminho da submissão.
 */
function processSubmissionAtomically(validated, submissionId, fingerprint) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) return validated.v1 ? v1ErrorResponse(submissionId, "temporary_failure") : errorResponse();
  try {
    const props = PropertiesService.getScriptProperties();
    const idempotencyKey = "submission_" + Utilities.base64EncodeWebSafe(
      Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, submissionId)
    );
    const now = new Date();
    const existingRaw = props.getProperty(idempotencyKey);

    if (existingRaw) {
      const existing = JSON.parse(existingRaw);
      // O mesmo submission_id reaproveitado para um payload diferente nunca
      // é uma duplicata legítima — é reuso indevido do id. Nunca retorna
      // duplicate=true nesse caso, mesmo que o estado já esteja "done".
      if (existing.fingerprint && existing.fingerprint !== fingerprint) {
        return validated.v1 ? v1RejectedResponse(submissionId, "duplicate_payload_conflict") : errorResponse();
      }
      if (existing.status === "done") {
        return validated.v1 ? v1Response(submissionId, "duplicate", "pending") : jsonResponse({ ok: true, duplicate: true });
      }
      const leaseUntil = existing.lease_until ? new Date(existing.lease_until) : null;
      if (leaseUntil && leaseUntil >= now) {
        // Lease ainda válida: outra requisição concorrente/retentativa está
        // em andamento. Não reprocessa para não duplicar; o cliente deve
        // tentar novamente mais tarde.
        return validated.v1 ? v1Response(submissionId, "duplicate", "pending") : jsonResponse({ ok: true, duplicate: true, processing: true });
      }
      if (estaOptOut(validated.email)) {
        existing.status = "done";
        existing.finished_at = now.toISOString();
        existing.aborted_opt_out = true;
        props.setProperty(idempotencyKey, JSON.stringify(existing));
        return validated.v1 ? v1Response(submissionId, "suppressed", "opt_out") : errorResponse();
      }
      // Lease expirada: retoma sem repetir efeitos já concluídos.
      existing.fingerprint = existing.fingerprint || fingerprint;
      existing.lease_until = new Date(now.getTime() + PROCESSING_LEASE_MS).toISOString();
      props.setProperty(idempotencyKey, JSON.stringify(existing));
      return concluirProcessamento(validated, submissionId, fingerprint, existing, props, idempotencyKey);
    }

    if (estaOptOut(validated.email)) return validated.v1 ? v1Response(submissionId, "suppressed", "opt_out") : errorResponse();
    if (!checkRateLimitLocked(validated.email, props)) return validated.v1 ? v1ErrorResponse(submissionId, "temporary_failure") : errorResponse();

    const state = {
      status: "processing",
      started_at: now.toISOString(),
      lease_until: new Date(now.getTime() + PROCESSING_LEASE_MS).toISOString(),
      lead_appended: false,
      outbox_enqueued: false,
      fingerprint: fingerprint,
    };
    props.setProperty(idempotencyKey, JSON.stringify(state));
    return concluirProcessamento(validated, submissionId, fingerprint, state, props, idempotencyKey);
  } finally {
    lock.releaseLock();
  }
}

function concluirProcessamento(validated, submissionId, fingerprint, state, props, idempotencyKey) {
  // Pré-voo obrigatório: valida/cria ambas as abas antes de qualquer efeito
  // parcial. Uma Outbox incompatível jamais pode deixar um lead já gravado.
  getOutboxSheet();
  getSheet();
  if (!state.lead_appended) {
    appendLeadIdempotente(validated.name, validated.email, validated.whatsapp, validated.sigla,
      validated.teste, validated.resultado, validated.pontuacoes, submissionId, fingerprint);
    state.lead_appended = true;
    props.setProperty(idempotencyKey, JSON.stringify(state));
  }
  if (!state.outbox_enqueued) {
    enqueueOutbox(submissionId, validated, fingerprint);
    state.outbox_enqueued = true;
    props.setProperty(idempotencyKey, JSON.stringify(state));
  }
  state.status = "done";
  state.finished_at = new Date().toISOString();
  props.setProperty(idempotencyKey, JSON.stringify(state));
  return validated.v1 ? v1Response(submissionId, "accepted", "pending") : jsonResponse({ ok: true });
}

function v1Response(submissionId, status, sequenceState) {
  return jsonResponse({ contract: "supleno.integracao.v1", status: status, submission_id: submissionId,
    sequence_state: sequenceState });
}

/**
 * Rate limit com PropertiesService + LockService.
 * Dois limites independentes (ver constantes no topo do arquivo):
 *  - por e-mail, numa janela de 24h (evita reenvio abusivo da mesma pessoa)
 *  - global, numa janela de 60s (evita rajadas de um script/bot)
 * O lock evita condição de corrida entre requisições simultâneas.
 */
function checkRateLimit(email) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(3000)) {
    // Não conseguimos garantir consistência agora — mais seguro recusar
    // do que arriscar dupla contagem ou perda de limite.
    return false;
  }
  try {
    const props = PropertiesService.getScriptProperties();
    return checkRateLimitLocked(email, props);
  } finally {
    lock.releaseLock();
  }
}

function checkRateLimitLocked(email, props) {
  const now = Date.now();
  const globalKey = "rl_global_" + Math.floor(now / 60000);
  const globalCount = Number(props.getProperty(globalKey) || "0") + 1;
  if (globalCount > RATE_LIMIT_GLOBAL_PER_MINUTE) return false;

  const emailKey = "rl_email_" + email.toLowerCase() + "_" + Math.floor(now / 86400000);
  const emailCount = Number(props.getProperty(emailKey) || "0") + 1;
  if (emailCount > RATE_LIMIT_PER_EMAIL_PER_DAY) return false;

  props.setProperty(globalKey, String(globalCount));
  props.setProperty(emailKey, String(emailCount));
  return true;
}

// Única fonte de verdade para as colunas da planilha "Leads MBTI": usada
// tanto para escrever o cabeçalho quanto para localizar a coluna do
// Submission ID em appendLeadIdempotente, para as duas nunca divergirem.
const LEAD_SHEET_HEADERS = ["Data", "Nome", "E-mail", "Sigla", "WhatsApp", "Produto", "Resultado", "Pontuações", "Submission ID", "Fingerprint"];

function getSheet() {
  const ss = SHEET_ID ? SpreadsheetApp.openById(SHEET_ID) : SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);
  }
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(LEAD_SHEET_HEADERS);
    SpreadsheetApp.flush();
  } else {
    if (sheet.getLastColumn() !== LEAD_SHEET_HEADERS.length) {
      throw new Error('aba "' + SHEET_NAME + '" com quantidade de colunas inesperada; migre o cabeçalho antes de continuar');
    }
    const existingHeaders = sheet.getRange(1, 1, 1, LEAD_SHEET_HEADERS.length).getValues()[0];
    if (existingHeaders.join("\u0001") !== LEAD_SHEET_HEADERS.join("\u0001")) {
      throw new Error('aba "' + SHEET_NAME + '" com cabeçalho inesperado; migre o cabeçalho antes de continuar');
    }
  }
  return sheet;
}

/**
 * Impede injeção de fórmula em planilhas: se o valor começar com um dos
 * caracteres que o Sheets interpreta como início de fórmula (=, +, -, @) ou
 * com tab/quebra de linha, prefixa com apóstrofo para forçar texto puro.
 */
function sanitizeForSheet(value) {
  const str = String(value);
  if (/^[=+\-@\t\r]/.test(str)) {
    return "'" + str;
  }
  return str;
}

/**
 * Grava o lead na planilha de forma idempotente por submissionId. Chamada de
 * dentro do ScriptLock já mantido por processSubmissionAtomically: procura
 * uma linha existente com o mesmo Submission ID antes de gravar, e não
 * grava de novo se ela já existir. Isso cobre a janela entre o appendRow
 * físico e a persistência de lead_appended=true em PropertiesService — se o
 * processo cair exatamente nesse intervalo, a retomada não duplica a linha.
 */
function appendLeadIdempotente(name, email, whatsapp, sigla, teste, resultado, pontuacoes, submissionId, fingerprint) {
  const sheet = getSheet();
  const submissionIdColumn = LEAD_SHEET_HEADERS.indexOf("Submission ID") + 1;
  const lastRow = sheet.getLastRow();
  if (lastRow > 1) {
    const existingRows = sheet.getRange(2, submissionIdColumn, lastRow - 1, 2).getValues();
    for (let i = 0; i < existingRows.length; i++) {
      if (existingRows[i][0] === submissionId) {
        if (existingRows[i][1] !== fingerprint) {
          throw new Error("submission_id já gravado com fingerprint diferente");
        }
        return;
      }
    }
  }
  sheet.appendRow([
    new Date(),
    sanitizeForSheet(name),
    sanitizeForSheet(email),
    sanitizeForSheet(sigla),
    sanitizeForSheet(whatsapp),
    sanitizeForSheet(teste),
    sanitizeForSheet(JSON.stringify(resultado)),
    sanitizeForSheet(JSON.stringify(pontuacoes)),
    sanitizeForSheet(submissionId),
    sanitizeForSheet(fingerprint)
  ]);
}

/** Escapa HTML para evitar injeção de marcação no corpo do e-mail. */
function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** Link opaco de cancelamento (token HMAC), incluído em todo e-mail enviado. */
function optoutLinkHtml(email) {
  const optoutUrl = `${ScriptApp.getService().getUrl()}?action=optout&token=${encodeURIComponent(gerarOptoutToken(email))}`;
  return `<p style="font-size:11px; color:#6B6055; margin-top:16px;"><a href="${optoutUrl}" style="color:#6B6055;">Cancelar recebimento de e-mails</a></p>`;
}

function sendResultEmail(name, email, code, gender, teste, resultado, pontuacoes) {
  if (teste !== "tipos") {
    const productName = teste === "estilos" ? "Supleno Estilos" : "Supleno Traços";
    const safeName = escapeHtml(name);
    const safeResult = escapeHtml(JSON.stringify(resultado));
    const safeScores = escapeHtml(JSON.stringify(pontuacoes));
    MailApp.sendEmail({
      to: email,
      subject: `Seu resultado no ${productName}`,
      htmlBody: `<h1>${productName}</h1><p>Olá, ${safeName}.</p><p>Resultado: ${safeResult}</p><p>Pontuações: ${safeScores}</p>${optoutLinkHtml(email)}`,
      name: "Testes Supleno"
    });
    return;
  }
  const gk = gender === "F" ? "f" : "m";
  const p = PROFILES[code];
  const typeName = p["name_" + gk];
  const desc = p["desc_" + gk];
  const strengths = p.strengths.map(s => `<li>${escapeHtml(s)}</li>`).join("");
  const growth = p.growth.map(s => `<li>${escapeHtml(s)}</li>`).join("");
  const fullPageUrl = `${SITE_BASE_URL}/tipos/resultados/${code.toLowerCase()}-${gk}.html`;
  const safeName = escapeHtml(name);

  const subject = `Seu resultado: ${typeName} (${code}-${gender})`;
  const html = `
    <div style="font-family:Arial,sans-serif; max-width:560px; margin:0 auto; color:#2B2420;">
      <p style="text-transform:uppercase; letter-spacing:.08em; font-size:12px; color:#1F4B4C; font-weight:bold;">Método Supleno</p>
      <h1 style="color:#163736; font-size:24px;">${escapeHtml(typeName)}</h1>
      <p style="font-size:32px; font-weight:800; color:#C15A38; margin:0 0 16px;">${code}-${gender}</p>
      <p style="font-size:15px; line-height:1.6;">Olá, ${safeName}! Aqui está o seu resultado completo do Teste de Perfil de Personalidade.</p>
      <p style="font-size:15px; line-height:1.6;">${escapeHtml(desc)}</p>
      <h3 style="font-size:13px; text-transform:uppercase; letter-spacing:.06em; color:#1F4B4C;">Pontos Fortes</h3>
      <ul style="font-size:14.5px; line-height:1.6;">${strengths}</ul>
      <h3 style="font-size:13px; text-transform:uppercase; letter-spacing:.06em; color:#1F4B4C;">Caminhos de Desenvolvimento</h3>
      <ul style="font-size:14.5px; line-height:1.6;">${growth}</ul>
      <p style="margin-top:24px;"><a href="${fullPageUrl}" style="color:#C15A38;">Ver a página completa do seu perfil &rarr;</a></p>
      <div style="margin-top:28px; padding:20px; background:#163736; border-radius:14px; text-align:center;">
        <p style="color:#F3EDE4; font-size:14px; margin:0 0 14px;">Quer aprofundar seu autoconhecimento com o Método Supleno?</p>
        <a href="${CTA_URL}" style="background:#D9A441; color:#163736; padding:12px 22px; border-radius:999px; text-decoration:none; font-weight:bold; display:inline-block;">Conhecer o Método Supleno</a>
      </div>
      <p style="font-size:11px; color:#6B6055; margin-top:24px;">Conteúdo educativo, não substitui avaliação psicológica profissional.</p>
      ${optoutLinkHtml(email)}
    </div>
  `;

  MailApp.sendEmail({
    to: email,
    subject: subject,
    htmlBody: html,
    name: FROM_NAME
  });
}

function jsonResponse(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

/** Resposta de erro genérica — nunca expõe detalhes internos ao cliente. */
function errorResponse() {
  return jsonResponse({ ok: false, error: "Não foi possível processar sua solicitação." });
}

// Função de teste manual — rode pelo editor do Apps Script (menu Executar) para
// conferir se a planilha, a outbox e o envio de e-mail estão funcionando, sem
// precisar do site. A submissão só enfileira (outbox); processarOutbox() é
// quem de fato chama MailApp — exatamente como acontece via gatilho de tempo
// em produção (ver README > "Fila de envio (outbox)").
function testeManual() {
  const fakeEvent = {
    postData: {
      contents: JSON.stringify({
        name: "Teste",
        email: Session.getActiveUser().getEmail(),
        whatsapp: "",
        code: "INTJ",
        gender: "F",
        teste: "tipos",
        resultado: { code: "INTJ", gender: "F" },
        pontuacoes: { E: 2, I: 5, S: 3, N: 4, T: 4, F: 3, J: 5, P: 2 },
        consentimento: true,
        submission_id: "teste-manual-" + Date.now(),
        website: "", // honeypot — deve ficar sempre vazio
        token: ACCESS_TOKEN // só é exigido se ACCESS_TOKEN estiver configurado
      })
    }
  };
  const res = doPost(fakeEvent);
  Logger.log(res.getContent());
  Logger.log(JSON.stringify(processarOutbox()));
}
