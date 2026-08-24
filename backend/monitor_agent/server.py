from __future__ import annotations

import argparse
import os

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", required=True, choices=("stt", "llm", "tts", "gateway", "archive"))
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--target-pid", type=int, default=0)
    parser.add_argument("--process-names", default="")
    parser.add_argument("--health-url", default="")
    parser.add_argument("--gpu", action="store_true")
    parser.add_argument("--log-path", default="")
    parser.add_argument("--lms-cli", default="")
    parser.add_argument("--lmstudio-log-path", default="")
    parser.add_argument("--lmstudio-log-sources", default="server,runtime,model")
    parser.add_argument("--disable-lmstudio-logs", action="store_true")
    args = parser.parse_args()
    os.environ["MEMORYPAL_MONITOR_SERVICE"] = args.service
    os.environ["MEMORYPAL_MONITOR_TARGET_PID"] = str(args.target_pid)
    os.environ["MEMORYPAL_MONITOR_PROCESS_NAMES"] = args.process_names
    os.environ["MEMORYPAL_MONITOR_HEALTH_URL"] = args.health_url
    os.environ["MEMORYPAL_MONITOR_GPU"] = str(args.gpu).lower()
    if args.log_path:
        os.environ["MEMORYPAL_MONITOR_LOG_PATH"] = args.log_path
    if args.lms_cli:
        os.environ["MEMORYPAL_LMS_CLI"] = args.lms_cli
    if args.lmstudio_log_path:
        os.environ["MEMORYPAL_LMSTUDIO_LOG_PATH"] = args.lmstudio_log_path
    os.environ["MEMORYPAL_LMSTUDIO_LOG_SOURCES"] = args.lmstudio_log_sources
    os.environ["MEMORYPAL_LMSTUDIO_LOG_ENABLED"] = str(not args.disable_lmstudio_logs).lower()
    uvicorn.run("app:app", app_dir=os.path.dirname(__file__), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
