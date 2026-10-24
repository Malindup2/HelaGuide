"""Errors shared by the live application, content preparation and the historical V1 stores."""


class StateStoreError(RuntimeError):
    """Persistence is unavailable; the application must fail closed."""
