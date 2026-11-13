"""dfbench_client: a small stdlib client for the DF harness challenge (game API v0, docs/GAME-API.md).

    from dfbench_client import load_task, GameClient, ModelClient
    t = load_task()                                       # DFBENCH_TASK
    game = GameClient(t.game_url)
    model = ModelClient(t.model_base_url, t.model_name, t.api_key)

See game.py (task / observe / act / query / events, typed rule errors), model.py (OpenAI-compatible chat through the
gateway, retries, usage and cost) and task.py (DFBENCH_TASK).
"""
from .errors import (ActionLimit, ActionRejected, BudgetExhausted, ContextTooLong, DfbenchError, GameAPIError,
                     GameOver, GameUnavailable, HandsOff, ModelError)
from .game import GameClient
from .model import ModelClient
from .task import Task, load_task

__all__ = ["ActionLimit", "ActionRejected", "BudgetExhausted", "ContextTooLong", "DfbenchError", "GameAPIError",
           "GameOver", "GameUnavailable", "HandsOff", "ModelError", "GameClient", "ModelClient", "Task", "load_task"]
__version__ = "0.1.0"

from .admission import GameClient
