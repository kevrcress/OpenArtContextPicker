"""Director context picker: one JSON request on stdin, one JSON response line on stdout, exit 0.

Exit status 1 only when the response line could not be written to stdout.

Usage: python context_solver.py < request.json
"""

import time

_T0 = time.perf_counter()

import json  # noqa: E402
import sys  # noqa: E402

_INTERNAL_ERROR = '{"status":"invalid","reason":"internal error"}'


def _read_stdin() -> bytes:
    """Read at most MAX_BYTES + 1 bytes, then stop: bytes past the limit are never read or drained.

    A request over the limit is invalid as soon as byte MAX_BYTES + 1 has been seen, and a
    producer that keeps the pipe open must not block the answer.
    """
    import os

    import dcp_validate

    limit = dcp_validate.MAX_BYTES + 1
    fd = sys.stdin.fileno()
    chunks = []
    got = 0
    while got < limit:
        chunk = os.read(fd, min(1 << 20, limit - got))  # returns what is there; blocks only when nothing is
        if not chunk:
            break
        chunks.append(chunk)
        got += len(chunk)
    return b"".join(chunks)


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
        sys.stdout.write(line + "\n")  # one write of the complete line, then one flush
        sys.stdout.flush()
    except BaseException as exc:  # noqa: BLE001 - an undelivered response is a failure, not exit 0
        try:
            sys.stderr.write(f"context_solver: could not write the response to stdout: {exc!r}\n")
        except Exception:  # noqa: BLE001
            pass
        try:
            # Keep the interpreter's own flush at exit from failing a second time on the same stream.
            import os

            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except Exception:  # noqa: BLE001
            pass
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
