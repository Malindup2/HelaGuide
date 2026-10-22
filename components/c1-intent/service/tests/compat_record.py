"""
Records the golden responses for test_compat_context_v2.py by running tests/compat_cases.py against another
checkout of the C1 service (the base branch). Not a test; run it only to re-record, from service/:

    git worktree add <scratch>\\ctxv2 c1/context-v2
    python tests/compat_record.py --service <scratch>\\ctxv2\\components\\c1-intent\\service
    git worktree remove <scratch>\\ctxv2

The app and tests/conftest.py FakeEngine are imported from --service; compat_cases.py from this folder.
"""
import argparse
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "fixtures" / "compat_context_v2.json"


def _load_cases():
    spec = importlib.util.spec_from_file_location("compat_cases", HERE / "compat_cases.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--service", required=True, help="components/c1-intent/service of the base branch checkout")
    ap.add_argument("--base", default="c1/context-v2", help="name of the base branch, stored in the file")
    args = ap.parse_args()
    service = Path(args.service).resolve()
    sys.path.insert(0, str(service))
    os.chdir(service)
    cases = _load_cases()

    from fastapi.testclient import TestClient
    from app.core import pipeline
    from app.core.sessions import SessionStore
    from app.main import app
    from tests.conftest import FakeEngine
    assert Path(pipeline.__file__).resolve().is_relative_to(service), "imported the wrong app"

    def setattr_(obj, name, value):
        setattr(obj, name, value)

    def delenv(name):
        os.environ.pop(name, None)

    client = TestClient(app)
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["STUB_MODE"] = "true"
        stub = cases.run_stub(client)
        cases.install_fake_engine(pipeline, SessionStore, FakeEngine, Path(tmp), setattr_, os.environ.__setitem__,
                                  delenv)
        responses = cases.run(client)
    golden = {"base": args.base, "stub": stub, "responses": responses, "openapi": cases.contract_openapi(app)}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(golden, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(responses)} responses + {len(stub)} stub responses from {service} -> {OUT}")


if __name__ == "__main__":
    main()
