"""Guard the two distinct two-room analysis interfaces during integration.

These tests check CLI wiring only; they do not assert scientific validity.
"""
from cleanroomx.cfd_pipeline_cli import build_parser


def test_explorer_two_room_cli_keeps_explicit_output_flag():
    args = build_parser().parse_args(
        ["two-room-analyze", "case", "receipt.json", "--output", "explorer"]
    )
    assert args.command == "two-room-analyze"
    assert args.case_directory == "case"
    assert args.receipt == "receipt.json"
    assert args.output == "explorer"


def test_receipt_bound_bundle_cli_keeps_positional_output():
    args = build_parser().parse_args(
        ["two-room-verified-bundle", "case", "receipt.json", "verified"]
    )
    assert args.command == "two-room-verified-bundle"
    assert args.output_directory == "verified"


def test_receipt_bound_bundle_audit_cli():
    args = build_parser().parse_args(["two-room-bundle-audit", "verified"])
    assert args.command == "two-room-bundle-audit"
    assert args.directory == "verified"
