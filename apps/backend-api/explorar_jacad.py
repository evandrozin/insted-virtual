"""Descobre o contrato real da API do JACAD.

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
    if not token:
        print("Sem token a maioria dos ERPs devolve 401. Preencha JACAD_TOKEN.")
    print()

    import httpx

    caminhos = sys.argv[1:] or CANDIDATOS
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
