# API do JaCad — contrato real

Levantado em 01/09/2026 contra `insted-developer`, a partir do OpenAPI
(`Acadêmico v3.1.60.410`) e de chamadas reais. Substitui as suposições que eu
tinha escrito no cliente REST.

## Autenticação: é uma troca, não uma chave fixa

O valor de 32 caracteres **não** é o token de acesso. Ele é a chave cadastrada
no sistema acadêmico (desktop) e serve para obter um access token:

```
POST /api/v1/auth/token
Header: token: <chave de 32 caracteres>
→ 200 { "token": "<access token, ~575 caracteres>", "expiresIn": <epoch ms>, ... }
```

Depois, em todas as chamadas:

```
Authorization: <access token>      (sem "Bearer")
```

Mandar a chave direto no `Authorization` devolve 401 com
`errorCode: EXPTK01, "Token inválido ou expirado"` — foi o que travou a primeira
tentativa. `/api/**` é guardado por inteiro: caminho inexistente e a própria raiz
devolvem o mesmo 401, então **não dá para descobrir endpoints por sondagem**.

Base correta: `https://insted-developer.jacad.com.br` — **sem** `/api`, que já faz
parte dos caminhos.

## Onde estão os dados

| o que | endpoint | observação |
|---|---|---|
| Alunos (cadastro) | `GET /api/v1/academico/alunos` | 10.129 no total, **sem filtro de ativo** |
| Matrículas | `GET /api/v1/academico/matriculas` | é aqui que se acha quem está ativo |
| Períodos letivos | `GET /api/v1/academico/periodos-letivos/` | exige `idOrg`, que o token não devolve |
| Turmas | `GET /api/v1/academico/turmas` | exige `turmaIdPeriodoLetivo` e `turmaStatus` |
| Disciplinas da turma | `GET /api/v1/academico/turmas/{idTurma}/disciplinas` | **traz o professor** |
| Horários | `GET /api/v1/academico/disciplinas/{idDisciplinaProfessor}/horarios` | **traz sala e bloco** |

Não existe endpoint de professores. Eles vêm das disciplinas da turma, com
`idProfessor` e `professor`.

Paginação: `pageSize` (máx. 500) e `currentPage`; a resposta traz
`page.totalElements` e a lista em `elements`.

## Período letivo corrente

`idPeriodoLetivo = 42`, nome `20262`, situação `ABERTO`.

Matrículas `ATIVA` nesse período: **1.733**, das quais

* **1.508** na unidade física `Insted` (presencial — é o que a maquete acompanha)
* 225 em `Insted Digital`

Confere com os 1.732 informados pela Secretaria. As outras 2.965 matrículas
ativas da base são de Pós, Extensão e períodos anteriores.

105 turmas distintas com aluno matriculado; 108 turmas ativas, sendo 80
presenciais. Turnos: 93 noturno, 14 matutino, 1 integral.

## O ensalamento estava na API o tempo todo

O horário devolve a sala **com o código que a Secretaria usa**:

```json
{
  "idDisciplinaHorarioSala": 268170,
  "idSala": 55, "sala": "04A", "bloco": "FERNANDO CORREIA",
  "idDisciplinaProfessor": 34994, "idProfessor": 547,
  "professor": "...", "disciplina": "...",
  "horaInicio": "1970-01-01T19:00:00-0300",
  "horaTermino": "1970-01-01T19:50:00-0300",
  "dataAula": "2026-08-13", "tipo": "F"
}
```

Dois pontos que mudam o modelo:

* `dataAula` é **data real**, não dia da semana. O JaCad tem o calendário de
  aulas, não uma grade recorrente — melhor do que assumíamos.
* `horaInicio`/`horaTermino` são o **tempo de aula** (~50 min), não o bloco
  inteiro. Uma "aula das 19:00 às 22:30" aparece como várias linhas seguidas.

### As 35 salas em uso (período 20262, turmas presenciais)

Bloco `FERNANDO CORREIA` (15.735 horários):

```
01A  04A
01B 02B 03B 04B 05B 06B 07B 08B 09B 10B 11B 13B
01C 02C 03C 04C 05C 06C 07C 08C 09C 10C 11C 12C 13C 14C 15C 16C 17C 18C
LABINF 1C   LABINF 2C
```

Bloco `NÚCLEO DE PRÁTICAS INTEGRADAS` (525 horários): `Prajur`.

O sufixo A/B/C aparenta ser o pavimento, mas **isso ainda não está confirmado** —
é o que falta casar com os códigos das plantas da Sigma em `campus_seed.py`.

85 professores distintos aparecem nas disciplinas do período.
