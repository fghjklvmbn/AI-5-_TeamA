from app import classify_status


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
    gpu = {"vram_used_percent": 10, "cuda_utilization_percent": 70}
    assert classify_status(
        service_online=True, process_cpu_percent=1, system_ram_percent=1,
        gpu=gpu, gpu_expected=True, latency_delayed=False,
    )[0] == "yellow"
