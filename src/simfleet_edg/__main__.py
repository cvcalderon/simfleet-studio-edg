"""Minimal shell entry point; future CLI is not implemented yet."""

from argparse import ArgumentParser

from simfleet_edg import __version__


def main() -> None:
    parser = ArgumentParser(description="SimFleet-EDG scaffold (not a generator yet)")
    parser.add_argument("--version", action="version", version=f"simfleet-edg {__version__}")
    parser.parse_args()
    parser.print_help()


if __name__ == "__main__":
    main()
