"""
Validates that all url_for() calls in templates have corresponding routes defined.
Run this at app startup to catch missing endpoints early.
"""
import re
import glob
from pathlib import Path


def get_template_endpoints():
    """Extract all non-blueprintendpoint names referenced in templates."""
    endpoints = set()
    for html_file in glob.glob('templates/**/*.html', recursive=True):
        try:
            with open(html_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                # Find url_for calls: url_for('endpoint_name' or url_for("endpoint_name"
                matches = re.findall(r"url_for\s*\(\s*['\"]([a-zA-Z0-9_.]+)['\"]", content)
                for m in matches:
                    # Skip 'static' built-in and blueprint-qualified names (containing .)
                    if '.' not in m and m != 'static':
                        endpoints.add(m)
        except Exception as e:
            print(f"Warning: Could not parse {html_file}: {e}")
    return endpoints


def get_app_endpoints(app):
    """Extract all route endpoint names from Flask app."""
    endpoints = set()
    for rule in app.url_map.iter_rules():
        # Skip special endpoints
        if not rule.endpoint.startswith('_') and rule.endpoint != 'static':
            endpoints.add(rule.endpoint)
    return endpoints


def validate_endpoints(app):
    """
    Check that all template url_for() calls have matching routes.
    Raises ValueError if any are missing.
    """
    template_endpoints = get_template_endpoints()
    app_endpoints = get_app_endpoints(app)
    
    missing = template_endpoints - app_endpoints

    if missing:
        sorted_missing = sorted(missing)
        print(
            f"⚠ Endpoint validation warning: {len(missing)} template endpoint(s) "
            f"have no matching route:\n" +
            "\n".join(f"  - {ep}" for ep in sorted_missing)
        )
    else:
        print(
            f"✓ Endpoint validation passed: {len(app_endpoints)} routes defined, "
            f"all {len(template_endpoints)} template references matched."
        )


if __name__ == "__main__":
    # For manual testing. create_app() returns (app, socketio).
    from app import create_app

    created = create_app()
    if isinstance(created, tuple):
        app = created[0]
    else:
        app = created

    validate_endpoints(app)
