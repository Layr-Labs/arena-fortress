"""Typed errors for the game API and the model gateway."""


class DfbenchError(Exception):
    """Base class for everything this client raises."""


# --- game API -----------------------------------------------------------------------------------------------------
class GameAPIError(DfbenchError):
    """The game server answered with an HTTP error, or with a body that isn't JSON.

    `status` is the HTTP status (None for a bad body), `body` the parsed JSON body when there was one,
    `error_code` the API's error code when the body had one."""

    def __init__(self, msg, status=None, body=None):
        super().__init__(msg)
        self.status = status
        self.body = body if isinstance(body, dict) else {}
        self.error_code = self.body.get("error_code")


class GameUnavailable(GameAPIError):
    """The game server could not be reached after the client's retries (connection errors only)."""


class ActionRejected(GameAPIError):
    """Base for the three rule rejections the loop must handle itself (contract §3/§4)."""


class ActionLimit(ActionRejected):
    """`action_limit`: K actions were used today; only advance_days is accepted until the day changes."""


class HandsOff(ActionRejected):
    """`hands_off`: the task's hands-off window has begun; actions are rejected and the server runs the rest."""


class GameOver(ActionRejected):
    """`game_over`: the horizon was reached, the fort was lost, or the wall cap was hit."""


RULE_ERRORS = {"action_limit": ActionLimit, "hands_off": HandsOff, "game_over": GameOver}


# --- model gateway --------------------------------------------------------------------------------------------------
class ModelError(DfbenchError):
    """The gateway (or the provider behind it) failed the call. `status` is the HTTP status, if any."""

    def __init__(self, msg, status=None, body=None):
        super().__init__(msg)
        self.status = status
        self.body = body


class BudgetExhausted(ModelError):
    """The gateway refused the call because the game's credits are used up. Retrying can't help: the game runs on
    unmanaged to the horizon (contract §2), so a harness should stop calling the model (or exit)."""


class ContextTooLong(ModelError):
    """The prompt is over the model's context window. Retrying the same prompt can't succeed: shorten it."""
