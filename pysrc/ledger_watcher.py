import os
import time
import asyncio
import re
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import asyncpg
from pgvector.asyncpg import register_vector
from neo4j import AsyncGraphDatabase
from sentence_transformers import SentenceTransformer
from logging_setup import configure_module_logger

try:
    import tomllib
except ImportError:
    import tomli as tomllib

logger = configure_module_logger(__name__, "ledger_watcher.log")

def load_config(config_path: str = "model.toml") -> dict:
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config not found: {config_path}")
    with open(config_path, "rb") as f:
        return tomllib.load(f)

def parse_ledger(file_path: str) -> dict:
    sessions = {}
    current_session = None
    current_section = None
    if not os.path.exists(file_path):
        return sessions
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("## 记录时间/会话:"):
                current_session = line.replace("## 记录时间/会话:", "").strip()
                sessions.setdefault(current_session, {"facts": [], "edges": []})
                current_section = None
            elif line.startswith("### 核心事实"):
                current_section = "facts"
            elif line.startswith("### 实体关系图谱"):
                current_section = "edges"
            elif line.startswith("- ") and current_session:
                content = line[2:].strip()
                if current_section == "facts":
                    sessions[current_session]["facts"].append(content)
                elif current_section == "edges":
                    m = re.match(r"\[(.*?)\]\s*--\((.*?)\)-->\s*\[(.*?)\]", content)
                    if m:
                        sessions[current_session]["edges"].append({
                            "src": m.group(1).strip(),
                            "type": m.group(2).strip(),
                            "tgt": m.group(3).strip()
                        })
    return sessions

class LedgerSync:
    def __init__(self, config):
        self.cfg = config
        embed_cfg = config.get("embedding", {})
        model_path = embed_cfg.get("model_path", "")
        self.pg_pool = None
        self.neo4j = None
        
        if not model_path:
            raise ValueError("Embedding model_path is required.")
        try:
            self.emb_model = SentenceTransformer(model_path)
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise

    async def connect(self):
        try:
            pg_cfg = self.cfg.get("postgres", {})
            pg_dsn = pg_cfg.get("dsn") or f"postgresql://{pg_cfg.get('user', 'postgres')}:{pg_cfg.get('password', 'password')}@{pg_cfg.get('host', 'localhost')}:{pg_cfg.get('port', 5432)}/{pg_cfg.get('database', 'postgres')}"
            self.pg_pool = await asyncpg.create_pool(pg_dsn)
        except Exception as e:
            logger.error(f"PostgreSQL connection failed: {e}")
            raise

        try:
            neo4j_cfg = self.cfg.get("neo4j", {})
            self.neo4j = AsyncGraphDatabase.driver(
                neo4j_cfg.get("uri", "bolt://localhost:7687"),
                auth=(neo4j_cfg.get("user", "neo4j"), neo4j_cfg.get("password", "root"))
            )
        except Exception as e:
            logger.error(f"Neo4j connection failed: {e}")
            raise

    async def close(self):
        if self.pg_pool: await self.pg_pool.close()
        if self.neo4j: await self.neo4j.close()

    async def sync_session(self, session_id: str, data: dict):
        if self.pg_pool:
            try:
                async with self.pg_pool.acquire() as conn:
                    await register_vector(conn)
                    await conn.execute("DELETE FROM episodic_memory WHERE id LIKE $1", f"{session_id}_%")
                    facts = data.get("facts", [])
                    if facts:
                        embeddings = await asyncio.to_thread(self.emb_model.encode, facts)
                        embeddings = embeddings.tolist()
                        records = [(f"{session_id}_{i}", text, embeddings[i]) for i, text in enumerate(facts)]
                        await conn.executemany(
                            "INSERT INTO episodic_memory (id, text, embedding) VALUES ($1, $2, $3)",
                            records
                        )
            except Exception as e:
                logger.error(f"PG Sync Error for session {session_id}: {e}")

        if self.neo4j:
            try:
                edges = data.get("edges", [])
                async with self.neo4j.session() as session:
                    await session.run("MATCH ()-[r {session_id: $sid}]->() DELETE r", sid=session_id) 
                    if edges:
                        for edge in edges:
                            clean_type = re.sub(r'[^\w]', '', edge['type']) or "UNKNOWN_REL"
                            await session.run(
                                f"MERGE (a {{id: $src}}) MERGE (b {{id: $tgt}}) MERGE (a)-[r:`{clean_type}`]->(b) SET r.session_id = $sid",
                                src=edge['src'], tgt=edge['tgt'], sid=session_id
                            )
            except Exception as e:
                logger.error(f"Neo4j Sync Error for session {session_id}: {e}")

class LedgerHandler(FileSystemEventHandler):
    def __init__(self, loop, sync_engine, file_path):
        self.loop = loop
        self.sync_engine = sync_engine
        self.file_path = os.path.abspath(file_path)
        self.last_modified = time.time()
        self.sync_lock = asyncio.Lock()

    def on_modified(self, event):
        if os.path.abspath(event.src_path) == self.file_path:
            current_time = time.time()
            if current_time - self.last_modified > 2.0:
                self.last_modified = current_time
                logger.info(f"Detected changes in {os.path.basename(self.file_path)}. Syncing...")
                asyncio.run_coroutine_threadsafe(self.process_sync(), self.loop)

    async def process_sync(self):
        if self.sync_lock.locked():
            logger.warning("Sync is already in progress. Skipping this trigger.")
            return
        async with self.sync_lock:
            sessions = parse_ledger(self.file_path)
            for sid, data in sessions.items():
                await self.sync_engine.sync_session(sid, data)
            logger.info("Ledger sync completed successfully.")

async def main():
    try:
        config = load_config("model.toml")
    except Exception as e:
        logger.error(f"Config error: {e}")
        return

    sync_engine = LedgerSync(config)
    
    try:
        await sync_engine.connect()
    except Exception:
        logger.error("Failed to connect to databases. Exiting.")
        return

    ledger_path = "MEMORY_LEDGER.md"
    if not os.path.exists(ledger_path):
        with open(ledger_path, "w", encoding="utf-8") as f:
            f.write("")

    loop = asyncio.get_running_loop()
    event_handler = LedgerHandler(loop, sync_engine, ledger_path)
    observer = Observer()
    observer.schedule(event_handler, path=os.path.dirname(os.path.abspath(ledger_path)), recursive=False)
    observer.start()
    
    logger.info(f"Started watching {ledger_path} for hot-reloads...")
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping watcher...")
        observer.stop()
    finally:
        observer.join()
        await sync_engine.close()

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
