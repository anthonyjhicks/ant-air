from __future__ import annotations

import ast
import os
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4
import subprocess

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"

SCRIPT_RUNS: dict[str, "ScriptRun"] = {}
SCRIPT_RUN_ORDER: list[str] = []
MAX_SCRIPT_RUN_HISTORY = 50
SCRIPT_RUNS_LOCK = threading.Lock()

SCRIPT_ARG_OVERRIDES = {
    "import_csv": {
        "arguments": [
            {
                "id": "csv_path",
                "label": "CSV path",
                "help": "Path to CSV file",
                "required": True,
            }
        ]
    }
}

SCRIPT_DESCRIPTION_OVERRIDES = {
    "backfill_airline_code_ba": (
        "Fill missing airline_code fields with BA for all flights."
    ),
    "backfill_baflightpath_airline_code": (
        "Set airline_code to BA for baflightpath flights that are missing it."
    ),
    "backfill_flight_aircraft_from_history": (
        "Copy aircraft type and registration from the latest history record onto flights."
    ),
    "backfill_flight_history": (
        "Fetch flight history from FlightAware AeroAPI (last 10 days only) and store normalized history entries."
    ),
    "backfill_flight_stats": (
        "Compute missing distance values using stored or looked-up coordinates."
    ),
    "backfill_gemini_codeshare": (
        "Use Gemini to infer aircraft and codeshare details for missing-aircraft flights."
    ),
    "backfill_geo_data": (
        "Backfill lat/long, distance, and route direction using airport data and geocoding."
    ),
    "backfill_trips": (
        "Create Trip and TripLeg records for flights that have trip identifiers."
    ),
    "cleanup_airnav_missing": (
        "Remove AirNavMissing placeholders and delete empty AirNavRadar history rows."
    ),
    "cleanup_gemini_guess_registrations": (
        "Clear low-confidence Gemini-guess registrations without AirNavRadar support."
    ),
    "sync_airnavradar_history_aircraft_type": (
        "Sync AirNavRadar history aircraft_type from raw payload values."
    ),
    "import_boarding_pass_scans": (
        "Parse boarding pass PDFs with Gemini and import draft flights into the inbox."
    ),
    "import_csv": (
        "Import flights from a CSV file, deleting existing flights for matching booking sites."
    ),
    "import_flightpath_csv": (
        "Import BA Flightpath CSV, replacing existing baflightpath flights."
    ),
    "import_sources": (
        "Delete all flights then import TripIt, Google Flights, and BA Flightpath CSVs."
    ),
    "import_tripit_har": (
        "Parse a TripIt HAR file and import draft flights into the inbox."
    ),
    "normalize_aircraft_type_names": (
        "Normalize aircraft type codes into full names across flights and history."
    ),
    "normalize_flight_numbers": (
        "Split combined flight numbers into airline_code + numeric flight_number."
    ),
    "ungroup_singleton_flights": (
        "Clear grouping_id for any duplicate group that has only one flight."
    ),
    "validate_duplicate_groups": (
        "Preview duplicate grouping suggestions using current match rules."
    ),
}

class ScriptRunnerError(RuntimeError):
    pass


@dataclass
class ScriptRun:
    run_id: str
    script_key: str
    command: list[str]
    created_at: datetime
    status: str = "running"
    exit_code: int | None = None
    finished_at: datetime | None = None
    output_lines: list[str] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)
    process: subprocess.Popen[str] | None = None
    stop_requested: bool = False

    def append_output(self, line: str) -> None:
        with self.lock:
            self.output_lines.append(line)

    def complete(self, exit_code: int) -> None:
        with self.lock:
            self.exit_code = exit_code
            self.finished_at = datetime.utcnow()
            if self.stop_requested:
                self.status = "stopped"
            else:
                self.status = "success" if exit_code == 0 else "failed"


