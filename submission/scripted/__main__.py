"""Plumbing test harness (organiser, Yukon dev): a fixed script with no model calls. It sets up drink, food and
housing, then advances to the horizon. Its only purpose is to score differently from the baseline on the fake stack
so the promotion path can be exercised."""
from dfbench_client import ActionLimit, GameClient, GameOver, HandsOff, load_task


def main():
    t = load_task()
    g = GameClient(t.game_url)
    g.wait_ready()
    try:
        for tool, args in [("build_workshop", {"type": "Still"}), ("build_workshop", {"type": "Craftsdwarfs"}),
                           ("add_order", {"recipe": "brew_drink", "amount": 20}),
                           ("build_farm", {}), ("build_farm", {}),
                           ("place_furniture", {"item": "bed", "n": 20}),
                           ("place_furniture", {"item": "chair", "n": 20})]:
            g.act(tool, args)
        while True:
            g.advance(28)
    except (GameOver, HandsOff, ActionLimit):
        pass
    try:
        while True:
            g.advance(28)
    except GameOver:
        pass


if __name__ == "__main__":
    main()
