from __future__ import annotations

import argparse
import ctypes
import logging
import multiprocessing
import socket
import sys
import time
import traceback
import urllib.error
import urllib.request
from threading import Thread

import uvicorn

from backend.app.main import app as backend_app
from backend.app.config import (
    APP_NAME,
    APP_VERSION,
    LOG_FILE,
    FRONTEND_DIST_DIR,
    WEBVIEW_STORAGE_DIR,
    WHISPER_CUDA_MODEL_SIZE,
    WHISPER_CPU_FALLBACK_MODEL_SIZE,
    WHISPER_CPU_PRIMARY_MODEL_SIZE,
)
from backend.app.services.runtime_setup import prepare_runtime_assets

APP_TITLE = APP_NAME
SERVER_HOST = "127.0.0.1"
SERVER_STARTUP_TIMEOUT_SECONDS = 45
WINDOW_WIDTH = 1440
WINDOW_HEIGHT = 960
WINDOW_MIN_WIDTH = 1200
WINDOW_MIN_HEIGHT = 760


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--prepare-runtime", action="store_true")
    return parser.parse_args(argv)


def configure_logging() -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
        ],
        force=True,
    )


def show_error(message: str) -> None:
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, message, APP_TITLE, 0x10)
        return
    print(message, file=sys.stderr)


def ensure_frontend_bundle() -> None:
    index_path = FRONTEND_DIST_DIR / "index.html"
    if index_path.exists():
        return
    raise RuntimeError(
        "Desktop frontend bundle is missing.\n\n"
        "Run scripts/build-desktop.ps1 to build the desktop EXE."
    )


def pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((SERVER_HOST, 0))
        return int(sock.getsockname()[1])


class ServerThread(Thread):
    def __init__(self, port: int) -> None:
        super().__init__(name="desktop-backend", daemon=True)
        self.port = port
        self.server: uvicorn.Server | None = None
        self.error: BaseException | None = None

    def run(self) -> None:
        try:
            config = uvicorn.Config(
                backend_app,
                host=SERVER_HOST,
                port=self.port,
                reload=False,
                access_log=False,
                log_level="warning",
                server_header=False,
                date_header=False,
            )
            self.server = uvicorn.Server(config)
            self.server.run()
        except BaseException as exc:  # pragma: no cover
            self.error = exc

    def stop(self) -> None:
        if self.server is not None:
            self.server.should_exit = True


def wait_for_server(base_url: str, thread: ServerThread) -> None:
    deadline = time.monotonic() + SERVER_STARTUP_TIMEOUT_SECONDS
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        if thread.error is not None:
            raise RuntimeError(f"Backend failed to start: {thread.error}") from thread.error
        if not thread.is_alive():
            raise RuntimeError("Backend stopped before the desktop window could open.")

        try:
            with urllib.request.urlopen(f"{base_url}/api/health", timeout=1.5) as response:
                if response.status == 200:
                    return
        except urllib.error.URLError as exc:
            last_error = exc
        except TimeoutError as exc:
            last_error = exc
        except OSError as exc:
            # Windows can briefly reset the first loopback request while uvicorn is still
            # finishing startup. Treat it as transient and keep probing until timeout.
            last_error = exc

        time.sleep(0.2)

    message = "Backend startup timed out."
    if last_error is not None:
        message = f"{message}\n\nLast error: {last_error}"
    raise RuntimeError(message)


def _prepare_runtime(logger: logging.Logger) -> int:
    logger.info("Preparing runtime assets")
    prepare_runtime_assets(
        whisper_model_sizes=(
            WHISPER_CPU_PRIMARY_MODEL_SIZE,
            WHISPER_CPU_FALLBACK_MODEL_SIZE,
        ),
        cuda_model_size=WHISPER_CUDA_MODEL_SIZE,
        progress_callback=logger.info,
    )
    logger.info("Runtime assets are ready")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging()
    logger = logging.getLogger("desktop")
    try:
        if args.prepare_runtime:
            return _prepare_runtime(logger)

        import webview

        logger.info("Desktop startup")
        logger.info("App version=%s", APP_VERSION)
        logger.info("Frozen=%s", getattr(sys, "frozen", False))
        logger.info("Frontend dist=%s", FRONTEND_DIST_DIR)
        logger.info("Webview storage=%s", WEBVIEW_STORAGE_DIR)
        ensure_frontend_bundle()
        port = pick_free_port()
        base_url = f"http://{SERVER_HOST}:{port}"
        WEBVIEW_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

        server_thread = ServerThread(port)
        server_thread.start()
        logger.info("Backend thread started on %s", base_url)

        try:
            wait_for_server(base_url, server_thread)
            logger.info("Backend healthcheck passed")
            webview.create_window(
                APP_TITLE,
                base_url,
                width=WINDOW_WIDTH,
                height=WINDOW_HEIGHT,
                min_size=(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT),
            )
            logger.info("Starting pywebview")
            webview.start(
                debug=False,
                gui="edgechromium",
                private_mode=False,
                storage_path=str(WEBVIEW_STORAGE_DIR),
            )
            logger.info("pywebview exited cleanly")
        finally:
            logger.info("Stopping backend thread")
            server_thread.stop()
            server_thread.join(timeout=5)
            logger.info("Backend thread alive after join=%s", server_thread.is_alive())

        return 0
    except Exception as exc:
        logger.exception("Desktop startup failed")
        logger.error("Traceback:\n%s", traceback.format_exc())
        if not args.prepare_runtime:
            show_error(str(exc))
        return 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
