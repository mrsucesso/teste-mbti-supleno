# Matriz de adaptadores — contrato Supleno Integracao v1

O contrato `supleno.integracao.v1` define o comportamento. Não escolhe tecnologia nem cria endpoint, banco, planilha ou credencial.

| Camada | Entrada/saída do contrato | Implementação atual | Adaptação obrigatória |
|---|---|---|---|
| Frontend | `person.name/email/whatsapp`, `product`, `result`, `scores`, `consent`, `attribution` | Os três HTML montam payload legado com `name`, `email`, `teste`, `resultado`, `pontuacoes`, `consentimento` e UTMs | Adaptador de borda renomeia `teste` para `product`, agrupa pessoa e consentimento; resultado aparece antes da captura |
| Apps Script | Request de captura; resposta `accepted/duplicate/rejected/error` | `apps-script/Code.gs` valida os três produtos, usa `submission_id`, fingerprint, consentimento, outbox e opt-out | Adaptador mantém planilha como detalhe; normaliza `ok/duplicate` para status do contrato sem expor detalhes internos |
| Backend local | Mesmo comportamento, sem rede | `backend/funil_store.py` (`FunilStore`) persiste JSON Lines e opera em sandbox | Adaptador mapeia `nome/email/whatsapp`, `teste`, `data_criacao`, `estado_sequencia` e `opt_out` para os nomes neutros |
| Métricas | Eventos sem PII | `assets/funil-analytics.js` registra localmente | Métricas não fazem parte da captura e só podem ser despachadas com configuração explícita |

## Implementações futuras

| Persistência | Chave idempotente | Estados | Opt-out | Exportação |
|---|---|---|---|---|
| Planilha | Coluna `submission_id` + fingerprint | Coluna de estado/outbox, com `pending`, `sending`, `sent`, `uncertain` | Registro de supressão e token opaco fora da URL | Leitura de colunas canônicas para JSON/CSV, sem segredo |
| Banco | Índice único em `submission_id` e fingerprint | Enum/tabela de transições com auditoria | Tabela de supressão com hash/token e bloqueio transacional | Consulta versionada para JSON/CSV, com minimização |

Nenhuma opção é escolhida nesta fase. O simulador `scripts/simulador-integracao-v1.py` prova o fluxo apenas em memória, com dados sintéticos e sem rede real.
