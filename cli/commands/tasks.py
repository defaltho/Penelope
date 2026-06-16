"""penelope task — manage tasks."""
from __future__ import annotations

import click

from cli.client import PenelopeClient
from cli.render import print_error, print_success, print_table


@click.group()
def task() -> None:
    """Gerir tarefas."""


@task.command("list")
def list_tasks() -> None:
    """Lista tarefas."""
    client = PenelopeClient()
    try:
        tasks = client.list_tasks()
    except Exception as e:
        print_error(str(e))
        return

    if not tasks:
        click.echo("Sem tarefas.")
        return

    rows = [
        [str(t["id"]), "done" if t["done"] else "    ", t["text"][:60]]
        for t in tasks
    ]
    print_table("Tarefas", ["ID", "Estado", "Texto"], rows)


@task.command()
@click.argument("text")
def add(text: str) -> None:
    """Adiciona uma tarefa."""
    client = PenelopeClient()
    try:
        result = client.create_task(text)
        print_success(f"Tarefa #{result.get('id', '?')} criada.")
    except Exception as e:
        print_error(str(e))


@task.command()
@click.argument("task_id", type=int)
def done(task_id: int) -> None:
    """Marca uma tarefa como concluída."""
    client = PenelopeClient()
    try:
        client.update_task(task_id, done=True)
        print_success(f"Tarefa #{task_id} concluída.")
    except Exception as e:
        print_error(str(e))


@task.command()
@click.argument("task_id", type=int)
def rm(task_id: int) -> None:
    """Apaga uma tarefa."""
    client = PenelopeClient()
    try:
        client.delete_task(task_id)
        print_success(f"Tarefa #{task_id} apagada.")
    except Exception as e:
        print_error(str(e))
