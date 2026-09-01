"""Descobre o contrato real da API do JACAD.

O QUE JA FOI DESCARTADO (01/09/2026, contra insted-developer)

A API responde, mas `/api/**` esta guardado por inteiro: caminho inexistente,
endpoint real e a propria raiz devolvem o mesmo 401 com

    errorCode: {"code": "EXPTK01", "desc": "Token invalido ou expirado"}

Consequencias praticas:

* O 401 nao distingue caminho existente de inexistente, entao **nao da para
  descobrir endpoints por sondagem**. A secao 3 deste script so vira util
  depois que a autenticacao passar.
* 15 formatos de credencial foram testados - Bearer, Basic, token cru, X-API-KEY,
  apikey, X-Auth-Token, query string - todos com a mesma recusa.
* A documentacao (swagger, api-docs, actuator) tambem exige autenticacao.
* 23 nomes de endpoint de login foram testados sob /api e na raiz: 401 e 404
  respectivamente. Nao ha login publico com nome obvio.

A mensagem "expirado" sugere token de vida curta, obtido por uma troca, e nao
chave permanente. Sem a documentacao do JACAD - ou um exemplo de requisicao que
funcione - nao da para avancar por tentativa.

Por que existe: o cliente REST em app/services/jacad_client.py foi escrito sem
acesso a documentacao. Os caminhos (/academico/alunos) e os nomes de campo
(registroAcademico, turma.codigo) sao suposicoes. Este script bate na API de
verdade e mostra o que ela responde, para o mapeamento sair de evidencia e nao
de chute.

Roda na sua maquina, lendo JACAD_BASE_URL e JACAD_TOKEN do .env. O token nunca
e impresso nem enviado para lugar nenhum alem do proprio ERP.

Uso:
    python explorar_jacad.py                 # sonda os caminhos candidatos
    python explorar_jacad.py /meu/caminho    # inspeciona um caminho especifico
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core import parametros  # noqa: F401,E402  carrega o .env
from app.core.config import settings  # noqa: E402

# Caminhos que o cliente usa hoje, mais variacoes comuns em ERPs academicos.
# Nenhum deles e confirmado: a lista existe para achar o que responde.
CANDIDATOS = [
    "/academico/alunos", "/alunos", "/api/alunos", "/v1/alunos",
    "/academico/professores", "/professores", "/api/professores",
    "/academico/turmas", "/turmas",
    "/academico/grade-horaria", "/grade-horaria", "/horarios",
]

# O backend do JACAD e Spring: a recusa vem do Spring Security, que responde
# antes de rotear. Enquanto a autenticacao nao passar, TODO caminho devolve 401
# - existindo ou nao. Por isso a ordem aqui e: documentacao, depois esquema de
# autenticacao, e so entao os caminhos.
DOCUMENTACAO = [
    "/v3/api-docs", "/v2/api-docs", "/api-docs",
    "/swagger-ui/index.html", "/swagger-ui.html", "/swagger-resources",
    "/actuator", "/actuator/health",
]

# Um token de 32 caracteres nao e JWT; parece chave de API. Cada entrada e
# (rotulo, headers, query).
def _variantes_auth(token: str):
    import base64

    b64 = base64.b64encode(token.encode()).decode()
    b64_usuario = base64.b64encode(f"{token}:".encode()).decode()
    return [
        ("Authorization: Bearer",   {"Authorization": f"Bearer {token}"}, {}),
        ("Authorization: cru",      {"Authorization": token}, {}),
        ("Authorization: Basic",    {"Authorization": f"Basic {b64}"}, {}),
        ("Authorization: Basic u:", {"Authorization": f"Basic {b64_usuario}"}, {}),
        ("Authorization: Token",    {"Authorization": f"Token {token}"}, {}),
        ("Authorization: ApiKey",   {"Authorization": f"ApiKey {token}"}, {}),
        ("X-API-KEY",               {"X-API-KEY": token}, {}),
        ("x-api-key",               {"x-api-key": token}, {}),
        ("apikey",                  {"apikey": token}, {}),
        ("api-key",                 {"api-key": token}, {}),
        ("token",                   {"token": token}, {}),
        ("X-Auth-Token",            {"X-Auth-Token": token}, {}),
        ("query ?token=",           {}, {"token": token}),
        ("query ?apikey=",          {}, {"apikey": token}),
            ("query ?access_token=",    {}, {"access_token": token}),
    ]


def _sondar_documentacao(base: str) -> None:
    """Procura a especificacao da API, que resolveria o mapeamento de uma vez."""
    import httpx

    print("== 1. Documentacao da API (sem autenticacao) ==")
    achou = False
    with httpx.Client(base_url=base, timeout=20.0, follow_redirects=True) as http:
        for caminho in DOCUMENTACAO:
            try:
                r = http.get(caminho, headers={"Accept": "*/*"})
            except Exception as erro:
                print(f"    {caminho:28} FALHOU {type(erro).__name__}")
                continue
            marca = "OK " if r.status_code == 200 else "   "
            print(f"{marca} {caminho:28} HTTP {r.status_code}  {len(r.content)} bytes")
            if r.status_code == 200 and r.content:
                achou = True
                destino = pathlib.Path(caminho.strip("/").replace("/", "_") + ".json")
                destino.write_bytes(r.content)
                print(f"      -> salvo em {destino}")
    if not achou:
        print("    Nenhuma documentacao aberta.")
    print()


def _descobrir_auth(base: str, token: str, caminho: str) -> None:
    """Tenta esquemas de autenticacao ate a resposta deixar de ser 401."""
    import httpx

    print(f"== 2. Esquema de autenticacao (contra {caminho}) ==")
    with httpx.Client(base_url=base, timeout=20.0, follow_redirects=True) as http:
        for rotulo, headers, query in _variantes_auth(token):
            try:
                r = http.get(caminho, headers={"Accept": "application/json", **headers},
                             params=query)
            except Exception as erro:
                print(f"    {rotulo:26} FALHOU {type(erro).__name__}")
                continue
            # 401 = continua recusando. Qualquer outra coisa e progresso: 200
            # obviamente, mas 403/404 tambem, porque significam que passou da
            # autenticacao e chegou na autorizacao ou no roteamento.
            marca = "   " if r.status_code == 401 else ">> "
            print(f"{marca} {rotulo:26} HTTP {r.status_code}  {r.text[:90]}")
    print()




LIMITE_AMOSTRA = 2


def _formato(valor, profundidade=0):
    """Descreve o formato de um valor sem despejar o conteudo inteiro."""
    if isinstance(valor, dict):
        if profundidade >= 2:
            return "{...}"
        return "{" + ", ".join(
            f"{k}: {_formato(v, profundidade + 1)}" for k, v in list(valor.items())[:20]
        ) + "}"
    if isinstance(valor, list):
        if not valor:
            return "[]"
        return f"[{_formato(valor[0], profundidade + 1)}] x{len(valor)}"
    if valor is None:
        return "null"
    return type(valor).__name__


def main() -> int:
    base = (settings.JACAD_BASE_URL or "").rstrip("/")
    token = settings.JACAD_TOKEN

    if not base:
        print("JACAD_BASE_URL nao esta definida. Preencha o .env e rode de novo.")
        return 1
    print(f"Base    : {base}")
    print(f"Token   : {'definido, ' + str(len(token)) + ' caracteres' if token else 'AUSENTE'}")
    print()

    if sys.argv[1:]:
        _sondar_caminhos(base, token, sys.argv[1:])
        return 0

    _sondar_documentacao(base)
    _descobrir_auth(base, token, CANDIDATOS[0])
    print("== 3. Caminhos, com o esquema atual (Bearer) ==")
    print("   Enquanto a autenticacao nao passar, todo caminho devolve 401 -")
    print("   o Spring recusa antes de rotear. Esta secao so informa depois")
    print("   que a secao 2 encontrar um esquema que saia do 401.")
    print()
    _sondar_caminhos(base, token, CANDIDATOS)
    return 0


def _sondar_caminhos(base: str, token: str, caminhos) -> int:
    """Bate em cada caminho e descreve o que voltou."""
    import httpx

    encontrados = []

    with httpx.Client(
        base_url=base,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=30.0,
        follow_redirects=True,
    ) as http:
        for caminho in caminhos:
            try:
                r = http.get(caminho)
            except Exception as erro:
                print(f"  {caminho:32} FALHOU  {type(erro).__name__}: {erro}")
                continue

            marca = "OK " if r.status_code == 200 else "   "
            print(f"{marca} {caminho:32} HTTP {r.status_code}  {r.headers.get('content-type','')[:40]}")

            if r.status_code != 200:
                if r.status_code in (401, 403):
                    print(f"      -> autenticacao recusada: {r.text[:120]}")
                continue

            try:
                corpo = r.json()
            except Exception:
                print(f"      -> resposta nao e JSON: {r.text[:120]}")
                continue

            encontrados.append(caminho)
            # Muitos ERPs embrulham a lista em {"data": [...]} ou {"content": [...]}.
            print(f"      formato: {_formato(corpo)}")
            itens = corpo
            for chave in ("data", "content", "items", "resultado", "registros"):
                if isinstance(itens, dict) and chave in itens:
                    print(f"      lista embrulhada em {chave!r}")
                    itens = itens[chave]
                    break
            if isinstance(itens, list) and itens:
                print(f"      campos do 1o item: {sorted(itens[0])}"
                      if isinstance(itens[0], dict) else f"      1o item: {itens[0]!r}")
                print("      amostra:")
                for item in itens[:LIMITE_AMOSTRA]:
                    print("        " + json.dumps(item, ensure_ascii=False)[:400])
            print()

    print()
    if encontrados:
        print("Caminhos que responderam 200:")
        for c in encontrados:
            print(f"  {c}")
        print("\nMe mande esta saida (sem o token, que nao aparece aqui) e eu ajusto")
        print("o cliente REST para os campos reais.")
    else:
        print("Nenhum caminho respondeu 200. Verifique a base, o token e o formato")
        print("de autenticacao. Se a documentacao indicar outro caminho, rode:")
        print("  python explorar_jacad.py /o/caminho/da/documentacao")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
