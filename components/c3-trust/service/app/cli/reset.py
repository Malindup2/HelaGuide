"""Start from a clean state: recreate C3's tables, load the reporters, register the mock facts.

    python -m app.cli.reset              (PostgreSQL from docker-compose.c3.yml)
    python -m app.cli.reset --sqlite     (no Docker)
"""
import argparse

from app.cli._common import add_common_args, build, mask_url, utf8


def main(argv=None) -> None:
    utf8()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_args(ap)
    args = ap.parse_args(argv)
    pipe = build(args, reset=True)
    n_rep = pipe.load_reporters()
    results = pipe.sync_facts()
    print(f"database : {mask_url(pipe.s.database_url)}")
    print(f"reset    : tables recreated, {n_rep} reporters loaded, {sum(r.created for r in results)} facts registered")
    print("each fact version now has a confidence record owned by C3 (initial confidence "
          f"{pipe.s.c_base:.0%})")


if __name__ == "__main__":
    main()
