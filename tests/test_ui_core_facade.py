from ui.core import MenuChoice, UI


class StubIO:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.logged = []
        self.prompts = []
        self.clears = 0
        self.waits = []

    def log(self, message: str, *, level: str = "info") -> None:
        self.logged.append((message, level))

    def prompt(self, prompt: str, *, options=None):
        self.prompts.append((prompt, options))
        if not self.responses:
            return ""
        return self.responses.pop(0)

    def clear(self) -> None:
        self.clears += 1

    def wait(self, seconds: float) -> None:
        self.waits.append(seconds)


def test_ui_log_and_prompt_delegation():
    io = StubIO(responses=["ok"])
    layer = UI(io, theme="clean")

    layer.print("hello world", level="story")
    answer = layer.prompt("?", options=["ok", "no"])
    layer.wait(0.1)
    layer.clear()

    assert ("hello world", "story") in io.logged
    assert answer == "ok"
    assert io.prompts[-1][0] == "?"
    assert io.clears == 1
    assert io.waits[-1] == 0.1


def test_menu_respects_disabled_options_and_defaults():
    io = StubIO(responses=["2", ""])
    layer = UI(io)
    result = layer.menu(
        "Pick",
        [
            MenuChoice("1", "Enabled", value="ENABLED"),
            MenuChoice("2", "Locked", value="LOCKED", enabled=False),
            MenuChoice("", "Default Next", value="DEFAULT", hint="Enter"),
        ],
        prompt_text="> ",
        clear_first=False,
    )
    assert result == "DEFAULT"
    assert any("locked" in str(msg).lower() for msg, _ in io.logged)
