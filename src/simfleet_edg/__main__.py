"""Minimal package entry point for SimFleet Studio EDG."""

from argparse import ArgumentParser

from simfleet_edg import __version__


def main() -> None:
    parser = ArgumentParser(description="SimFleet Studio EDG scientific reproducibility core")
    parser.add_argument(
        "--version",
        action="version",
        version=f"simfleet-studio-edg {__version__}",
    )
    parser.parse_args()
    parser.print_help()


if __name__ == "__main__":
    main()
