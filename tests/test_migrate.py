"""One-time import of VOXD's settings and data (phonotype.migrate)."""
import os


def _old_install(tmp_path):
    cfg = tmp_path / "config" / "voxd"; cfg.mkdir(parents=True)
    data = tmp_path / "data" / "voxd"; (data / "models").mkdir(parents=True)
    model = data / "models" / "ggml-tiny.bin"; model.write_bytes(b"m" * 10)
    (data / "output").mkdir()
    (data / "output" / "voxd_perf_data.csv").write_text("a,b\n")
    (cfg / "config.yaml").write_text(f"whisper_model_path: {model}\nlanguage: ru\n")
    (cfg / "keys.env").write_text("OPENROUTER_API_KEY=sk\n")
    return cfg, data, model


def test_import_copies_config_and_links_big_files(tmp_path, monkeypatch):
    import phonotype.migrate as M
    cfg, data, model = _old_install(tmp_path)
    monkeypatch.setattr(M, "LINK_ABOVE", 5)                 # the 10-byte "model" counts as large
    new_cfg, new_data = tmp_path / "config" / "phonotype", tmp_path / "data" / "phonotype"

    assert M.import_from_voxd(new_cfg, new_data) is True
    text = (new_cfg / "config.yaml").read_text()
    assert f"whisper_model_path: {new_data}/models/ggml-tiny.bin" in text and "language: ru" in text
    assert (new_cfg / "keys.env").read_text() == "OPENROUTER_API_KEY=sk\n"
    assert (new_cfg / "keys.env").stat().st_mode & 0o777 == 0o600
    new_model = new_data / "models" / "ggml-tiny.bin"
    assert os.path.samefile(new_model, model)               # hard link: no extra space
    assert (new_data / "output" / "phonotype_perf_data.csv").read_text() == "a,b\n"
    assert model.exists() and (cfg / "config.yaml").exists()   # nothing removed

    assert M.import_from_voxd(new_cfg, new_data) is False   # only once


def test_import_is_skipped_when_phonotype_already_configured(tmp_path):
    import phonotype.migrate as M
    _old_install(tmp_path)
    new_cfg = tmp_path / "config" / "phonotype"; new_cfg.mkdir(parents=True)
    (new_cfg / "config.yaml").write_text("language: en\n")
    assert M.import_from_voxd(new_cfg, tmp_path / "data" / "phonotype") is False
    assert (new_cfg / "config.yaml").read_text() == "language: en\n"


def test_nothing_to_import(tmp_path):
    import phonotype.migrate as M
    assert M.import_from_voxd(tmp_path / "c" / "phonotype", tmp_path / "d" / "phonotype") is False
    assert not (tmp_path / "c" / "phonotype").exists()
