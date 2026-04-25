# ============================================================
# Agent Core Main Entry Point
# ============================================================
# Entry point for running the autonomous agent.
# Supports command-line arguments and demo mode.
#
# Usage:
#   python -m app.main --goal "Your goal here"
#   python -m app.main --mode demo
#   python -m app.main --goal "..." --max-steps 100
#
# Console Output:
#   - Configuration display
#   - Agent execution trace
#   - Final summary
# ============================================================

import sys
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agent.agent import create_agent
from app.core.config import get_config, Config


def parse_args():
    """
    Parse command-line arguments.

    Returns:
        Namespace: Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Autonomous Agent Core for Paper Reproduction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m app.main --goal "Reproduce paper 'Attention Is All You Need'"
  python -m app.main --mode demo
  python -m app.main --goal "Run experiment" --max-steps 100
        """
    )

    parser.add_argument(
        "--goal",
        type=str,
        default=None,
        help="The goal for the agent to accomplish",
    )

    parser.add_argument(
        "--mode",
        type=str,
        choices=["agent", "demo"],
        default="demo",
        help="Run mode: 'agent' for real execution, 'demo' for demonstration",
    )

    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Maximum steps before termination",
    )

    parser.add_argument(
        "--config",
        action="store_true",
        help="Print configuration and exit",
    )

    return parser.parse_args()


def run_demo_mode():
    """
    Run in demonstration mode with a sample goal.
    """
    print("\n" + "=" * 60)
    print("[DEMO] DEMO MODE")
    print("=" * 60)
    print("\nRunning with a sample paper reproduction goal...\n")

    # Demo goal
    demo_goal = "复现论文：Minimal learning machine for multi-label learning"

    # Override max steps for demo
    config = get_config()
    original_max = config.agent.max_steps
    config.agent.max_steps = 10  # Limit steps for demo

    try:
        agent = create_agent()
        context = agent.run(demo_goal)
    finally:
        config.agent.max_steps = original_max


def run_agent_mode(goal: str, max_steps: int = None):
    """
    Run in agent mode with user-specified goal.

    Args:
        goal: The goal to accomplish
        max_steps: Optional override for max steps
    """
    # Load config and apply overrides
    config = get_config()
    if max_steps:
        config.agent.max_steps = max_steps

    # Create and run agent
    agent = create_agent()
    context = agent.run(goal)

    # Return exit code based on status
    if context.status == "completed":
        sys.exit(0)
    else:
        sys.exit(1)


def main():
    """Main entry point."""
    args = parse_args()

    # Load and display configuration
    config = get_config()
    config.print_config()

    # Handle --config flag
    if args.config:
        print("Configuration displayed above. Exiting.")
        sys.exit(0)

    # Run based on mode
    if args.mode == "demo":
        run_demo_mode()
    elif args.mode == "agent":
        if not args.goal:
            print("[X] Error: --goal is required in agent mode")
            print("   Use --goal 'your goal here' or --mode demo")
            sys.exit(1)
        run_agent_mode(args.goal, args.max_steps)


if __name__ == "__main__":
    main()
