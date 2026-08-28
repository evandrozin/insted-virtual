"""Estado compartilhado em Redis, para operar com varias instancias.

Necessario em serverless (Vercel Functions) e em qualquer deploy com mais de
uma replica: uma conexao WebSocket fica presa a uma instancia, entao uma
passagem de catraca recebida na instancia B precisa alcancar o painel ligado
na instancia A. Isso e feito pelo canal pub/sub.

Todas as chaves expiram em 20 h: o estado e do dia letivo e se limpa sozinho.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

from app.core.config import settings
from app.models.academico import RegistroPresenca
from app.models.dashboard import Alerta
from app.services.store.base import CANAL_EVENTOS

NS = "insted"
TTL_DIA = 60 * 60 * 20

K_AULAS_ABERTAS = f"{NS}:aulas_abertas"
K_NO_CAMPUS = f"{NS}:no_campus"
K_FEED = f"{NS}:feed"
K_ALERTAS = f"{NS}:alertas"
K_DEDUPE = f"{NS}:alertas_dedupe"
K_SERIE = f"{NS}:serie"
K_CATRACAS = f"{NS}:catracas"
K_CONTADORES = f"{NS}:contadores"
K_ANCORA = f"{NS}:ancora_relogio"


def _k_presencas(aula_id: str) -> str:
    return f"{NS}:presencas:{aula_id}"


def _k_aulas_do_aluno(ra: str) -> str:
    return f"{NS}:aluno_aulas:{ra}"


class RedisStore:
    """Implementacao de EstadoStore sobre Redis."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._redis = None
        self._pubsub_task: Optional[asyncio.Task] = None
        self._assinantes: List[Callable[[Any], Awaitable[None]]] = []

    # -- ciclo de vida ------------------------------------------------------
    async def iniciar(self) -> None:
        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(
            self._url, encoding="utf-8", decode_responses=True
        )
        await self._redis.ping()

    async def encerrar(self) -> None:
        if self._pubsub_task:
            self._pubsub_task.cancel()
            try:
                await self._pubsub_task
            except (asyncio.CancelledError, Exception):
                pass
        if self._redis:
            await self._redis.aclose()

    @property
    def nome(self) -> str:
        return "redis"

    # -- abertura de aula ---------------------------------------------------
    async def marcar_aula_aberta(self, aula_id: str) -> bool:
        # SADD devolve 1 so para quem inseriu: serve de trava distribuida.
        adicionou = await self._redis.sadd(K_AULAS_ABERTAS, aula_id)
        await self._redis.expire(K_AULAS_ABERTAS, TTL_DIA)
        return bool(adicionou)

    async def aula_esta_aberta(self, aula_id: str) -> bool:
        return bool(await self._redis.sismember(K_AULAS_ABERTAS, aula_id))

    async def aulas_abertas(self) -> Set[str]:
        return set(await self._redis.smembers(K_AULAS_ABERTAS))

    async def fechar_aula(self, aula_id: str) -> None:
        pipe = self._redis.pipeline()
        pipe.srem(K_AULAS_ABERTAS, aula_id)
        pipe.delete(_k_presencas(aula_id))
        await pipe.execute()

    # -- presencas ----------------------------------------------------------
    async def salvar_presencas(self, aula_id: str, registros: List[RegistroPresenca]) -> None:
        if not registros:
            return
        chave = _k_presencas(aula_id)
        pipe = self._redis.pipeline()
        pipe.hset(chave, mapping={r.aluno_ra: r.model_dump_json() for r in registros})
        pipe.expire(chave, TTL_DIA)
        for r in registros:
            pipe.sadd(_k_aulas_do_aluno(r.aluno_ra), aula_id)
            pipe.expire(_k_aulas_do_aluno(r.aluno_ra), TTL_DIA)
        await pipe.execute()

    async def obter_presenca(self, aula_id: str, ra: str) -> Optional[RegistroPresenca]:
        cru = await self._redis.hget(_k_presencas(aula_id), ra)
        return RegistroPresenca.model_validate_json(cru) if cru else None

    async def atualizar_presenca(self, registro: RegistroPresenca) -> None:
        await self._redis.hset(
            _k_presencas(registro.aula_id),
            registro.aluno_ra,
            registro.model_dump_json(),
        )

    async def presencas_da_aula(self, aula_id: str) -> List[RegistroPresenca]:
        bruto = await self._redis.hgetall(_k_presencas(aula_id))
        return [RegistroPresenca.model_validate_json(v) for v in bruto.values()]

    async def presencas_do_aluno(self, ra: str) -> List[RegistroPresenca]:
        aulas = await self._redis.smembers(_k_aulas_do_aluno(ra))
        if not aulas:
            return []
        pipe = self._redis.pipeline()
        for aula_id in aulas:
            pipe.hget(_k_presencas(aula_id), ra)
        return [
            RegistroPresenca.model_validate_json(cru)
            for cru in await pipe.execute()
            if cru
        ]

    # -- presenca fisica ----------------------------------------------------
    async def entrar_campus(self, ra: str) -> None:
        await self._redis.sadd(K_NO_CAMPUS, ra)
        await self._redis.expire(K_NO_CAMPUS, TTL_DIA)

    async def sair_campus(self, ra: str) -> None:
        await self._redis.srem(K_NO_CAMPUS, ra)

    async def esta_no_campus(self, ra: str) -> bool:
        return bool(await self._redis.sismember(K_NO_CAMPUS, ra))

    async def alunos_no_campus(self) -> Set[str]:
        return set(await self._redis.smembers(K_NO_CAMPUS))

    async def total_no_campus(self) -> int:
        return int(await self._redis.scard(K_NO_CAMPUS))

    # -- feed ---------------------------------------------------------------
    async def push_evento(self, evento: dict) -> None:
        pipe = self._redis.pipeline()
        pipe.lpush(K_FEED, json.dumps(evento, ensure_ascii=False))
        pipe.ltrim(K_FEED, 0, settings.MAX_EVENTOS_FEED - 1)
        pipe.expire(K_FEED, TTL_DIA)
        await pipe.execute()

    async def feed(self, limite: int = 30) -> List[dict]:
        return [json.loads(v) for v in await self._redis.lrange(K_FEED, 0, limite - 1)]

    # -- alertas ------------------------------------------------------------
    async def push_alerta(self, alerta: Alerta, chave_dedupe: str) -> bool:
        if not await self._redis.sadd(K_DEDUPE, chave_dedupe):
            return False
        pipe = self._redis.pipeline()
        pipe.expire(K_DEDUPE, TTL_DIA)
        pipe.lpush(K_ALERTAS, alerta.model_dump_json())
        pipe.ltrim(K_ALERTAS, 0, settings.MAX_ALERTAS - 1)
        pipe.expire(K_ALERTAS, TTL_DIA)
        await pipe.execute()
        return True

    async def alertas(self, limite: int = 20) -> List[Alerta]:
        return [
            Alerta.model_validate_json(v)
            for v in await self._redis.lrange(K_ALERTAS, 0, limite - 1)
        ]

    async def limpar_dedupe(self, prefixo: str) -> None:
        chaves = [c for c in await self._redis.smembers(K_DEDUPE) if c.startswith(prefixo)]
        if chaves:
            await self._redis.srem(K_DEDUPE, *chaves)

    # -- serie --------------------------------------------------------------
    async def salvar_ponto_serie(self, hora: str, ponto: dict) -> None:
        await self._redis.hset(K_SERIE, hora, json.dumps(ponto))
        await self._redis.expire(K_SERIE, TTL_DIA)

    async def serie(self) -> List[dict]:
        bruto = await self._redis.hgetall(K_SERIE)
        return [json.loads(bruto[h]) for h in sorted(bruto)]

    # -- contadores e catracas ---------------------------------------------
    async def incrementar_passagem(self, catraca_id: str, entrada: bool, momento: str) -> None:
        campo = "entradas" if entrada else "saidas"
        pipe = self._redis.pipeline()
        pipe.hincrby(K_CONTADORES, campo, 1)
        pipe.expire(K_CONTADORES, TTL_DIA)
        pipe.hset(K_CATRACAS, catraca_id, json.dumps(
            {"online": True, "ultimo_evento_em": momento, "campo": campo}
        ))
        pipe.hincrby(f"{K_CATRACAS}:{catraca_id}", campo, 1)
        pipe.expire(f"{K_CATRACAS}:{catraca_id}", TTL_DIA)
        pipe.expire(K_CATRACAS, TTL_DIA)
        await pipe.execute()

    async def estado_catracas(self) -> Dict[str, dict]:
        bruto = await self._redis.hgetall(K_CATRACAS)
        saida: Dict[str, dict] = {}
        for cid, cru in bruto.items():
            info = json.loads(cru)
            contagem = await self._redis.hgetall(f"{K_CATRACAS}:{cid}")
            saida[cid] = {
                "online": info.get("online", True),
                "ultimo_evento_em": info.get("ultimo_evento_em"),
                "entradas": int(contagem.get("entradas", 0)),
                "saidas": int(contagem.get("saidas", 0)),
            }
        return saida

    async def marcar_catraca_offline(self, catraca_id: str) -> None:
        cru = await self._redis.hget(K_CATRACAS, catraca_id)
        if not cru:
            return
        info = json.loads(cru)
        info["online"] = False
        await self._redis.hset(K_CATRACAS, catraca_id, json.dumps(info))

    async def contadores(self) -> Dict[str, int]:
        bruto = await self._redis.hgetall(K_CONTADORES)
        return {
            "entradas": int(bruto.get("entradas", 0)),
            "saidas": int(bruto.get("saidas", 0)),
        }

    # -- relogio ------------------------------------------------------------
    async def ancora_relogio(self) -> Optional[str]:
        return await self._redis.get(K_ANCORA)

    async def definir_ancora_relogio(self, iso: str) -> None:
        # NX: a primeira instancia fixa a ancora, as demais a herdam.
        await self._redis.set(K_ANCORA, iso, ex=TTL_DIA, nx=True)

    # -- difusao ------------------------------------------------------------
    async def publicar(self, payload: Any) -> None:
        from app.services.realtime import json_seguro

        await self._redis.publish(CANAL_EVENTOS, json_seguro(payload))

    async def assinar(self, callback: Callable[[Any], Awaitable[None]]) -> None:
        self._assinantes.append(callback)
        if self._pubsub_task is None:
            self._pubsub_task = asyncio.create_task(self._escutar())

    async def _escutar(self) -> None:
        """Relay do canal Redis para os assinantes locais."""
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(CANAL_EVENTOS)
        try:
            async for msg in pubsub.listen():
                if msg.get("type") != "message":
                    continue
                try:
                    payload = json.loads(msg["data"])
                except (ValueError, TypeError):
                    continue
                for callback in list(self._assinantes):
                    try:
                        await callback(payload)
                    except Exception as erro:
                        print(f"[pubsub] assinante falhou: {erro}")
        except asyncio.CancelledError:
            raise
        finally:
            try:
                await pubsub.aclose()
            except Exception:
                pass
