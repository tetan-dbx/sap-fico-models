"""Deploy Unity Catalog metric views from YAML definitions.

Reads every ``*.yaml`` file in ``--metric_views_dir`` (each file is a metric-view
body in the same style as the reference examples), substitutes the ``${catalog}``
and ``${schema}`` placeholders, and runs

    CREATE OR REPLACE VIEW <catalog>.<schema>.<name> WITH METRICS LANGUAGE YAML AS $$ ... $$

on the configured SQL warehouse (where metric-view DDL is fully supported). The
view name is the YAML file's base name. Idempotent via CREATE OR REPLACE.

Run as a serverless ``spark_python_task`` in the project's Databricks Asset Bundle,
after the SDP pipeline has built the gold tables.
"""

import argparse
import pathlib
import sys

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deploy UC metric views from YAML.")
    parser.add_argument("--metric_views_dir", required=True, help="Directory of *.yaml metric-view definitions.")
    parser.add_argument("--catalog", required=True, help="Target catalog.")
    parser.add_argument("--schema", required=True, help="Target schema.")
    parser.add_argument("--warehouse_id", required=True, help="SQL warehouse id for metric-view DDL.")
    return parser.parse_args()


def render(body: str, catalog: str, schema: str) -> str:
    return body.replace("${catalog}", catalog).replace("${schema}", schema)


def main() -> None:
    args = parse_args()
    view_dir = pathlib.Path(args.metric_views_dir)
    yaml_files = sorted(view_dir.glob("*.yaml"))
    if not yaml_files:
        raise RuntimeError(f"no *.yaml files found in {view_dir}")

    w = WorkspaceClient()
    failures = []

    for path in yaml_files:
        name = path.stem
        body = render(path.read_text(), args.catalog, args.schema)
        full_name = f"`{args.catalog}`.`{args.schema}`.`{name}`"
        ddl = f"CREATE OR REPLACE VIEW {full_name} WITH METRICS LANGUAGE YAML AS $$\n{body}\n$$"

        print(f"Deploying metric view {full_name} from {path.name} ...")
        resp = w.statement_execution.execute_statement(
            warehouse_id=args.warehouse_id,
            statement=ddl,
            wait_timeout="50s",
        )
        state = resp.status.state if resp.status else None
        # Poll if the warehouse was cold / statement still running.
        while state in (StatementState.PENDING, StatementState.RUNNING):
            resp = w.statement_execution.get_statement(resp.statement_id)
            state = resp.status.state if resp.status else None

        if state == StatementState.SUCCEEDED:
            print(f"  OK: {full_name}")
        else:
            msg = resp.status.error.message if (resp.status and resp.status.error) else state
            print(f"  FAILED: {full_name}: {msg}", file=sys.stderr)
            failures.append((name, str(msg)))

    if failures:
        detail = "; ".join(f"{name}: {msg}" for name, msg in failures)
        raise RuntimeError(f"{len(failures)} metric view(s) failed: {detail}")

    print(f"\nAll {len(yaml_files)} metric view(s) deployed to {args.catalog}.{args.schema}.")


# Note: do not call sys.exit() — inside a Databricks spark_python_task a raised
# SystemExit (even code 0) is reported as a task failure. Raise on error instead.
if __name__ == "__main__":
    main()
