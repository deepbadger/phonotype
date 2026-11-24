from datetime import datetime, timedelta


def test_add_load_search_delete(isolate_xdg_dirs):
    from phonotype.core import history as H
    t0 = datetime(2026, 11, 24, 10, 0, 0)
    H.add("Запусти Kubernetes", "запусти кубернетес", cfg_data={}, model="m.bin", prompt="default", now=t0)
    H.add("Второй текст", "Второй текст", cfg_data={}, now=t0 + timedelta(minutes=1))
    assert H.add("  ", cfg_data={}) is None                       # nothing to record

    entries = H.load()
    assert [e["text"] for e in entries] == ["Второй текст", "Запусти Kubernetes"]   # newest first
    assert "raw" not in entries[0]                                # same as typed: not stored twice
    assert entries[1]["raw"] == "запусти кубернетес" and entries[1]["prompt"] == "default"
    assert H.last_text() == "Второй текст"
    assert oct(H.history_path().stat().st_mode & 0o777) == "0o600"

    assert [e["text"] for e in H.search(entries, "КУБЕРНЕТЕС")] == ["Запусти Kubernetes"]  # matches raw too
    assert H.search(entries, "текст запусти") == []               # every word must match
    assert len(H.search(entries, "")) == 2

    H.delete(entries[0]["ts"])
    assert [e["text"] for e in H.load()] == ["Запусти Kubernetes"]
    H.clear()
    assert H.load() == [] and H.last_text() == ""


def test_retention_and_switch(isolate_xdg_dirs):
    from phonotype.core import history as H
    now = datetime(2026, 11, 24, 12, 0, 0)
    H.add("old", cfg_data={"history_days": 0}, now=now - timedelta(days=40))
    H.add("recent", cfg_data={"history_days": 0}, now=now - timedelta(days=2))
    assert len(H.load()) == 2                                     # 0 days keeps everything
    H.add("new", cfg_data={"history_days": 30}, now=now)
    assert [e["text"] for e in H.load()] == ["new", "recent"]
    assert H.add("x", cfg_data={"history_enabled": False}, now=now) is None
    assert len(H.load()) == 2


def test_torn_line_does_not_hide_the_rest(isolate_xdg_dirs):
    from phonotype.core import history as H
    H.add("one", cfg_data={})
    with open(H.history_path(), "a", encoding="utf-8") as f:
        f.write('{"ts": "2026-11-24T10:00:00", "text": "tw\n')
    assert [e["text"] for e in H.load()] == ["one"]


def test_history_window_filters_and_shows_raw(qapp):
    from phonotype.core import history as H
    from phonotype.core.config import get_config
    from phonotype.gui.history_window import HistoryWindow, entry_title
    t0 = datetime(2026, 11, 24, 16, 34, 58)
    H.add("Запусти Kubernetes", "запусти кубернетес", cfg_data={}, prompt="default", now=t0)
    H.add("Просто текст", cfg_data={}, now=t0 + timedelta(minutes=5))

    w = HistoryWindow(get_config())
    w.show()
    assert w.list.count() == 2 and w.list.item(0).text() == "24.11 16:39  Просто текст"
    assert not w.raw.isVisible()                                  # nothing was rewritten
    w.search.setText("kubernetes")
    assert w.list.count() == 1 and w.text.toPlainText() == "Запусти Kubernetes"
    assert w.raw.isVisible() and w.raw.toPlainText() == "запусти кубернетес"
    assert "AI: Default" in w.details.text() and w.count.text() == "1 of 2"
    w.delete_current()
    assert [e["text"] for e in H.load()] == ["Просто текст"]
    assert entry_title({"ts": "bad", "text": "x" * 100}).endswith("…")
