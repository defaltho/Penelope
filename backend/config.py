"""Configuração única do Penelope. Trocável por máquina via env (prefixo ASSISTANT_).

A única diferença entre o Mac (M5 Pro 24GB) e o Windows (RTX 3060 8GB) é o
ASSISTANT_CHAT_MODEL (qwen3-vl:8b vs qwen3-vl:4b). Todo o resto é idêntico.
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Raiz do projeto (penelope/), um nível acima de backend/.
_BACKEND_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ASSISTANT_", env_file=".env")

    # Ollama
    ollama_url: str = "http://127.0.0.1:11434"  # IPv4 explícito (evita localhost->::1)
    chat_model: str = "qwen3-vl:8b"          # Windows: ASSISTANT_CHAT_MODEL=qwen3-vl:4b
    extract_model: str = "qwen3-vl:8b"       # mesmo modelo para extração/consolidação
    vision_model: str = "qwen3-vl:8b"        # OCR/visão no mesmo modelo (sem troca)
    embed_model: str = "embeddinggemma"

    # Embeddings / vetores
    embed_dim: int = 768                     # validado no arranque com chamada real

    # Geração
    num_ctx: int = 8192                      # EXPLÍCITO; default do Ollama é pequeno
    chat_temperature: float = 0.7

    # Visão / OCR (Stage 2)
    vision_num_ctx: int = 8192               # encoder de visão soma 1-3GB; imagens grandes gastam tokens
    vision_max_dim: int = 1600               # redimensiona o lado maior (poupa VRAM/tokens no 3060)

    # Recuperação de memória
    top_k_facts: int = 5
    top_k_turns: int = 3
    consolidate_k: int = 5
    recent_history_turns: int = 6            # nº de mensagens literais recentes no prompt

    # Raiz do projeto (usada pelas ferramentas de ficheiro do agente, com sandbox).
    project_root: str = str(_PROJECT_ROOT)

    # Base de dados (1 ficheiro)
    db_path: str = str(_PROJECT_ROOT / "data" / "memory.db")

    # Imagens anexadas persistidas (Stage 2 / Fase 3 de gestão)
    images_dir: str = str(_PROJECT_ROOT / "data" / "images")

    # Pipeline de dispatch (Stage 3). Vazio = sem destino: regista só localmente.
    dispatch_url: str = ""

    # System prompt base
    base_system_prompt: str = (
        "És o Penelope, um assistente pessoal local-first. "
        "Respondes de forma concisa, útil e natural. "
        "Tens qualidade excecional em Inglês e Português; responde no idioma do utilizador. "
        "Usa o que sabes sobre o utilizador quando for relevante, sem o repetir desnecessariamente."
    )


settings = Settings()
