"""penelope web — start the Penelope backend and open the browser."""
from __future__ import annotations

import shutil
import socket
import subprocess
import time
import webbrowser

import click

from cli.render import print_error, print_info, print_success


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return True
    return False


def _wait_ready(url: str, timeout: int = 30) -> bool:
    import httpx
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            httpx.get(url, timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


@click.command()
@click.option("--port", default=7000, show_default=True, help="Porta do backend.")
@click.option("--no-browser", is_flag=True, help="Não abrir o browser automaticamente.")
def web(port: int, no_browser: bool) -> None:
    """Inicia o servidor Penelope e abre o browser.

    Se o servidor já estiver a correr, abre apenas o browser.
    Ctrl+C para parar.
    """
    from pathlib import Path

    project_root = Path(__file__).resolve().parent.parent.parent
    url = f"http://127.0.0.1:{port}"

    if _port_in_use(port):
        print_info("Backend", f"já está a correr na porta {port}")
        if not no_browser:
            webbrowser.open(url)
            print_success(f"Aberto no browser: {url}")
        return

    uv_exe = shutil.which("uv")
    if not uv_exe:
        print_error("'uv' não encontrado no PATH. Corre 'pip install uv' ou usa o setup.cmd.")
        return

    print_info("Backend", f"a iniciar na porta {port}…")

    proc = subprocess.Popen(
        [uv_exe, "run", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(project_root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if not _wait_ready(f"{url}/api/health", timeout=30):
        proc.terminate()
        print_error("Backend demorou demasiado a arrancar. Verifica os logs.")
        return

    print_success(f"Penelope pronto em {url}")
    if not no_browser:
        webbrowser.open(url)

    print_info("", "Ctrl+C para parar")
    try:
        while proc.poll() is None:
            time.sleep(1)
        print_error("O servidor parou inesperadamente.")
    except KeyboardInterrupt:
        pass
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        print_info("Backend", "parado")
