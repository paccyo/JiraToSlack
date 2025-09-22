import argparse


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Local prototype CLI for future Slack Bot integration"
    )
    parser.add_argument(
        "--name",
        default="World",
        help="Name to greet (default: World)",
    )
    args = parser.parse_args()

    print(f"Hello, {args.name}! (prototype)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
