"""Command-line interface for the ngxstorage Python SDK."""

from __future__ import annotations

import argparse
import json
import sys

from ngxstorage import NGXClient, ClientConfig


def _client(args: argparse.Namespace) -> NGXClient:
    return NGXClient(
        ClientConfig(
            controllers=args.controllers.split(","),
            api_key=args.api_key,
            pool_name=args.pool_name or "",
            insecure_skip_verify=not args.verify,
        )
    )


def _print(obj) -> None:
    json.dump(obj, sys.stdout, indent=2)
    sys.stdout.write("\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="ngxstorage", description="NGX Storage Manager API v2 CLI")
    parser.add_argument("--controllers", required=True, help="comma-separated controller IPs")
    parser.add_argument("--api-key", required=True, help="NGX API key")
    parser.add_argument("--pool-name", default="", help="canonical pool name")
    parser.add_argument("--verify", action="store_true", help="verify TLS (default: skip for self-signed NGX)")

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status", help="cluster work-mode status")
    sub.add_parser("pools", help="list storage pools")
    sub.add_parser("luns", help="list block volumes")
    sub.add_parser("shares", help="list file volumes")
    sub.add_parser("fctargets", help="list FC targets")
    sub.add_parser("snapshots", help="list snapshots")

    create_lun = sub.add_parser("create-lun", help="create a LUN")
    create_lun.add_argument("name")
    create_lun.add_argument("size_gb", type=int)

    delete_lun = sub.add_parser("delete-lun", help="delete a LUN")
    delete_lun.add_argument("lun_id")

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1

    client = _client(args)

    try:
        if args.command == "status":
            _print(client.status.cluster())
        elif args.command == "pools":
            _print(client.pools.list())
        elif args.command == "luns":
            _print(client.luns.list())
        elif args.command == "shares":
            _print(client.shares.list())
        elif args.command == "fctargets":
            _print(client.fc_targets.list())
        elif args.command == "snapshots":
            _print(client.snapshots.list())
        elif args.command == "create-lun":
            _print(client.luns.create(args.name, args.size_gb))
        elif args.command == "delete-lun":
            client.luns.delete(args.lun_id)
    except Exception as exc:  # noqa: BLE001 - CLI top-level error boundary
        print(f"ngxstorage: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
