"""Entry point — CLI router + wires everything together."""

import asyncio
import logging
import random
import signal
import sys

from rich.console import Console
from rich.panel import Panel

BANNER = r"""
    _   _  _ _____ ___ ___  ___ _____ ___
   /_\ | \| |_   _|_ _|   \/ _ \_   _| __|
  / _ \| .` | | |  | || |) | (_) || | | _|
 /_/ \_\_|\_| |_| |___|___/ \___/ |_| |___|
"""

TAGLINES = [
    "The antidote to bloated AI frameworks.",
    "Less framework. More you.",
    "Your AI. Your Mac. Your rules.",
    "One Telegram message away from useful.",
    "Built from scratch. Runs like it means it.",
    "No Docker. No cloud. No nonsense.",
    "The AI assistant that doesn't need a DevOps team.",
    "Bloated frameworks hate this one trick.",
    "Personal AI without the personal data harvesting.",
    "Because your AI shouldn't need Kubernetes.",
    "Lightweight enough to run on a philosophy.",
    "All the power. None of the YAML.",
    "Your terminal just got an upgrade.",
    "AI that remembers you. Runs on your Mac. Talks on Telegram.",
    "Encrypted at rest. Opinionated in conversation.",
    "Fewer dependencies than your morning coffee order.",
    "Small enough to read. Powerful enough to matter.",
]

console = Console()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)


def show_banner():
    tagline = random.choice(TAGLINES)
    console.print(Panel(
        f"[bold green]{BANNER}[/bold green]\n  [dim]{tagline}[/dim]",
        border_style="green",
    ))


async def run_bot():
    """Initialize all components and start the bot."""
    from antidote.config import Config
    from antidote.providers import get_provider
    from antidote.memory.store import MemoryStore
    from antidote.channels.telegram import TelegramChannel
    from antidote.agent.loop import AgentLoop
    from antidote.agent.context import ContextBuilder
    from antidote.tools.registry import ToolRegistry
    from antidote.tools.filesystem import ReadFileTool, WriteFileTool, ListDirTool
    from antidote.tools.shell import RunCommandTool

    config = Config()

    # Initialize components
    provider = get_provider()
    memory = MemoryStore(config.get("memory", "db_path", default="~/.antidote/memory.db"))
    await memory.initialize()

    # Register tools
    tools = ToolRegistry()
    tools.register(ReadFileTool(config))
    tools.register(WriteFileTool(config))
    tools.register(ListDirTool(config))
    tools.register(RunCommandTool(config))

    # Build agent
    context = ContextBuilder(config, memory, tools)
    agent = AgentLoop(provider, context, memory, tools)

    # Start Telegram
    telegram = TelegramChannel(config)

    # Graceful shutdown
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig, lambda: asyncio.create_task(_shutdown(telegram, memory))
        )

    console.print("[green]Antidote is running.[/green] Send a message on Telegram.")
    await telegram.start(on_message=agent.process_message)


async def _shutdown(channel, memory):
    console.print("\n[yellow]Shutting down gracefully...[/yellow]")
    await channel.stop()
    await memory.close()
    asyncio.get_event_loop().stop()


def _run_wizard():
    """Import and run the setup wizard."""
    import importlib.util
    from pathlib import Path

    wizard_path = Path(__file__).parent.parent / "wizard.py"
    if not wizard_path.exists():
        console.print("[red]wizard.py not found.[/red]")
        sys.exit(1)

    spec = importlib.util.spec_from_file_location("wizard", wizard_path)
    wizard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wizard)
    wizard.main()


def cli():
    """CLI entry point."""
    show_banner()

    args = sys.argv[1:]

    if args and args[0] == "setup":
        _run_wizard()
        return

    # Auto-detect: if no config, run wizard first
    from antidote.config import Config
    if not Config.exists():
        console.print("[yellow]No configuration found. Starting setup wizard...[/yellow]\n")
        _run_wizard()
        console.print()
        answer = console.input("[green]Start the bot now? (y/n): [/green]")
        if answer.lower() != "y":
            return

    try:
        asyncio.run(run_bot())
    except ValueError as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        console.print("Run [green]antidote setup[/green] to reconfigure.")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[dim]Goodbye.[/dim]")


if __name__ == "__main__":
    cli()
