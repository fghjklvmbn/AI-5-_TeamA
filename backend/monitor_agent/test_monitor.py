from types import SimpleNamespace

import app
from app import HardwareSampler, classify_status


def test_status_thresholds_follow_operational_rules():
    assert classify_status(
        service_online=True, process_cpu_percent=50, system_ram_percent=70,
        gpu=None, gpu_expected=False, latency_delayed=False,
    )[0] == "green"
    assert classify_status(
        service_online=True, process_cpu_percent=50.1, system_ram_percent=20,
        gpu=None, gpu_expected=False, latency_delayed=False,
    )[0] == "yellow"
    assert classify_status(
        service_online=False, process_cpu_percent=0, system_ram_percent=0,
        gpu=None, gpu_expected=False, latency_delayed=False,
    )[0] == "red"


def test_gpu_or_conditions_mark_yellow():
    gpu = {"vram_used_percent": 80, "cuda_utilization_percent": 10}
    assert classify_status(
        service_online=True, process_cpu_percent=1, system_ram_percent=1,
        gpu=gpu, gpu_expected=True, latency_delayed=False,
    )[0] == "yellow"


def test_monitor_rebinds_to_loopback_health_listener_when_target_pid_is_stale(monkeypatch):
    class FakeProcess:
        def __init__(self, pid):
            self.pid = pid

        def children(self, recursive=False):
            return []

    monkeypatch.setattr(app, "HEALTH_URL", "http://127.0.0.1:8010/v1/health")
    monkeypatch.setattr(app, "TARGET_PID", 99999)
    monkeypatch.setattr(app.psutil, "Process", FakeProcess)
    monkeypatch.setattr(app.psutil, "net_connections", lambda **_kwargs: [
        SimpleNamespace(
            status=app.psutil.CONN_LISTEN,
            pid=24700,
            laddr=SimpleNamespace(port=8010),
        ),
    ])

    processes = HardwareSampler()._candidate_processes()

    assert [process.pid for process in processes] == [24700]
    gpu = {"vram_used_percent": 10, "cuda_utilization_percent": 70}
    assert classify_status(
        service_online=True, process_cpu_percent=1, system_ram_percent=1,
        gpu=gpu, gpu_expected=True, latency_delayed=False,
    )[0] == "yellow"
