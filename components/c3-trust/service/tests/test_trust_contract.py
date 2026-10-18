"""What C3 sends to C4 must be exactly the contract `trust` message."""
import json

from jsonschema import Draft202012Validator, FormatChecker

from helaguide_common.config import get_settings
from tests.pipeline_fixtures import ds, pipe, run, settings  # noqa: F401


def test_trust_output_is_exactly_the_contract_trust_message(pipe, ds):
    schema = json.loads((get_settings().contracts_dir / "schema" / "v1" / "trust.schema.json").read_text(encoding="utf-8"))
    v = Draft202012Validator(schema, format_checker=FormatChecker())
    for mid in ["ft-A1", "fb-A2", "ft-A6"]:
        run(pipe, ds, mid)
    for fid in ["svc:passport:fee:normal", "svc:nic:fee:one_day"]:
        payload = json.loads(pipe.exposure.contract_trust(fid).model_dump_json())
        assert not list(v.iter_errors(payload)), payload
