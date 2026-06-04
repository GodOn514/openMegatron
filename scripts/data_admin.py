import argparse
import asyncio
import json
import os
import urllib.parse
from pathlib import Path
from typing import Iterable

import asyncpg
import redis.asyncio as redis
from neo4j import AsyncGraphDatabase

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


CONVERSATION_PATTERNS = [
    "agent_history:*",
    "core_memory:*",
    "notifications:*",
    "active_chat_turn:*",
    "confirm_req:*",
    "failure:*",
    "chat:shared:*",
    "chat:private:*",
]


def load_config(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("rb") as file:
        return tomllib.load(file)


def redis_url(redis_cfg: dict) -> str:
    host = redis_cfg.get("host", "localhost")
    port = int(redis_cfg.get("port", 6379))
    db = int(redis_cfg.get("db", 0))
    password = redis_cfg.get("password")
    if password:
        encoded = urllib.parse.quote_plus(str(password))
        return f"redis://:{encoded}@{host}:{port}/{db}"
    return f"redis://{host}:{port}/{db}"


def postgres_dsn(config: dict) -> str:
    pg_cfg = config.get("postgres") or config.get("postgresql") or config.get("pgvector") or {}
    if pg_cfg.get("dsn"):
        return str(pg_cfg["dsn"])
    user = pg_cfg.get("user", "root")
    password = pg_cfg.get("password", "root")
    host = pg_cfg.get("host", "localhost")
    port = int(pg_cfg.get("port", 54320))
    database = pg_cfg.get("database", "root")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


def command_count(command: str) -> int:
    try:
        return int(str(command).split()[-1])
    except Exception:
        return 0


async def delete_redis_patterns(config: dict, patterns: Iterable[str]) -> int:
    redis_cfg = config.get("redis", {}) or {}
    client = redis.from_url(redis_url(redis_cfg), decode_responses=True)
    deleted = 0
    try:
        for pattern in patterns:
            batch = []
            async for key in client.scan_iter(match=pattern, count=200):
                batch.append(key)
                if len(batch) >= 200:
                    deleted += int(await client.delete(*batch))
                    batch = []
            if batch:
                deleted += int(await client.delete(*batch))
    finally:
        await client.aclose()
    return deleted


async def clear_postgres_memory(config: dict) -> dict:
    deleted = {}
    conn = await asyncpg.connect(postgres_dsn(config))
    try:
        async with conn.transaction():
            for table in ("memory_links", "memory_evolution_log", "topic_index", "episodic_memory"):
                try:
                    deleted[table] = command_count(await conn.execute(f"DELETE FROM {table}"))
                except Exception as exc:
                    deleted[table] = 0
                    print(f"[WARN] Skipped {table}: {exc}")
    finally:
        await conn.close()
    return deleted


async def clear_neo4j_memory(config: dict) -> int:
    neo_cfg = config.get("neo4j", {}) or {}
    uri = neo_cfg.get("uri", "bolt://localhost:7687")
    user = neo_cfg.get("user", "neo4j")
    password = neo_cfg.get("password", "root")
    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    try:
        async with driver.session() as session:
            result = await session.run("MATCH (n) DETACH DELETE n")
            summary = await result.consume()
            return int(getattr(summary.counters, "nodes_deleted", 0) or 0)
    finally:
        await driver.close()


async def main() -> int:
    parser = argparse.ArgumentParser(description="Megatron local data manager")
    parser.add_argument("--config", default="pysrc/model.toml")
    parser.add_argument("--clear-conversations", action="store_true")
    parser.add_argument("--clear-memory", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()

    if not args.confirm:
        print("[ERROR] Refusing to modify data without --confirm.")
        return 1
    if not args.clear_conversations and not args.clear_memory:
        print("[ERROR] No operation selected.")
        return 1

    config = load_config(Path(args.config))
    result = {}

    if args.clear_conversations:
        deleted = await delete_redis_patterns(config, CONVERSATION_PATTERNS)
        result["redis_conversation_keys"] = deleted
        print(f"[OK] Cleared Redis conversation keys: {deleted}")

    if args.clear_memory:
        pg_deleted = await clear_postgres_memory(config)
        result["postgres_memory_rows"] = pg_deleted
        print(f"[OK] Cleared PostgreSQL memory rows: {json.dumps(pg_deleted, ensure_ascii=False)}")
        try:
            neo4j_deleted = await clear_neo4j_memory(config)
            result["neo4j_nodes"] = neo4j_deleted
            print(f"[OK] Cleared Neo4j memory nodes: {neo4j_deleted}")
        except Exception as exc:
            result["neo4j_error"] = str(exc)
            print(f"[WARN] Neo4j clear skipped: {exc}")
        redis_core_deleted = await delete_redis_patterns(config, ["core_memory:*"])
        result["redis_core_memory_keys"] = redis_core_deleted
        print(f"[OK] Cleared Redis core memory keys: {redis_core_deleted}")

    print(json.dumps({"status": "success", "result": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    raise SystemExit(asyncio.run(main()))
