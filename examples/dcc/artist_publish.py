from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from _api import ApiError, PipelineApiClient  # noqa: E402
from _workflow import (  # noqa: E402
    EntityLocator,
    PublishRequest,
    ensure_task,
    render_summary,
    run_publish,
)

TASK_STATUS_CHOICES = ["blocked", "pending", "in_progress", "review", "revision", "approved"]
STEP_TYPE_CHOICES = [
    "layout",
    "animation",
    "fx",
    "lighting",
    "compositing",
    "roto",
    "paint",
    "matchmove",
    "prep",
    "matte_painting",
    "cfx",
    "editorial",
    "rendering",
    "modeling",
    "rigging",
    "shading",
    "groom",
    "lookdev",
    "texture",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generic publish client that exercises the real Pipeline Production Hub API."
    )
    parser.add_argument("--base-url", default=os.getenv("PPH_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--email", default=os.getenv("PPH_EMAIL"))
    parser.add_argument("--password", default=os.getenv("PPH_PASSWORD"))
    parser.add_argument("--task-id")
    parser.add_argument("--project-id")
    parser.add_argument("--project-code")
    parser.add_argument("--shot-id")
    parser.add_argument("--shot-code")
    parser.add_argument("--asset-id")
    parser.add_argument("--asset-code")
    parser.add_argument("--step-type", choices=STEP_TYPE_CHOICES)
    parser.add_argument("--step-name")
    parser.add_argument("--order", type=int, default=1)
    parser.add_argument("--initial-task-status", choices=TASK_STATUS_CHOICES, default="pending")
    parser.add_argument("--file", dest="primary_file", required=True, type=Path)
    parser.add_argument("--preview-file", type=Path)
    parser.add_argument("--description")
    parser.add_argument("--set-task-status", choices=TASK_STATUS_CHOICES)
    parser.add_argument("--status-comment")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.email or not args.password:
        parser.error("--email and --password are required (or set PPH_EMAIL / PPH_PASSWORD)")

    try:
        with PipelineApiClient(args.base_url) as client:
            print(f"Logging in to {args.base_url} ...")
            client.login(args.email, args.password)

            locator = EntityLocator(
                project_id=args.project_id,
                project_code=args.project_code,
                shot_id=args.shot_id,
                shot_code=args.shot_code,
                asset_id=args.asset_id,
                asset_code=args.asset_code,
            )
            task_id = ensure_task(
                client,
                task_id=args.task_id,
                locator=locator,
                step_type=args.step_type,
                step_name=args.step_name,
                order=args.order,
                initial_status=args.initial_task_status,
                notify=print,
            )
            request = PublishRequest(
                task_id=task_id,
                primary_file=args.primary_file,
                preview_file=args.preview_file,
                description=args.description,
                set_task_status=args.set_task_status,
                status_comment=args.status_comment,
                source_label="Artist CLI",
            )
            result = run_publish(client, request, notify=print)

        print()
        print(render_summary(result))
        return 0
    except (ApiError, FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"\nPublish failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
