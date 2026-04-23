from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote, unquote, urlparse
import json

import requests


@dataclass(frozen=True)
class NpmPackageUrl:
    package_name: str
    original_url: str


def parse_npm_package_url(url: str) -> NpmPackageUrl | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host not in {"www.npmjs.com", "npmjs.com"}:
        return None

    parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2 or parts[0] != "package":
        return None

    if parts[1].startswith("@") and len(parts) >= 3:
        package_name = f"{parts[1]}/{parts[2]}"
    else:
        package_name = parts[1]

    return NpmPackageUrl(package_name=package_name, original_url=url)


def fetch_npm_package_markdown(package_url: NpmPackageUrl) -> str:
    package_name = package_url.package_name
    registry_name = quote(package_name, safe="@")
    registry_url = f"https://registry.npmjs.org/{registry_name}"
    response = requests.get(
        registry_url,
        headers={"Accept": "application/vnd.npm.install-v1+json, application/json"},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    latest_version = data.get("dist-tags", {}).get("latest")
    version_data = data.get("versions", {}).get(latest_version, {}) if latest_version else {}
    readme = data.get("readme") or version_data.get("readme") or "[No README found]"

    lines = [
        f"# {package_name}",
        "",
        f"Source URL: {package_url.original_url}",
        "",
        f"Registry URL: {registry_url}",
        "",
        "## Metadata",
        "",
        f"- Name: {data.get('name', package_name)}",
        f"- Latest version: {latest_version or '[unknown]'}",
        f"- Description: {data.get('description') or version_data.get('description') or '[none]'}",
    ]

    homepage = version_data.get("homepage") or data.get("homepage")
    repository = _repository_url(version_data.get("repository") or data.get("repository"))
    license_value = version_data.get("license") or data.get("license")
    if homepage:
        lines.append(f"- Homepage: {homepage}")
    if repository:
        lines.append(f"- Repository: {repository}")
    if license_value:
        lines.append(f"- License: {license_value}")

    keywords = version_data.get("keywords") or data.get("keywords")
    if keywords:
        lines.append(f"- Keywords: {', '.join(map(str, keywords))}")

    dependencies = version_data.get("dependencies") or {}
    if dependencies:
        lines.extend(["", "## Dependencies", ""])
        lines.extend(f"- `{name}`: `{constraint}`" for name, constraint in sorted(dependencies.items()))

    lines.extend(["", "## README", "", readme.rstrip(), ""])
    return "\n".join(lines)


def _repository_url(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        url = value.get("url")
        if url:
            return str(url)
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)
