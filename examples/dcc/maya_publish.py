from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

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
        description="Maya-oriented publish example that hits the real backend API."
    )
    parser.add_argument("--base-url", default=os.getenv("PPH_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--email", default=os.getenv("PPH_EMAIL"))
    parser.add_argument("--password", default=os.getenv("PPH_PASSWORD"))
    parser.add_argument("--mode", choices=["auto", "mock", "maya"], default="auto")
    parser.add_argument("--task-id")
    parser.add_argument("--project-id")
    parser.add_argument("--project-code")
    parser.add_argument("--shot-id")
    parser.add_argument("--shot-code")
    parser.add_argument("--asset-id")
    parser.add_argument("--asset-code")
    parser.add_argument("--step-name", default="Animation")
    parser.add_argument("--step-type", choices=STEP_TYPE_CHOICES, default="animation")
    parser.add_argument("--order", type=int, default=1)
    parser.add_argument("--initial-task-status", choices=TASK_STATUS_CHOICES, default="pending")
    parser.add_argument("--scene-path", type=Path)
    parser.add_argument("--preview-file", type=Path)
    parser.add_argument("--frame-start", type=int)
    parser.add_argument("--frame-end", type=int)
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
        scene_context = resolve_scene_context(args)

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
            print(
                f"Using {scene_context['mode_label']} scene {scene_context['scene_path'].name}"
                f" ({scene_context['frame_start']}-{scene_context['frame_end']})."
            )
            description = args.description or build_maya_description(scene_context)
            request = PublishRequest(
                task_id=task_id,
                primary_file=scene_context["scene_path"],
                preview_file=args.preview_file,
                description=description,
                set_task_status=args.set_task_status,
                status_comment=args.status_comment,
                source_label=scene_context["source_label"],
            )
            result = run_publish(client, request, notify=print)

        print()
        print(render_summary(result))
        return 0
    except (ApiError, FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"\nMaya publish failed: {exc}", file=sys.stderr)
        return 1


def resolve_scene_context(args: argparse.Namespace) -> dict[str, Any]:
    if args.mode == "mock":
        return build_mock_context(args)

    if args.mode == "maya":
        return build_live_maya_context(args)

    if args.scene_path is not None:
        return build_mock_context(args)

    try:
        return build_live_maya_context(args)
    except RuntimeError:
        return build_mock_context(args)


def build_live_maya_context(args: argparse.Namespace) -> dict[str, Any]:
    try:
        from maya import cmds  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("Maya Python API is not available in this process") from exc

    scene_name = str(cmds.file(q=True, sceneName=True) or "")
    if not scene_name:
        raise RuntimeError("Current Maya scene is unsaved. Save it or pass --scene-path.")

    scene_path = Path(scene_name)
    if not scene_path.exists():
        raise FileNotFoundError(f"Current Maya scene path does not exist: {scene_path}")

    frame_start = (
        args.frame_start
        if args.frame_start is not None
        else int(cmds.playbackOptions(q=True, minTime=True))
    )
    frame_end = (
        args.frame_end
        if args.frame_end is not None
        else int(cmds.playbackOptions(q=True, maxTime=True))
    )
    return {
        "mode_label": "live Maya",
        "source_label": "Maya",
        "scene_path": scene_path,
        "frame_start": frame_start,
        "frame_end": frame_end,
    }


def build_mock_context(args: argparse.Namespace) -> dict[str, Any]:
    scene_path = args.scene_path or THIS_DIR / "fixtures" / "anim_v001.ma"
    if not scene_path.exists():
        raise FileNotFoundError(f"Maya scene not found: {scene_path}")

    return {
        "mode_label": "mock DCC",
        "source_label": "Maya mock",
        "scene_path": scene_path,
        "frame_start": args.frame_start or 1001,
        "frame_end": args.frame_end or 1100,
    }


def build_maya_description(scene_context: dict[str, Any]) -> str:
    return (
        f"{scene_context['source_label']} publish from {scene_context['scene_path'].name} "
        f"frames {scene_context['frame_start']}-{scene_context['frame_end']}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
