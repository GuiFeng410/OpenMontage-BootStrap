"""backlot open always prints the project URL, including spawn failures."""

from __future__ import annotations

from backlot.__main__ import _board_url, cmd_open


def test_board_url_includes_project_id():
    assert _board_url(4750, "jade-ad") == "http://127.0.0.1:4750/p/jade-ad"
    assert _board_url(4750, None) == "http://127.0.0.1:4750/"


def test_open_prints_url_when_spawn_times_out(monkeypatch, capsys):
    clock = {"t": 0}

    monkeypatch.setattr("backlot.__main__._server_alive", lambda port: False)
    monkeypatch.setattr("backlot.__main__._spawn_server", lambda port: "/tmp/server.log")
    monkeypatch.setattr("backlot.__main__.time.sleep", lambda s: clock.__setitem__("t", clock["t"] + 20))
    monkeypatch.setattr("backlot.__main__.time.time", lambda: clock["t"])
    monkeypatch.setattr("webbrowser.open", lambda url: True)

    rc = cmd_open("my-project")
    out = capsys.readouterr().out
    assert rc == 1
    assert "http://127.0.0.1:4750/p/my-project" in out
    assert "server did not come up in time" in out


def test_open_prints_url_when_already_alive(monkeypatch, capsys):
    monkeypatch.setattr("backlot.__main__._server_alive", lambda port: True)
    monkeypatch.setattr("webbrowser.open", lambda url: True)
    rc = cmd_open("alive-proj")
    out = capsys.readouterr().out
    assert rc == 0
    assert "http://127.0.0.1:4750/p/alive-proj" in out