def humanize_name(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").strip().title()


def extract_constant(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    return None


def extract_action(value: ast.AST | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, ast.Constant):
        return value.value if isinstance(value.value, str) else None
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute):
        return value.attr
    return None


class ArgumentCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.argument_calls: list[ast.Call] = []
        self.parser_calls: list[ast.Call] = []

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute):
            if node.func.attr == "add_argument":
                self.argument_calls.append(node)
            elif node.func.attr == "ArgumentParser":
                self.parser_calls.append(node)
        self.generic_visit(node)


def parse_script_metadata(script_path: Path) -> dict[str, Any]:
    content = script_path.read_text(encoding="utf-8")
    description = None
    arguments: list[dict[str, Any]] = []
    options: list[dict[str, Any]] = []

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return {"description": description, "arguments": arguments, "options": options}

    docstring = ast.get_docstring(tree)
    if docstring:
        description = docstring.strip().splitlines()[0]

    collector = ArgumentCollector()
    collector.visit(tree)

    for parser_call in collector.parser_calls:
        for keyword in parser_call.keywords:
            if keyword.arg == "description":
                value = extract_constant(keyword.value)
                if isinstance(value, str):
                    description = value
                    break
        if description:
            break

    for call in collector.argument_calls:
        positional_names: list[str] = []
        flags: list[str] = []
        for arg in call.args:
            value = extract_constant(arg)
            if not isinstance(value, str):
                continue
            if value.startswith("-"):
                flags.append(value)
            else:
                positional_names.append(value)

        help_text = None
        action = None
        default_value = None
        for keyword in call.keywords:
            if keyword.arg == "help":
                value = extract_constant(keyword.value)
                if isinstance(value, str):
                    help_text = value
            elif keyword.arg == "action":
                action = extract_action(keyword.value)
            elif keyword.arg == "default":
                default_value = extract_constant(keyword.value)

        if flags:
            primary_flag = next((flag for flag in flags if flag.startswith("--")), flags[0])
            option_id = primary_flag.lstrip("-").replace("-", "_")
            is_toggle = action in ("store_true", "store_false", "BooleanOptionalAction")
            if is_toggle:
                default_checked = False
                if action in ("store_true", "BooleanOptionalAction"):
                    default_checked = (
                        bool(default_value) if isinstance(default_value, bool) else False
                    )
                options.append(
                    {
                        "id": option_id,
                        "flag": primary_flag,
                        "label": help_text or humanize_name(primary_flag.lstrip("-")),
                        "help": help_text,
                        "type": "toggle",
                        "default": default_checked,
                        "action": action,
                    }
                )
            else:
                options.append(
                    {
                        "id": option_id,
                        "flag": primary_flag,
                        "label": help_text or humanize_name(primary_flag.lstrip("-")),
                        "help": help_text,
                        "type": "text",
                        "default": default_value if isinstance(default_value, str) else "",
                    }
                )
        elif positional_names:
            arg_name = positional_names[0]
            arguments.append(
                {
                    "id": arg_name,
                    "label": humanize_name(arg_name),
                    "help": help_text,
                    "required": True,
                }
            )

    return {"description": description, "arguments": arguments, "options": options}


def build_script_catalog() -> dict[str, Any]:
    scripts: list[dict[str, Any]] = []
    if not SCRIPTS_DIR.exists():
        return {"items": scripts, "by_key": {}}

    for script_path in sorted(SCRIPTS_DIR.glob("*.py")):
        key = script_path.stem
        metadata = parse_script_metadata(script_path)
        overrides = SCRIPT_ARG_OVERRIDES.get(key, {})
        arguments = overrides.get("arguments", metadata["arguments"])
        options = overrides.get("options", metadata["options"])
        description = (
            SCRIPT_DESCRIPTION_OVERRIDES.get(key)
            or metadata["description"]
            or f"{humanize_name(key)} utility script."
        )
        script_info = {
            "key": key,
            "title": humanize_name(key),
            "description": description,
            "filename": script_path.name,
            "arguments": arguments,
            "options": options,
            "path": script_path,
        }
        scripts.append(script_info)

    return {
        "items": scripts,
        "by_key": {script["key"]: script for script in scripts},
    }


_SCRIPT_CATALOG: dict[str, Any] | None = None


