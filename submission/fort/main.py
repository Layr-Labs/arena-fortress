"""Entrypoint: read DFBENCH_TASK, build the clients, run the harness."""
import os

from dfbench_client import GameAPIError, GameClient, ModelClient, load_task

from .harness import Harness, log


def main():
    task = load_task()
    game = GameClient(task.game_url)
    model = ModelClient(task.model_base_url, task.model_name, task.api_key, prices=task.prices)
    log("start", task=repr(task), model=task.model_name)
    h = Harness(task, game, model)
    if os.environ.get("FORT_NO_ADVISOR") == "1":
        h.no_advisor = True
    try:
        h.run()
    except GameAPIError as e:
        log("game_error", error=str(e)[:300])
        return 1
    return 0
