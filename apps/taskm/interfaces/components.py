"""
Shared UI component helpers for interfaces.

These would be real Reflex components at runtime; here they return
plain dicts that describe the component tree for testing/registration.
"""


def DataTable(record, columns, searchable=False, filterable=False,
              page_size=25, actions=None, row_actions=None):
    return {
        "_component": "DataTable",
        "record": record,
        "columns": columns,
        "searchable": searchable,
        "filterable": filterable,
        "page_size": page_size,
        "actions": actions or [],
        "row_actions": row_actions or [],
    }


def Form(record, fields, submit_label="Save", cancel_label="Cancel"):
    return {
        "_component": "Form",
        "record": record,
        "fields": fields,
        "submit_label": submit_label,
        "cancel_label": cancel_label,
    }


def Field(name, label=None, field_type="text", required=False, choices=None):
    return {
        "_component": "Field",
        "name": name,
        "label": label or name.replace("_", " ").title(),
        "field_type": field_type,
        "required": required,
        "choices": choices,
    }


def Button(label, action="navigate", to=None, rule=None, confirm=False):
    return {
        "_component": "Button",
        "label": label,
        "action": action,
        "to": to,
        "rule": rule,
        "confirm": confirm,
    }


def Layout(children):
    return {"_component": "Layout", "children": children}


def Row(children):
    return {"_component": "Row", "children": children}


def Card(title, content=None):
    return {"_component": "Card", "title": title, "content": content}


def Metric(label, value, change=None):
    return {"_component": "Metric", "label": label, "value": value, "change": change}
