"""Director context picker: one JSON request on stdin, one JSON response line on stdout, exit 0.

Usage: python context_solver.py < request.json
"""

import time

_T0 = time.perf_counter()

import json  # noqa: E402
import sys  # noqa: E402

_INTERNAL_ERROR = '{"status":"invalid","reason":"internal error"}'


def _read_stdin() -> bytes:
    """Read at most MAX_BYTES + 1 bytes; drain and discard anything beyond."""
    import dcp_validate

    stream = sys.stdin.buffer
    raw = stream.read(dcp_validate.MAX_BYTES + 1)
    if len(raw) > dcp_validate.MAX_BYTES:
        while stream.read(1 << 20):
            pass
    return raw


def main() -> int:
    line = _INTERNAL_ERROR
    try:
        import dcp_pipeline

        resp = dcp_pipeline.run(_read_stdin(), _T0)
        line = json.dumps(resp, separators=(",", ":"), ensure_ascii=True)
        diag = dcp_pipeline.LAST_DIAG
        try:
            sys.stderr.write(
                f"context_solver: method={diag['method']} active={diag['active']} "
                f"proven={diag['proven']} elapsed_ms={dcp_pipeline.elapsed_ms(_T0)}\n"
            )
        except Exception:  # noqa: BLE001
            pass
    except BaseException:  # noqa: BLE001 - the process must still answer with one well-formed line
        line = _INTERNAL_ERROR
        try:
            import traceback

            traceback.print_exc()
        except Exception:  # noqa: BLE001
            pass
    try:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()
    except Exception:  # noqa: BLE001
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
