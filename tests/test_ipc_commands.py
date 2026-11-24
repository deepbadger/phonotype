import time


def test_ipc_dispatches_named_commands(isolate_xdg_dirs):
    from phonotype.utils import ipc_client, ipc_server
    got = []
    ipc_server.start_ipc_server(lambda: got.append("trigger"),
                                {"cancel_record": lambda: got.append("cancel"),
                                 "paste_last": lambda: got.append("paste")})
    assert ipc_client.send_command("paste_last")
    assert ipc_client.send_command("bogus")           # ignored, listener survives
    assert ipc_client.send_command("cancel_record")
    assert ipc_client.send_trigger()
    for _ in range(50):
        if len(got) == 3:
            break
        time.sleep(0.02)
    assert got == ["paste", "cancel", "trigger"]
