from pathlib import Path
from ember.adapters.daemon.client import DaemonEmbedderClient
from ember.adapters.daemon.lifecycle import DaemonLifecycle


def test_daemon_paths_partitioned_by_model():
    """Verify Unix sockets, PID, and log paths are partitioned by model name."""
    # Test client path partitioning
    client_default = DaemonEmbedderClient()
    client_code = DaemonEmbedderClient(model_name="jina-code-v2")
    client_doc = DaemonEmbedderClient(model_name="jina-en-v2")

    # The default socket path
    assert "daemon.sock" in str(client_default.socket_path)

    # Path partition for code model preset
    assert "jinaai_jina_embeddings_v2_base_code" in str(client_code.socket_path)

    # Path partition for doc model preset
    assert "jinaai_jina_embeddings_v2_base_en" in str(client_doc.socket_path)

    # Test lifecycle path partitioning
    lc_default = DaemonLifecycle()
    lc_code = DaemonLifecycle(model_name="jina-code-v2")
    lc_doc = DaemonLifecycle(model_name="jina-en-v2")

    assert "daemon.sock" in str(lc_default.socket_path)
    assert "daemon.pid" in str(lc_default.pid_file)
    assert "daemon.log" in str(lc_default.log_file)

    assert "jinaai_jina_embeddings_v2_base_code" in str(lc_code.socket_path)
    assert "jinaai_jina_embeddings_v2_base_code" in str(lc_code.pid_file)
    assert "jinaai_jina_embeddings_v2_base_code" in str(lc_code.log_file)

    assert "jinaai_jina_embeddings_v2_base_en" in str(lc_doc.socket_path)
    assert "jinaai_jina_embeddings_v2_base_en" in str(lc_doc.pid_file)
    assert "jinaai_jina_embeddings_v2_base_en" in str(lc_doc.log_file)
