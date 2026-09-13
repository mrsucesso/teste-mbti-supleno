# Contrato neutro de integração Supleno — v1

Status: contrato local de homologação. Não é endpoint publicado, não cria infraestrutura e não transporta dados.

Identificador: `supleno.integracao.v1`.

## Fluxo de captura

1. O frontend calcula e mostra o resultado antes da captura opcional.
2. Um adaptador normaliza o request para os campos dos schemas.
3. O receptor valida `contract`, `submission_id`, produto, pessoa, resultado, consentimento e atribuição.
4. A chave `submission_id` é idempotente. Mesmo id com mesmo conteúdo retorna `duplicate`; mesmo id com conteúdo diferente é `rejected` com erro neutro.
5. Captura aceita retorna `accepted` e inicia a sequência em `pending`. O receptor nunca envia comunicação no mesmo request.

Schemas: `schemas/captura.request.schema.json` e `schemas/captura.response.schema.json`.

## Consentimento, opt-out e minimização

`consent.granted` deve ser exatamente `true`, com `captured_at`, finalidade e versão. Sem consentimento, não persiste nem entra em sequência. O opt-out é uma transição terminal `opt_out`, cancela itens pendentes, bloqueia novo cadastro até política explícita de reconsentimento e não coloca e-mail na URL. O contrato não prescreve provedor de token.

UTMs (`utm_source`, `utm_medium`, `utm_campaign`) e `origin` são atribuição opcional, separados da identidade. Não são segredos. Dados de progresso local não incluem nome, e-mail ou WhatsApp.

## Estados da sequência e erros

Estados de intenção: `pending` → `sending` → `sent`; falha ou lease vencida vira `uncertain` e exige reconciliação explícita. O encerramento normal é `completed`; opt-out termina em `opt_out`. Não existe reenvio automático às cegas.

Códigos mínimos de erro: `invalid_request`, `consent_required`, `duplicate_payload_conflict`, `suppressed`, `temporary_failure` e `configuration_blocked`. A mensagem externa é curta e não revela stack trace, segredo ou PII. `temporary_failure` pode ser tentado novamente; conflito, consentimento e supressão não.

## Exportação

A exportação deve ser explícita, autenticada na camada que escolher a tecnologia e versionada. O formato mínimo é JSON ou CSV com `submission_id`, produto, resultado, atribuição, estado da sequência e `opt_out`. Não inclui tokens, credenciais ou conteúdo de logs. A política de retenção deve ser definida antes de produção; o simulador só mantém memória durante o processo.

## Compatibilidade

Frontend, Apps Script e `FunilStore` já possuem regras equivalentes, mas usam nomes históricos diferentes. A matriz `matriz-adaptadores.md` documenta o mapeamento sem alterar nenhum backend real nesta fase. A planilha e o banco são opções futuras para implementar o mesmo contrato, não decisões tecnológicas.

## Homologação segura

Execute:

```bash
python3 scripts/simulador-integracao-v1.py
python3 -m unittest tests.test_fase10e
```

O simulador usa somente `example.invalid`, não importa cliente HTTP, não abre rede e imprime um resumo JSON com `rede_real: false`.
