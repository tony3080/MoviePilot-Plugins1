"""Runtime capability probes that do not perform network or file mutations."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Dict


def runtime_capabilities(plugin_dir: Path) -> Dict[str, Any]:
    grpc_ready = importlib.util.find_spec("grpc") is not None
    generated_ready = (
        (plugin_dir / "generated" / "clouddrive_pb2.py").is_file()
        and (plugin_dir / "generated" / "clouddrive_pb2_grpc.py").is_file()
    )
    proto_ready = (plugin_dir / "clouddrive.proto").is_file()
    return {
        "moviepilot": {
            "ready": True,
            "mode": "current_instance",
            "recognition": "host_runtime",
            "sites": "host_runtime",
        },
        "qbittorrent": {
            "ready": True,
            "scope": "moviepilot_configured_qbittorrent_only",
            "phase": "rss_enqueue_and_source_rename",
        },
        "clouddrive": {
            "ready": bool(grpc_ready and generated_ready and proto_ready),
            "grpc": grpc_ready,
            "generated": generated_ready,
            "proto": proto_ready,
            "phase": "connection_pending",
        },
        "catchup": {"ready": False, "phase": "client_pending"},
        "scanner": {"ready": False, "phase": "client_pending"},
    }
