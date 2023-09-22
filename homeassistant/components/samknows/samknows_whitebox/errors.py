class RefreshFailed(Exception):
    """Raised when refreshing an auth token has failed."""


class CouldNotAuthenticate(Exception):
    """Raised when authentication has failed."""


class RequestFailed(Exception):
    """Raised when a request returns a non-OK error code."""
