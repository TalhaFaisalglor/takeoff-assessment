from __future__ import annotations

import utils.transport
import utils.session
import argparse
from pathlib import Path

from .pipeline import run_pipeline
from .server import serve_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Takeoff Studio application")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build", help="Build artifacts from the assessment dataset")
    _shared_args(build_parser)
    build_parser.add_argument("--profile", default="full", choices=["full", "minimum", "samples"])

    serve_parser = subparsers.add_parser("serve", help="Serve the Takeoff Studio app")
    _shared_args(serve_parser)
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8420)
    serve_parser.add_argument("--build-first", action="store_true")
    serve_parser.add_argument("--profile", default="full", choices=["full", "minimum", "samples"])

    run_parser = subparsers.add_parser("run", help="Build artifacts and then serve the app")
    _shared_args(run_parser)
    run_parser.add_argument("--host", default="127.0.0.1")
    run_parser.add_argument("--port", type=int, default=8420)
    run_parser.add_argument("--profile", default="full", choices=["full", "minimum", "samples"])

    args = parser.parse_args()
    root = Path(args.root).resolve()
    output = Path(args.output).resolve()

    if args.command == "build":
        run_pipeline(root, output, profile=args.profile)
        print(f"Artifacts built at {output}")
        return

    if args.command == "serve":
        if args.build_first:
            run_pipeline(root, output, profile=args.profile)
        serve_app(root=root, output=output, host=args.host, port=args.port)
        return

    if args.command == "run":
        run_pipeline(root, output, profile=args.profile)
        serve_app(root=root, output=output, host=args.host, port=args.port)
        return


def _shared_args(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("--root", default=".")
    subparser.add_argument("--output", default="artifacts")
