from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from emss.app import build_application
from emss.config.settings import load_settings
from emss.services.users import UserValidationError
from emss.services.backup import BackupError


def _write_json_output(output: Path, payload: dict[str, object]) -> None:
    target = output.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(target)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="emss", description="E-MAS Farmasi"
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Lokasi file konfigurasi TOML nonsensitif",
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("init-db", help="Terapkan migrasi database lokal")
    health = subparsers.add_parser(
        "health", help="Periksa kesehatan fondasi aplikasi"
    )
    health.add_argument(
        "--output",
        type=Path,
        help="Tulis hasil JSON secara atomik ke file untuk otomasi",
    )

    gui_smoke = subparsers.add_parser(
        "gui-smoke", help="Uji login GUI pada database sementara terisolasi"
    )
    gui_smoke.add_argument("--output", type=Path, required=True)
    bundle_smoke = subparsers.add_parser('bundle-smoke', help='Uji pemuatan DDI dan pemetaan pada data sementara')
    bundle_smoke.add_argument('--output', type=Path, required=True)

    create_admin = subparsers.add_parser(
        "create-admin", help="Buat administrator lokal pertama"
    )
    create_admin.add_argument("--username")
    create_admin.add_argument("--display-name")

    backup = subparsers.add_parser(
        "backup", help="Buat backup database lokal dengan checksum"
    )
    backup.add_argument("--reason", default="MANUAL")
    subparsers.add_parser("backup-list", help="Tampilkan riwayat backup")
    verify = subparsers.add_parser(
        "backup-verify", help="Verifikasi checksum dan integritas backup"
    )
    verify.add_argument("path", type=Path)
    restore = subparsers.add_parser(
        "restore", help="Pulihkan database dari backup tervalidasi"
    )
    restore.add_argument("path", type=Path)
    restore.add_argument(
        "--yes",
        action="store_true",
        help="Konfirmasi penggantian database aktif",
    )

    subparsers.add_parser("gui", help="Jalankan antarmuka desktop")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command_name = args.command or "gui"

    if command_name == 'bundle-smoke':
        if args.config is not None:
            _write_json_output(args.output, {'state':'ERROR','error_type':'CONFIG_NOT_ALLOWED'})
            return 2
        from emss.release.bundle_smoke import run_bundle_smoke
        payload = run_bundle_smoke()
        _write_json_output(args.output, payload)
        return 0 if payload.get('state') == 'READY' else 1

    if command_name == "gui-smoke":
        if args.config is not None:
            _write_json_output(args.output, {"state": "ERROR", "error_type": "CONFIG_NOT_ALLOWED"})
            return 2
        from emss.release.gui_smoke import run_gui_smoke

        payload = run_gui_smoke()
        _write_json_output(args.output, payload)
        return 0 if payload.get("state") == "READY" else 1

    try:
        settings = load_settings(args.config)
        container = build_application(settings)
    except (FileNotFoundError, ValueError, ValidationError) as exc:
        if sys.stderr is not None:
            print(f"Konfigurasi gagal: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        if command_name == "health" and args.output is not None:
            failure: dict[str, object] = {
                "state": "ERROR",
                "error_type": type(exc).__name__,
            }
            if isinstance(exc, ModuleNotFoundError):
                failure["missing_module"] = exc.name
            _write_json_output(args.output, failure)
        if sys.stderr is not None:
            print(
                f"Inisialisasi aplikasi gagal: {type(exc).__name__}",
                file=sys.stderr,
            )
        return 3

    try:
        if command_name == "init-db":
            print(
                "Database siap. Revisi:",
                container.database.current_revision(),
            )
            return 0
        if command_name == "health":
            result = container.health.check()
            health_payload = result.to_dict()
            if args.output is not None:
                _write_json_output(args.output, health_payload)
            if sys.stdout is not None:
                print(
                    json.dumps(
                        health_payload,
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            return 0 if result.state.value == "READY" else 1
        if command_name == "create-admin":
            username = args.username or input("Username administrator: ").strip()
            display_name = (
                args.display_name or input("Nama tampilan: ").strip()
            )
            password = getpass.getpass("Password (minimal 6 karakter): ")
            confirmation = getpass.getpass("Ulangi password: ")
            if password != confirmation:
                print("Password tidak sama.", file=sys.stderr)
                return 4
            try:
                user = container.users.create_first_admin(
                    username=username,
                    display_name=display_name,
                    password=password,
                )
            except UserValidationError as exc:
                print(f"Gagal membuat administrator: {exc}", file=sys.stderr)
                return 5
            print(f"Administrator '{user.username}' berhasil dibuat.")
            seed = container.bundled_ddi.apply_if_eligible(user.id)
            container.bundled_mapping.apply_if_eligible(user.id)
            if seed.status in {"APPLIED", "APPLIED_ALONGSIDE_EXISTING_MASTER"}:
                print(
                    f"Master DDI '{seed.bundle_id}' berhasil dimuat sebagai DRAFT: "
                    f"{seed.rule_count} pair, {seed.ingredient_count} zat aktif."
                )
                if seed.status == "APPLIED_ALONGSIDE_EXISTING_MASTER":
                    print("Master lokal yang sudah ada tetap dipertahankan sebagai versi terpisah.")
            elif seed.status == "RECOVERED_EXISTING_BUNDLE":
                print("Master DDI bawaan lama dikenali kembali; hasil review yang ada dipertahankan.")
            return 0
        if command_name == "backup":
            try:
                record = container.backup.create_backup(args.reason)
            except BackupError as exc:
                print(f"Backup gagal: {exc}", file=sys.stderr)
                return 6
            print(
                json.dumps(
                    {
                        "status": "SUCCESS",
                        "file": str(record.database_path),
                        "checksum_sha256": record.checksum_sha256,
                        "schema_revision": record.schema_revision,
                        "size_bytes": record.size_bytes,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        if command_name == "backup-list":
            print(
                json.dumps(
                    [
                        {
                            "created_at": item.created_at,
                            "reason": item.reason,
                            "file": str(item.database_path),
                            "checksum_sha256": item.checksum_sha256,
                            "schema_revision": item.schema_revision,
                            "size_bytes": item.size_bytes,
                        }
                        for item in container.backup.list_backups()
                    ],
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        if command_name == "backup-verify":
            try:
                record = container.backup.verify_backup(args.path)
            except BackupError as exc:
                print(f"Verifikasi gagal: {exc}", file=sys.stderr)
                return 7
            print(
                f"VALID: {record.database_path} | "
                f"SHA-256 {record.checksum_sha256}"
            )
            return 0
        if command_name == "restore":
            if not args.yes:
                print(
                    "Restore dibatalkan. Tambahkan --yes setelah memastikan "
                    "file dan waktu backup sudah benar.",
                    file=sys.stderr,
                )
                return 8
            try:
                result = container.backup.restore_backup(args.path, None)
            except BackupError as exc:
                print(f"Restore gagal: {exc}", file=sys.stderr)
                return 9
            print(
                "Restore berhasil. Safety backup: "
                f"{result.safety_backup}. Jalankan ulang aplikasi."
            )
            return 0
        if command_name == "gui":
            from emss.ui.application import run_gui

            return run_gui(container)
        print(f"Perintah tidak dikenal: {command_name}", file=sys.stderr)
        return 2
    finally:
        container.close()
