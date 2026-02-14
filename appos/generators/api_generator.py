"""
AppOS REST API Generator — Auto-generates @web_api endpoint definitions
for @record objects, routing through the api_executor.py pipeline.

Generates:
    POST   /api/{app}/{records}        — Create
    GET    /api/{app}/{records}         — List
    GET    /api/{app}/{records}/{id}    — Get
    PUT    /api/{app}/{records}/{id}    — Update
    DELETE /api/{app}/{records}/{id}    — Delete
    GET    /api/{app}/{records}/search  — Search

Output:
    .appos/generated/{app}/apis/{record}_api.py

IMPORTANT: Generated endpoints are @web_api-decorated functions that
execute through api_executor.py (the standard AppOS pipeline) — NOT
standalone FastAPI/Flask routes.

Design refs: AppOS_Design.md §9 (API Endpoint Generator), §12 (Web API Engine)
"""

from __future__ import annotations

import logging
import os
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("appos.generators.api_generator")


class ApiGenerator:
    """
    Generates @web_api endpoint definitions for @record objects.

    These generated endpoints route through the AppOS api_executor pipeline
    (security check → rate limiting → execution → response formatting).

    Usage:
        gen = ApiGenerator(app_name="crm", app_dir="apps/crm",
                           output_dir=".appos/generated/crm/apis")
        count = gen.generate_all()
    """

    def __init__(
        self,
        app_name: str,
        app_dir: str,
        output_dir: str = "",
    ):
        self.app_name = app_name
        self.app_dir = Path(app_dir)
        self.output_dir = Path(output_dir) if output_dir else Path(f".appos/generated/{app_name}/apis")

    def generate_all(self) -> int:
        """
        Discover @record objects and generate REST API definitions.

        Returns:
            Number of API definition files generated.
        """
        records_dir = self.app_dir / "records"
        if not records_dir.exists():
            logger.info(f"No records/ directory in {self.app_dir}")
            return 0

        count = 0
        for py_file in sorted(records_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            try:
                records = self._discover_records(py_file)
                for record in records:
                    if record.get("generate_api", True):
                        self._generate_api(record)
                        count += 1
            except Exception as e:
                logger.warning(f"Failed to parse {py_file}: {e}")

        return count

    def _discover_records(self, py_file: Path) -> List[Dict[str, Any]]:
        """Discover @record-decorated models in a Python file."""
        import ast

        records = []
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, OSError):
            return records

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            has_record = any(
                (isinstance(d, ast.Name) and d.id == "record")
                or (isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "record")
                for d in node.decorator_list
            )
            if not has_record:
                continue

            # Parse Meta
            generate_api = True
            table_name = _to_snake(node.name)
            for item in node.body:
                if isinstance(item, ast.ClassDef) and item.name == "Meta":
                    for meta_item in item.body:
                        if isinstance(meta_item, ast.Assign):
                            for target in meta_item.targets:
                                if isinstance(target, ast.Name) and target.id == "generate_api":
                                    if isinstance(meta_item.value, ast.Constant):
                                        generate_api = bool(meta_item.value.value)
                                if isinstance(target, ast.Name) and target.id == "table_name":
                                    if isinstance(meta_item.value, ast.Constant):
                                        table_name = str(meta_item.value.value)

            # Collect fields
            fields = []
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    fields.append(item.target.id)

            records.append({
                "name": node.name,
                "table_name": table_name,
                "fields": fields,
                "generate_api": generate_api,
            })

        return records

    def _generate_api(self, record: Dict[str, Any]) -> Path:
        """
        Generate @web_api definitions for a record.

        Routes through api_executor.py pipeline — NOT standalone endpoints.
        """
        record_name = record["name"]
        table_name = record["table_name"]
        snake_name = _to_snake(record_name)
        plural = table_name + "s" if not table_name.endswith("s") else table_name
        base_path = f"/api/{self.app_name}/{plural}"
        service_class = f"{record_name}Service"

        code = textwrap.dedent(f'''\
            """
            Auto-generated REST API endpoints for {self.app_name}.{record_name}.

            Routes:
                POST   {base_path}            — Create
                GET    {base_path}            — List
                GET    {base_path}/{{id}}       — Get by ID
                PUT    {base_path}/{{id}}       — Update
                DELETE {base_path}/{{id}}       — Delete
                GET    {base_path}/search     — Search

            Generated by AppOS ApiGenerator.
            All endpoints route through the api_executor.py pipeline
            (security → rate limit → execution → response).
            """

            from appos.decorators.core import web_api


            @web_api(
                name="create_{snake_name}",
                method="POST",
                path="{base_path}",
                description="Create a new {record_name}",
            )
            def create_{snake_name}(ctx):
                """Create a new {record_name} record."""
                data = ctx.request.body
                service = ctx.get_service("{service_class}")
                result = service.create(data=data, user_id=ctx.user_id)
                return {{"status": "created", "id": result.id}}


            @web_api(
                name="list_{plural}",
                method="GET",
                path="{base_path}",
                description="List {record_name} records",
            )
            def list_{plural}(ctx):
                """List {record_name} records with pagination."""
                page = int(ctx.request.query.get("page", 1))
                page_size = int(ctx.request.query.get("page_size", 25))
                filters = {{
                    k: v for k, v in ctx.request.query.items()
                    if k not in ("page", "page_size")
                }}
                service = ctx.get_service("{service_class}")
                items = service.list(filters=filters, page=page, page_size=page_size)
                total = service.count(filters=filters)
                return {{
                    "items": items,
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                }}


            @web_api(
                name="get_{snake_name}",
                method="GET",
                path="{base_path}/{{id}}",
                description="Get a {record_name} by ID",
            )
            def get_{snake_name}(ctx):
                """Get a single {record_name} by ID."""
                record_id = int(ctx.request.path_params["id"])
                service = ctx.get_service("{service_class}")
                result = service.get(record_id)
                if result is None:
                    ctx.response.status_code = 404
                    return {{"error": "{record_name} not found"}}
                return result


            @web_api(
                name="update_{snake_name}",
                method="PUT",
                path="{base_path}/{{id}}",
                description="Update a {record_name}",
            )
            def update_{snake_name}(ctx):
                """Update an existing {record_name} record."""
                record_id = int(ctx.request.path_params["id"])
                data = ctx.request.body
                service = ctx.get_service("{service_class}")
                result = service.update(record_id, data=data, user_id=ctx.user_id)
                if result is None:
                    ctx.response.status_code = 404
                    return {{"error": "{record_name} not found"}}
                return {{"status": "updated", "id": result.id}}


            @web_api(
                name="delete_{snake_name}",
                method="DELETE",
                path="{base_path}/{{id}}",
                description="Delete a {record_name}",
            )
            def delete_{snake_name}(ctx):
                """Delete a {record_name} record (soft-delete if enabled)."""
                record_id = int(ctx.request.path_params["id"])
                service = ctx.get_service("{service_class}")
                success = service.delete(record_id, user_id=ctx.user_id)
                if not success:
                    ctx.response.status_code = 404
                    return {{"error": "{record_name} not found"}}
                return {{"status": "deleted", "id": record_id}}


            @web_api(
                name="search_{plural}",
                method="GET",
                path="{base_path}/search",
                description="Search {record_name} records",
            )
            def search_{plural}(ctx):
                """Full-text search across {record_name} records."""
                query = ctx.request.query.get("q", "")
                fields = ctx.request.query.get("fields", "").split(",") if ctx.request.query.get("fields") else None
                page = int(ctx.request.query.get("page", 1))
                page_size = int(ctx.request.query.get("page_size", 25))
                service = ctx.get_service("{service_class}")
                results = service.search(query=query, fields=fields, page=page, page_size=page_size)
                return {{"items": results, "query": query}}
        ''')

        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.output_dir / f"{snake_name}_api.py"
        output_path.write_text(code, encoding="utf-8")
        logger.info(f"Generated API: {output_path}")
        return output_path


def _to_snake(name: str) -> str:
    """Convert CamelCase to snake_case."""
    import re
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()
