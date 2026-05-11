from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) > 1:
        from tubby.cli import main as cli_main

        return cli_main()

    try:
        from tubby.gui import main as gui_main
    except ModuleNotFoundError as exc:
        if exc.name == "customtkinter":
            print(
                "Desktop dependencies are not installed. Run `pip install -r requirements.txt`.",
                file=sys.stderr,
            )
            return 1
        raise

    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main())
