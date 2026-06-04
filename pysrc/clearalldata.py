#!/usr/bin/env python3
import os
import sys
import asyncio
import logging
import shutil
from pathlib import Path
import asyncpg
import redis.asyncio as redis
from neo4j import AsyncGraphDatabase
from pgvector.asyncpg import register_vector

try:
    import tomllib
except ImportError:
    import tomli as tomllib

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def load_config(config_path="model.toml"):
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with open(config_path, "rb") as f:
        return tomllib.load(f)

async def reset_postgres(pg_cfg, embed_dim):
    dsn = pg_cfg.get("dsn")
    if not dsn:
        dsn = f"postgresql://{pg_cfg['user']}:{pg_cfg['password']}@{pg_cfg['host']}:{pg_cfg['port']}/{pg_cfg['database']}"
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute('CREATE EXTENSION IF NOT EXISTS vector;')
        await register_vector(conn)
        await conn.execute("DROP TABLE IF EXISTS topic_index CASCADE")
        await conn.execute("DROP TABLE IF EXISTS episodic_memory CASCADE")
        await conn.execute(f'''
            CREATE TABLE episodic_memory (
                id SERIAL PRIMARY KEY,
                text TEXT,
                embedding vector({embed_dim}),
                owner_id VARCHAR,
                scope VARCHAR DEFAULT 'shared',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        await conn.execute('''
            CREATE TABLE topic_index (
                id SERIAL PRIMARY KEY,
                entity VARCHAR(255),
                topic VARCHAR(255),
                episodic_id VARCHAR(255),
                text TEXT,
                session_id VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_entity ON topic_index(entity);')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_topic ON topic_index(topic);')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_session ON topic_index(session_id);')
        logger.info("PostgreSQL reset successful.")
    finally:
        await conn.close()

async def reset_neo4j(neo_cfg):
    uri = neo_cfg.get("uri", "bolt://localhost:7687")
    user = neo_cfg.get("user", "neo4j")
    password = neo_cfg.get("password", "neo4j")
    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    try:
        async with driver.session() as session:
            result = await session.run("MATCH (n) DETACH DELETE n")
            await result.consume()
            logger.info("Neo4j reset successful.")
    finally:
        await driver.close()

async def reset_redis(redis_cfg):
    host = redis_cfg.get("host", "localhost")
    port = redis_cfg.get("port", 6379)
    password = redis_cfg.get("password", "")
    db = redis_cfg.get("db", 0)
    r = redis.Redis(host=host, port=port, password=password, db=db, decode_responses=True)
    try:
        await r.flushdb()
        logger.info("Redis reset successful.")
    finally:
        await r.aclose()

def reset_filesystem_artifacts():
    base_dir = Path(__file__).parent.absolute()
    
    md_files = ["MEMORY_LEDGER.md", "CLINICAL_RULES.md"]
    for md in md_files:
        file_path = base_dir / md
        if file_path.exists():
            try:
                file_path.unlink()
                logger.info(f"Deleted: {file_path}")
            except Exception as e:
                logger.error(f"Failed to delete {file_path}: {e}")

    workspace_dir = base_dir / "workspace"
    if workspace_dir.exists():
        try:
            shutil.rmtree(workspace_dir, ignore_errors=True)
            logger.info(f"Deleted: {workspace_dir}")
        except Exception as e:
            logger.error(f"Failed to delete {workspace_dir}: {e}")
    workspace_dir.mkdir(parents=True, exist_ok=True)

    log_dir = base_dir.parent / "log"
    if log_dir.exists():
        try:
            shutil.rmtree(log_dir, ignore_errors=True)
            logger.info(f"Deleted: {log_dir}")
        except Exception as e:
            logger.error(f"Failed to delete {log_dir}: {e}")

async def main():
    if len(sys.argv) < 2 or sys.argv[1] != "--confirm":
        print("Usage: python reset_db.py --confirm")
        sys.exit(1)

    try:
        config = load_config()
    except Exception as e:
        logger.error(f"Config load failed: {e}")
        sys.exit(1)

    embed_cfg = config.get("embedding", {})
    embed_dim = embed_cfg.get("dim", 1024)

    if "postgres" in config:
        await reset_postgres(config["postgres"], embed_dim)

    if "neo4j" in config:
        await reset_neo4j(config["neo4j"])

    if "redis" in config:
        await reset_redis(config["redis"])

    reset_filesystem_artifacts()
    logger.info("All data cleared.")

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())