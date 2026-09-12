/**
 * TESTE DE PERFIL SUPLENO — backend em Google Apps Script
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
 *   6. Copie a URL do app da web gerada e cole em WEBHOOK_URL no index.html
 *      (e também em apps-script sempre que reimplantar, a URL pode mudar
 *      se você criar uma NOVA implantação em vez de atualizar a existente)
 */

// Se a planilha "Leads MBTI" NÃO estiver vinculada a este script
// (ou seja, se você criou o script separadamente), cole o ID dela aqui.
// Deixe em branco ("") se o script já está vinculado à planilha
// (Extensões > Apps Script a partir de dentro da própria planilha).
const SHEET_ID = "";
const SHEET_NAME = "Leads MBTI";

// E-mail que aparece como remetente (deve ser o dono da conta que implantou o script)
const FROM_NAME = "Método Supleno";

// Link do botão final do e-mail
const CTA_URL = "https://supleno.com"; // TODO: ajustar

// Base do site publicado (para montar o link da página completa no e-mail)
const SITE_BASE_URL = "https://mrsucesso.github.io/teste-mbti-supleno"; // trocar pelo domínio final após DNS e publicação

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

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    const name = (data.name || "").toString().trim();
    const email = (data.email || "").toString().trim();
    const whatsapp = (data.whatsapp || "").toString().trim();
    const code = (data.code || "").toString().trim().toUpperCase();
    const gender = (data.gender || "M").toString().trim().toUpperCase();
    const sigla = (data.sigla || (code + "-" + gender)).toString().trim();

    if (!name || !email || !code || !PROFILES[code]) {
      return jsonResponse({ ok: false, error: "dados incompletos" });
    }

    appendLead(name, email, whatsapp, sigla);
    sendResultEmail(name, email, code, gender);

    return jsonResponse({ ok: true });
  } catch (err) {
    return jsonResponse({ ok: false, error: String(err) });
  }
}

function getSheet() {
  const ss = SHEET_ID ? SpreadsheetApp.openById(SHEET_ID) : SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);
  }
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(["Data", "Nome", "E-mail", "Sigla", "WhatsApp"]);
  }
  return sheet;
}

function appendLead(name, email, whatsapp, sigla) {
  const sheet = getSheet();
  sheet.appendRow([new Date(), name, email, sigla, whatsapp]);
}

function sendResultEmail(name, email, code, gender) {
  const gk = gender === "F" ? "f" : "m";
  const p = PROFILES[code];
  const typeName = p["name_" + gk];
  const desc = p["desc_" + gk];
  const strengths = p.strengths.map(s => `<li>${s}</li>`).join("");
  const growth = p.growth.map(s => `<li>${s}</li>`).join("");
  const fullPageUrl = `${SITE_BASE_URL}/resultados/${code.toLowerCase()}-${gk}.html`;

  const subject = `Seu resultado: ${typeName} (${code}-${gender})`;
  const html = `
    <div style="font-family:Arial,sans-serif; max-width:560px; margin:0 auto; color:#2B2420;">
      <p style="text-transform:uppercase; letter-spacing:.08em; font-size:12px; color:#1F4B4C; font-weight:bold;">Método Supleno</p>
      <h1 style="color:#163736; font-size:24px;">${typeName}</h1>
      <p style="font-size:32px; font-weight:800; color:#C15A38; margin:0 0 16px;">${code}-${gender}</p>
      <p style="font-size:15px; line-height:1.6;">Olá, ${name}! Aqui está o seu resultado completo do Teste de Perfil de Personalidade.</p>
      <p style="font-size:15px; line-height:1.6;">${desc}</p>
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

// Função de teste manual — rode pelo editor do Apps Script (menu Executar) para
// conferir se a planilha e o envio de e-mail estão funcionando, sem precisar do site.
function testeManual() {
  const fakeEvent = {
    postData: {
      contents: JSON.stringify({
        name: "Teste",
        email: Session.getActiveUser().getEmail(),
        whatsapp: "",
        code: "INTJ",
        gender: "F"
      })
    }
  };
  const res = doPost(fakeEvent);
  Logger.log(res.getContent());
}
