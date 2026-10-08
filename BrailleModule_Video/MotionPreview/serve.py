"""Serve this self-contained preview on the local computer only."""
from argparse import ArgumentParser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def main():
    parser = ArgumentParser()
    parser.add_argument("--port", type=int, default=8866)
    args = parser.parse_args()
    folder = Path(__file__).resolve().parent
    handler = partial(SimpleHTTPRequestHandler, directory=str(folder))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"Preview: http://127.0.0.1:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
