"""Antidote setup wizard — branded interactive configuration."""

import json
import os
import shutil
import sys
from pathlib import Path

import questionary
from questionary import Style as QStyle
from rich.console import Console
from rich.panel import Panel
from rich.table import Table, box

ANTIDOTE_DIR = Path.home() / ".antidote"
CONFIG_PATH = ANTIDOTE_DIR / "config.json"
WORKSPACE_DIR = ANTIDOTE_DIR / "workspace"

console = Console()

QS = QStyle([
    ("qmark", "fg:#00D26A bold"),
    ("question", "bold"),
    ("answer", "fg:#00D26A bold"),
    ("pointer", "fg:#00D26A bold"),
    ("highlighted", "fg:#00D26A bold"),
    ("selected", "fg:#00D26A"),
])

MODELS = [
    ("anthropic/claude-sonnet-4-20250514", "Claude Sonnet 4", "Recommended", "Fast, smart"),
    ("anthropic/claude-haiku-4-5-20251001", "Claude Haiku 4.5", "Cheaper", "Fast, light"),
    ("openai/gpt-4.1-mini", "GPT-4.1 Mini", "Cheapest smart", "Good value"),
    ("deepseek/deepseek-r1", "DeepSeek R1", "Best reasoning", "Slow, deep"),
]


def _step(number: int, title: str):
    console.print(f"\n[cyan]{'─' * 50}[/cyan]")
    console.print(f"  [cyan]Step {number}[/cyan] — [bold]{title}[/bold]")
    console.print(f"[cyan]{'─' * 50}[/cyan]\n")


def _success(msg: str):
    console.print(f"  [green]✓[/green] {msg}")


def _warn(msg: str):
    console.print(f"  [yellow]⚠[/yellow] {msg}")


def main():
    console.print(Panel(
        "[bold green]Welcome to Antidote Setup[/bold green]\n"
        "[dim]Let's configure your personal AI assistant.[/dim]",
        border_style="green",
    ))

    # Check Python version
    if sys.version_info < (3, 11):
        console.print("[red]Python 3.11+ is required.[/red]")
        sys.exit(1)
    _success(f"Python {sys.version_info.major}.{sys.version_info.minor}")

    # Check existing installation
    if ANTIDOTE_DIR.exists():
        action = questionary.select(
            "Existing installation found. What would you like to do?",
            choices=["Reconfigure", "Fresh start (delete everything)"],
            style=QS,
        ).ask()
        if action and "Fresh" in action:
            shutil.rmtree(ANTIDOTE_DIR)
            _success("Cleaned previous installation")

    # Create directories
    ANTIDOTE_DIR.mkdir(parents=True, exist_ok=True)
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Telegram Bot Token
    _step(1, "Telegram Bot Token")
    console.print("  [cyan]1.[/cyan] Open Telegram and search for [bold]@BotFather[/bold]")
    console.print("  [cyan]2.[/cyan] Send [bold]/newbot[/bold] and follow the prompts")
    console.print("  [cyan]3.[/cyan] Copy the bot token and paste it below\n")

    telegram_token = questionary.password(
        "Telegram Bot Token:", style=QS
    ).ask()

    if telegram_token:
        # Validate token
        try:
            import urllib.request
            url = f"https://api.telegram.org/bot{telegram_token}/getMe"
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read())
                if data.get("ok"):
                    bot_name = data["result"].get("first_name", "Bot")
                    _success(f"Token valid — bot name: {bot_name}")
                else:
                    _warn("Token may be invalid, but continuing...")
        except Exception:
            _warn("Could not validate token (no internet?), saving anyway...")

        # Save to secrets
        from antidote.security.secrets import SecretStore
        store = SecretStore()
        store.save_secret("TELEGRAM_BOT_TOKEN", telegram_token)
        _success("Token encrypted and saved")
    else:
        _warn("Skipped — you can set TELEGRAM_BOT_TOKEN env var later")

    # Step 2: OpenRouter API Key
    _step(2, "OpenRouter API Key")
    console.print("  [cyan]1.[/cyan] Go to [bold]openrouter.ai/keys[/bold]")
    console.print("  [cyan]2.[/cyan] Create a new key and paste it below\n")

    openrouter_key = questionary.password(
        "OpenRouter API Key:", style=QS
    ).ask()

    if openrouter_key:
        from antidote.security.secrets import SecretStore
        store = SecretStore()
        store.save_secret("OPENROUTER_API_KEY", openrouter_key)
        _success("API key encrypted and saved")
    else:
        _warn("Skipped — you can set OPENROUTER_API_KEY env var later")

    # Step 3: Default Model
    _step(3, "Default AI Model")

    table = Table(box=box.ROUNDED, border_style="green")
    table.add_column("Model", style="bold")
    table.add_column("Speed", style="cyan")
    table.add_column("Notes", style="dim")
    for model_id, name, speed, notes in MODELS:
        table.add_row(name, speed, notes)
    console.print(table)

    model_choices = [f"{name} ({model_id})" for model_id, name, _, _ in MODELS]
    model_choices.append("Custom (type model ID)")

    model_answer = questionary.select(
        "Choose your default model:", choices=model_choices, style=QS
    ).ask()

    selected_model = MODELS[0][0]  # default
    if model_answer:
        if "Custom" in model_answer:
            selected_model = questionary.text("Model ID:", style=QS).ask() or selected_model
        else:
            idx = model_choices.index(model_answer)
            if idx < len(MODELS):
                selected_model = MODELS[idx][0]

    _success(f"Model: {selected_model}")

    # Step 4: AI Name
    _step(4, "Personalization")

    ai_name = questionary.text(
        "What should your AI be called?",
        default="Antidote",
        style=QS,
    ).ask() or "Antidote"

    _success(f"Name: {ai_name}")

    # Step 5: Write config
    _step(5, "Saving Configuration")

    config = {
        "name": ai_name,
        "version": "0.1.0",
        "providers": {
            "default": "openrouter",
            "openrouter": {"model": selected_model},
            "ollama": {"model": "llama3.2", "base_url": "http://localhost:11434"},
        },
        "channels": {"telegram": {"enabled": True}},
        "memory": {
            "db_path": str(ANTIDOTE_DIR / "memory.db"),
            "max_context_memories": 10,
        },
        "workspace": str(WORKSPACE_DIR),
        "identity": {
            "soul": "workspace/SOUL.md",
            "agents": "workspace/AGENTS.md",
            "user": "workspace/USER.md",
        },
        "safety": {
            "blocked_commands": ["rm -rf /", "mkfs", "dd if=", "shutdown", "reboot", "> /dev/sd"],
            "max_command_timeout": 60,
        },
    }

    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)
    _success("config.json written")

    # Copy workspace identity files
    project_workspace = Path(__file__).parent / "workspace"
    for md_file in ["SOUL.md", "AGENTS.md", "USER.md", "MEMORY.md"]:
        src = project_workspace / md_file
        dst = WORKSPACE_DIR / md_file
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)
    _success("Identity files copied to workspace")

    # Done
    console.print()
    console.print(Panel(
        f"[bold green]{ai_name} is configured![/bold green]\n\n"
        "Run [bold]antidote[/bold] to start the bot.\n"
        "Run [bold]antidote setup[/bold] to reconfigure.",
        border_style="green",
        title="[green]Done[/green]",
    ))


if __name__ == "__main__":
    main()
