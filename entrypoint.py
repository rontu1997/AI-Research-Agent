"""Process wrapper: starts Streamlit and drains active runs on SIGTERM (PRD NFR-19).

    uv run entrypoint.py            # same as `streamlit run app.py`, plus graceful shutdown

On SIGTERM the wrapper writes the drain marker (the app then refuses new runs), waits until no
runs are active or DRAIN_TIMEOUT_S passes, then stops Streamlit. A deploy during a longer run can
still cut it off; that limit is documented in the FAQ and PRD.
"""

from __future__ import annotations

import signal
import subprocess
import sys
import threading
from collections.abc import Sequence

from core.drain import DrainMarker, wait_for_drain
from core.settings import load_settings_from_environment


def main(argv: Sequence[str] | None = None) -> int:
    settings = load_settings_from_environment()
    marker = DrainMarker(settings.state_dir)
    marker.clear()
    marker.publish_active(0)
    extra = list(argv if argv is not None else sys.argv[1:])
    child = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app.py", *extra])
    stopping = threading.Event()

    def on_term(signum: int, frame: object) -> None:  # noqa: ARG001
        if stopping.is_set():
            return
        stopping.set()

        def drain() -> None:
            wait_for_drain(marker, timeout_s=settings.drain_timeout_s)
            child.terminate()

        threading.Thread(target=drain, daemon=True).start()

    signal.signal(signal.SIGTERM, on_term)
    signal.signal(signal.SIGINT, on_term)
    return child.wait()


if __name__ == "__main__":
    sys.exit(main())
