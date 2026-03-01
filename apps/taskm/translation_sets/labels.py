"""
Task Manager — Translation Set (i18n).

Translation Sets provide multi-language labels and notification strings.
Resolution chain: user.preferred_language → "en" (mandatory default) → key name.

Demonstrates:
  - Multiple languages (en, fr, es)
  - Parameterized translations with {name}, {count} placeholders
  - Notification/email strings alongside UI labels
  - .get(key, lang=None, **params) auto-detects language from user context
  - .ref(key) returns lazy reference for use in Interface Field labels

Design ref: AppOS_Design.md §5.18
"""


@translation_set(name="taskm_labels", app="taskm")
def taskm_translations():
    """
    Task Manager i18n labels.

    Usage in rules:
        msg = translations.taskm_labels.get("welcome_msg", name="Alice")
        # → "Welcome, Alice!" for English user

    Usage in interfaces:
        Field("title", label=translations.taskm_labels.ref("task_title"))
        # → "Task Title" for English, "Título de Tarea" for Spanish
    """
    return {
        # --- UI Labels ---
        "task_title": {
            "en": "Task Title",
            "fr": "Titre de la Tâche",
            "es": "Título de Tarea",
        },
        "project_name": {
            "en": "Project Name",
            "fr": "Nom du Projet",
            "es": "Nombre del Proyecto",
        },
        "priority": {
            "en": "Priority",
            "fr": "Priorité",
            "es": "Prioridad",
        },
        "status": {
            "en": "Status",
            "fr": "Statut",
            "es": "Estado",
        },
        "assignee": {
            "en": "Assignee",
            "fr": "Responsable",
            "es": "Asignado",
        },
        "due_date": {
            "en": "Due Date",
            "fr": "Date Limite",
            "es": "Fecha Límite",
        },
        "save_button": {
            "en": "Save",
            "fr": "Sauvegarder",
            "es": "Guardar",
        },
        "cancel_button": {
            "en": "Cancel",
            "fr": "Annuler",
            "es": "Cancelar",
        },
        "delete_button": {
            "en": "Delete",
            "fr": "Supprimer",
            "es": "Eliminar",
        },

        # --- Parameterized messages ---
        "welcome_msg": {
            "en": "Welcome, {name}!",
            "fr": "Bienvenue, {name} !",
            "es": "¡Bienvenido, {name}!",
        },
        "task_created_msg": {
            "en": "Task '{title}' has been created in project {project}.",
            "fr": "La tâche '{title}' a été créée dans le projet {project}.",
            "es": "La tarea '{title}' se ha creado en el proyecto {project}.",
        },
        "overdue_alert": {
            "en": "{count} task(s) are overdue.",
            "fr": "{count} tâche(s) en retard.",
            "es": "{count} tarea(s) vencida(s).",
        },
        "task_assigned_msg": {
            "en": "Task '{title}' has been assigned to {assignee}.",
            "fr": "La tâche '{title}' a été assignée à {assignee}.",
            "es": "La tarea '{title}' ha sido asignada a {assignee}.",
        },
    }


# Expose the translation set under the decorator name expected by imports
# e.g. from apps.taskm.translation_sets.labels import taskm_labels
taskm_labels = taskm_translations
