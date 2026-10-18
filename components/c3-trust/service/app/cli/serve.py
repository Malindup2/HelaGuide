"""
Start the HelaGuide citizen console for component 3 (the UI demo).

    python -m app.cli.serve                  PostgreSQL from docker-compose.c3.yml, then open the page
    python -m app.cli.serve --sqlite         no Docker needed (in-memory database)
    python -m app.cli.serve --port 8014      another port, if 8013 is taken
    python -m app.cli.serve --no-browser     do not open the browser
    python -m app.cli.serve --keep-data      do not reset the database at start (continue where you stopped)

The page is http://localhost:8013/ui . It runs entirely on its own: it does not call C1, C2, C4 or the gateway, and it
uses port 8013 so it can run next to the team's stack (which uses 8000-8004). Stop it with Ctrl+C.
"""
import argparse
import os
import threading
import webbrowser

from app.cli._common import add_common_args, banner, build, mask_url, utf8


def main(argv=None) -> None:
    utf8()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_args(ap)
    ap.add_argument("--port", type=int, default=8013)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--keep-data", action="store_true", help="do not reset the database at start")
    args = ap.parse_args(argv)

    os.environ["STUB_MODE"] = "false"            # the console needs the real logic (set before the app is imported)
    pipe = build(args, reset=not args.keep_data)
    if not pipe.repo.list_current_facts():
        pipe.load_reporters()
        pipe.sync_facts()
    elif not args.keep_data:
        pipe.load_reporters()
        pipe.sync_facts()
    pipe.embedder.encode(["warm up"])             # load the model now, not on the first click

    from app.core.pipeline import set_pipeline
    set_pipeline(pipe)
    import uvicorn
    from app.main import app

    url = f"http://localhost:{args.port}/ui"
    banner("HelaGuide citizen console · component 3")
    print(f"page     : {url}")
    print(f"database : {mask_url(pipe.s.database_url)}   model: {pipe.embedder.name}")
    print("stop     : Ctrl+C\n")
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    except OSError as exc:
        print(f"\nCould not start on port {args.port}: {exc}\nTry another port:  python -m app.cli.serve --port 8014")


if __name__ == "__main__":
    main()
