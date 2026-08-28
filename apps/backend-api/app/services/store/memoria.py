"""Estado em memoria do processo.

Padrao para desenvolvimento e para operacao em instancia unica. Preserva
exatamente o comportamento anterior a introducao do Redis: mesma latencia,
mesmo simulador, mesmo relogio de demonstracao.
"""
from __future__ import annotations

import asyncio
from collections import deque
from typing import Any, Awaitable, Callable, Deque, Dict, List, Optional, Set

from app.core.config import settings
from app.models.academico import RegistroPresenca
from app.models.dashboard import Alerta


class MemoriaStore:
    """Implementacao de EstadoStore sobre estruturas do proprio processo."""

    def __init__(self) -> None:
        self._aulas_abertas: Set[str] = set()
        self._presencas: Dict[str, Dict[str, RegistroPresenca]] = {}
        self._no_campus: Set[str] = set()

        self._feed: Deque[dict] = deque(maxlen=settings.MAX_EVENTOS_FEED)
        self._alertas: Deque[Alerta] = deque(maxlen=settings.MAX_ALERTAS)
        self._dedupe: Set[str] = set()

        self._serie: Dict[str, dict] = {}
        self._catracas: Dict[str, dict] = {}
        self._entradas = 0
        self._saidas = 0
        self._ancora: Optional[str] = None

        self._assinantes: List[Callable[[Any], Awaitable[None]]] = []
        self._lock = asyncio.Lock()

    # -- ciclo de vida ------------------------------------------------------
    async def iniciar(self) -> None:
        return None

    async def encerrar(self) -> None:
        return None

    @property
    def nome(self) -> str:
        return "memoria"

    # -- abertura de aula ---------------------------------------------------
    async def marcar_aula_aberta(self, aula_id: str) -> bool:
        async with self._lock:
            if aula_id in self._aulas_abertas:
                return False
            self._aulas_abertas.add(aula_id)
            return True

    async def aula_esta_aberta(self, aula_id: str) -> bool:
        return aula_id in self._aulas_abertas

    async def aulas_abertas(self) -> Set[str]:
        return set(self._aulas_abertas)

    async def fechar_aula(self, aula_id: str) -> None:
        async with self._lock:
            self._aulas_abertas.discard(aula_id)
            self._presencas.pop(aula_id, None)

    # -- presencas ----------------------------------------------------------
    async def salvar_presencas(self, aula_id: str, registros: List[RegistroPresenca]) -> None:
        async with self._lock:
            self._presencas[aula_id] = {r.aluno_ra: r for r in registros}

    async def obter_presenca(self, aula_id: str, ra: str) -> Optional[RegistroPresenca]:
        return self._presencas.get(aula_id, {}).get(ra)

    async def atualizar_presenca(self, registro: RegistroPresenca) -> None:
        async with self._lock:
            self._presencas.setdefault(registro.aula_id, {})[registro.aluno_ra] = registro

    async def presencas_da_aula(self, aula_id: str) -> List[RegistroPresenca]:
        return list(self._presencas.get(aula_id, {}).values())

    async def presencas_do_aluno(self, ra: str) -> List[RegistroPresenca]:
        return [
            registros[ra]
            for registros in self._presencas.values()
            if ra in registros
        ]

    # -- presenca fisica ----------------------------------------------------
    async def entrar_campus(self, ra: str) -> None:
        self._no_campus.add(ra)

    async def sair_campus(self, ra: str) -> None:
        self._no_campus.discard(ra)

    async def esta_no_campus(self, ra: str) -> bool:
        return ra in self._no_campus

    async def alunos_no_campus(self) -> Set[str]:
        return set(self._no_campus)

    async def total_no_campus(self) -> int:
        return len(self._no_campus)

    # -- feed ---------------------------------------------------------------
    async def push_evento(self, evento: dict) -> None:
        self._feed.appendleft(evento)

    async def feed(self, limite: int = 30) -> List[dict]:
        return list(self._feed)[:limite]

    # -- alertas ------------------------------------------------------------
    async def push_alerta(self, alerta: Alerta, chave_dedupe: str) -> bool:
        async with self._lock:
            if chave_dedupe in self._dedupe:
                return False
            self._dedupe.add(chave_dedupe)
            self._alertas.appendleft(alerta)
            return True

    async def alertas(self, limite: int = 20) -> List[Alerta]:
        return list(self._alertas)[:limite]

    async def limpar_dedupe(self, prefixo: str) -> None:
        async with self._lock:
            for chave in [c for c in self._dedupe if c.startswith(prefixo)]:
                self._dedupe.discard(chave)

    # -- serie --------------------------------------------------------------
    async def salvar_ponto_serie(self, hora: str, ponto: dict) -> None:
        self._serie[hora] = ponto

    async def serie(self) -> List[dict]:
        return [self._serie[h] for h in sorted(self._serie)]

    # -- contadores e catracas ---------------------------------------------
    async def incrementar_passagem(self, catraca_id: str, entrada: bool, momento: str) -> None:
        info = self._catracas.setdefault(
            catraca_id, {"online": True, "ultimo_evento_em": None, "entradas": 0, "saidas": 0}
        )
        info["online"] = True
        info["ultimo_evento_em"] = momento
        if entrada:
            info["entradas"] += 1
            self._entradas += 1
        else:
            info["saidas"] += 1
            self._saidas += 1

    async def estado_catracas(self) -> Dict[str, dict]:
        return {cid: dict(info) for cid, info in self._catracas.items()}

    async def marcar_catraca_offline(self, catraca_id: str) -> None:
        if catraca_id in self._catracas:
            self._catracas[catraca_id]["online"] = False

    async def contadores(self) -> Dict[str, int]:
        return {"entradas": self._entradas, "saidas": self._saidas}

    # -- relogio ------------------------------------------------------------
    async def ancora_relogio(self) -> Optional[str]:
        return self._ancora

    async def definir_ancora_relogio(self, iso: str) -> None:
        self._ancora = iso

    # -- difusao ------------------------------------------------------------
    async def publicar(self, payload: Any) -> None:
        for callback in list(self._assinantes):
            await callback(payload)

    async def assinar(self, callback: Callable[[Any], Awaitable[None]]) -> None:
        self._assinantes.append(callback)
