"""Camada de base de dados do Penelope: um único ficheiro SQLite com
sqlite-vec (busca vetorial) + FTS5 (busca por palavra-chave).

IMPORTANTE: requer um Python com loadable extensions ATIVADAS. O python3 do
sistema (3.9) tem-nas desativadas; usar sempre o Python 3.12 do uv.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import sqlite_vec

from config import settings


def connect(db_path: str | None = None) -> sqlite3.Connection:
    """Abre uma conexão com sqlite-vec carregado e PRAGMAs configurados."""
    path = db_path or settings.db_path
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path, check_same_thread=False)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)  # higiene: re-desativar após carregar

    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.row_factory = sqlite3.Row
    return conn


# Schema completo. embedding float[N] usa settings.embed_dim (768).
_SCHEMA = f"""
-- Conversas (para a "nova conversa" do teste de validação ser real)
CREATE TABLE IF NOT EXISTS conversations (
    id          INTEGER PRIMARY KEY,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Mensagens literais (Camada B, base)
CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id),
    role            TEXT NOT NULL CHECK (role IN ('user','assistant','system')),
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- FTS5 external-content sobre messages.content (sem duplicar texto)
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content,
    content='messages',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);

-- Triggers para manter o FTS sincronizado automaticamente
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content)
    VALUES ('delete', old.id, old.content);
END;
CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content)
    VALUES ('delete', old.id, old.content);
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;

-- Turnos (Camada B, recuperação semântica). Sync MANUAL com turn_vectors.
CREATE TABLE IF NOT EXISTS turns (
    turn_id         INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id),
    text            TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE VIRTUAL TABLE IF NOT EXISTS turn_vectors USING vec0(
    turn_id   INTEGER PRIMARY KEY,
    embedding float[{settings.embed_dim}]
);

-- Factos semânticos (Camada A, base). Sync MANUAL com fact_vectors.
CREATE TABLE IF NOT EXISTS semantic_facts (
    id          INTEGER PRIMARY KEY,
    text        TEXT NOT NULL,
    fact_type   TEXT,
    source_turn INTEGER,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    is_deleted  INTEGER NOT NULL DEFAULT 0
);
CREATE VIRTUAL TABLE IF NOT EXISTS fact_vectors USING vec0(
    fact_id   INTEGER PRIMARY KEY,
    embedding float[{settings.embed_dim}]
);

-- Skills: instruções/personas reutilizáveis. Quando enabled=1, a instrução é
-- injetada no system prompt de cada chat. Geridas no painel de Skills.
CREATE TABLE IF NOT EXISTS skills (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    instruction TEXT NOT NULL,
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Transações estruturadas (Stage 3): registo do que foi extraído/despachado.
CREATE TABLE IF NOT EXISTS transactions (
    id          INTEGER PRIMARY KEY,
    date        TEXT,
    amount      REAL,
    currency    TEXT,
    merchant    TEXT,
    category    TEXT,
    account     TEXT,
    notes       TEXT,
    dispatched  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Notas (vista Notes, leve: sem lembretes/agente).
CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT '',
    content     TEXT NOT NULL DEFAULT '',
    pinned      INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Tarefas (vista Tasks, checklist simples).
CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY,
    text        TEXT NOT NULL,
    done        INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Definições editáveis em runtime (chave/valor).
CREATE TABLE IF NOT EXISTS app_settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- Documentos (vista Documentos: tu escreves, a IA assiste).
CREATE TABLE IF NOT EXISTS documents (
    id          INTEGER PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT '',
    content     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Factos candidatos a aprovar (modo de revisão da memória autónoma).
CREATE TABLE IF NOT EXISTS pending_facts (
    id          INTEGER PRIMARY KEY,
    text        TEXT NOT NULL,
    fact_type   TEXT,
    source_turn INTEGER,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Skills candidatas a aprovar (auto-aprendizagem de procedimentos).
CREATE TABLE IF NOT EXISTS pending_skills (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    instruction TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def _migrate(conn: sqlite3.Connection) -> None:
    """Migrações idempotentes para BDs criadas antes destas colunas existirem."""
    if not _column_exists(conn, "conversations", "title"):
        conn.execute("ALTER TABLE conversations ADD COLUMN title TEXT")
    if not _column_exists(conn, "messages", "image_path"):
        conn.execute("ALTER TABLE messages ADD COLUMN image_path TEXT")
    # Metadados persistentes por mensagem do assistente (modelo + velocidade).
    if not _column_exists(conn, "messages", "model"):
        conn.execute("ALTER TABLE messages ADD COLUMN model TEXT")
    if not _column_exists(conn, "messages", "tok_per_sec"):
        conn.execute("ALTER TABLE messages ADD COLUMN tok_per_sec REAL")
    conn.commit()


def init_schema(conn: sqlite3.Connection) -> None:
    """Cria todas as tabelas/índices se não existirem e corre migrações."""
    conn.executescript(_SCHEMA)
    conn.commit()
    _migrate(conn)


def fts5_available(conn: sqlite3.Connection) -> bool:
    opts = [r[0] for r in conn.execute("PRAGMA compile_options").fetchall()]
    return any("FTS5" in o for o in opts)
