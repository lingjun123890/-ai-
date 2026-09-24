import sys
from game.engine import GameEngine
from game.gui import (ModeScreen, Game, run_host_multiplayer,
                      run_client, run_client_multiplayer, _mode_to_deck_scale)


def main() -> None:
    while True:
        result = ModeScreen().run()
        if result is None:
            break

        mode, data = result

        if mode == "offline":
            engine = GameEngine(["玩家A", "玩家B"], deck_scale=0.5)
            game = Game(engine)
            game.run()
        elif mode == "training":
            engine = GameEngine.create_training()
            game = Game(engine, training_mode=True)
            game.run()
        elif mode == "host_start":
            net, payload = data
            game_mode = payload.get("mode", "4p_free")
            run_host_multiplayer(net, payload["player_names"],
                                 host_player_index=0, mode=game_mode)
        elif mode == "client_start":
            net, payload = data
            run_client_multiplayer(net, payload)
        elif mode == "host":
            from game.gui import run_host
            run_host(data)
        elif mode == "client":
            run_client(data)
        else:
            break


if __name__ == "__main__":
    main()