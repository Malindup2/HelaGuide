# Stub

While `STUB_MODE=true`, this service answers every route with the canned samples in
[`contracts/examples/`](../../../contracts/examples/). That lets the other three
components integrate against **c3-trust** before its real logic exists.

Turn it off per service in `.env` once `app/core/` is implemented:

```bash
STUB_MODE=false
```

Keep stub behaviour working even after the real logic lands: it is what the other
components' tests run against.