def get_script_catalog() -> dict[str, Any]:
    global _SCRIPT_CATALOG
    if _SCRIPT_CATALOG is None:
        _SCRIPT_CATALOG = build_script_catalog()
    return _SCRIPT_CATALOG


def start_script_run(
    script_key: str | None,
    options: dict[str, Any] | None,
    arguments: dict[str, Any] | None,
) -> ScriptRun:
    if not script_key:
        raise ScriptRunnerError("No script selected.")

    catalog = get_script_catalog()
    script = catalog["by_key"].get(script_key)
    if not script:
        raise ScriptRunnerError("Unknown script.")

    options = options or {}
    arguments = arguments or {}

    command = [sys.executable, str(script["path"])]
    for arg in script["arguments"]:
        value = arguments.get(arg["id"])
        if arg.get("required") and not value:
            raise ScriptRunnerError(f"Missing required argument: {arg['label']}.")
        if value:
            command.append(str(value))

    for option in script["options"]:
        option_id = option["id"]
        if option["type"] == "toggle":
            if options.get(option_id):
                command.append(option["flag"])
        else:
            value = options.get(option_id)
            if value:
                command.extend([option["flag"], str(value)])

    run_id = uuid4().hex
    run = ScriptRun(
        run_id=run_id,
        script_key=script_key,
        command=command,
        created_at=datetime.utcnow(),
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{REPO_ROOT}:{env.get('PYTHONPATH', '')}".rstrip(":")

    process = subprocess.Popen(
        command,
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    run.process = process

    def stream_output() -> None:
        if process.stdout is None:
            run.append_output("No output stream available.\n")
            run.complete(process.wait())
            return
        for line in process.stdout:
            run.append_output(line)
        exit_code = process.wait()
        run.complete(exit_code)

    thread = threading.Thread(target=stream_output, daemon=True)
    thread.start()

    with SCRIPT_RUNS_LOCK:
        SCRIPT_RUNS[run_id] = run
        SCRIPT_RUN_ORDER.append(run_id)
        if len(SCRIPT_RUN_ORDER) > MAX_SCRIPT_RUN_HISTORY:
            oldest = SCRIPT_RUN_ORDER.pop(0)
            SCRIPT_RUNS.pop(oldest, None)

    return run


def get_script_run_status(run_id: str, cursor: int = 0) -> dict[str, Any] | None:
    with SCRIPT_RUNS_LOCK:
        run = SCRIPT_RUNS.get(run_id)

    if not run:
        return None

    with run.lock:
        output_lines = run.output_lines[cursor:]
        next_cursor = len(run.output_lines)
        return {
            "run_id": run.run_id,
            "script_key": run.script_key,
            "status": run.status,
            "exit_code": run.exit_code,
            "command": run.command,
            "created_at": run.created_at.isoformat() + "Z",
            "finished_at": run.finished_at.isoformat() + "Z"
            if run.finished_at
            else None,
            "output": output_lines,
            "next_cursor": next_cursor,
        }


def get_script_history() -> list[dict[str, Any]]:
    with SCRIPT_RUNS_LOCK:
        run_ids = list(reversed(SCRIPT_RUN_ORDER))
        runs = [SCRIPT_RUNS.get(run_id) for run_id in run_ids]

    history: list[dict[str, Any]] = []
    for run in runs:
        if not run:
            continue
        with run.lock:
            history.append(
                {
                    "run_id": run.run_id,
                    "script_key": run.script_key,
                    "status": run.status,
                    "exit_code": run.exit_code,
                    "command": run.command,
                    "created_at": run.created_at.isoformat() + "Z",
                    "finished_at": run.finished_at.isoformat() + "Z"
                    if run.finished_at
                    else None,
                }
            )
    return history


def stop_script_run(run_id: str) -> ScriptRun:
    with SCRIPT_RUNS_LOCK:
        run = SCRIPT_RUNS.get(run_id)

    if not run:
        raise ScriptRunnerError("Run not found.")

    with run.lock:
        if run.status != "running":
            return run
        run.stop_requested = True
        run.status = "stopping"
        process = run.process

    if process and process.poll() is None:
        process.terminate()

    return run
