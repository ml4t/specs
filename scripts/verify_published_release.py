"""Verify PyPI and GitHub records against the immutable release candidate."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

try:
    from scripts.release_candidate import (
        EXPECTED_DESCRIPTION,
        EXPECTED_GITHUB_HOMEPAGE,
        EXPECTED_GITHUB_TOPICS,
    )
except ModuleNotFoundError:  # Direct execution adds scripts/, not the repository root, to sys.path.
    from release_candidate import (
        EXPECTED_DESCRIPTION,
        EXPECTED_GITHUB_HOMEPAGE,
        EXPECTED_GITHUB_TOPICS,
    )

HASH_PATTERN = re.compile(r"[0-9a-f]{64}")


def _artifact_records(manifest: dict[str, Any]) -> dict[str, tuple[str, int]]:
    records = manifest.get("artifacts", [])
    if not isinstance(records, list):
        return {}
    return {
        str(record.get("filename", "")): (
            str(record.get("sha256", "")),
            int(record.get("size", 0)),
        )
        for record in records
        if isinstance(record, dict)
    }


def _pypi_metadata(info: dict[str, Any]) -> dict[str, Any]:
    return {
        "author_email": info.get("author_email"),
        "classifiers": sorted(info.get("classifiers", [])),
        "description": info.get("summary"),
        "keywords": sorted(
            keyword.strip() for keyword in str(info.get("keywords", "")).split(",") if keyword
        ),
        "license": info.get("license_expression") or info.get("license"),
        "maintainer_email": info.get("maintainer_email"),
        "project_urls": info.get("project_urls"),
        "requires_python": info.get("requires_python"),
    }


def published_release_failures(
    manifest: dict[str, Any],
    pypi: dict[str, Any],
    release: dict[str, Any],
    repository_metadata: dict[str, Any],
) -> list[str]:
    """Return mismatches across the candidate, PyPI, and GitHub release."""
    failures: list[str] = []
    version = str(manifest.get("version", ""))
    commit = str(manifest.get("commit_sha", ""))
    artifacts = _artifact_records(manifest)
    metadata = manifest.get("metadata")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("name") != "ml4t-specs"
        or not version
        or len(commit) != 40
        or not isinstance(metadata, dict)
        or len(artifacts) != 2
        or any(
            not HASH_PATTERN.fullmatch(digest) or size < 1 for digest, size in artifacts.values()
        )
    ):
        return ["release candidate manifest is incomplete"]

    info = pypi.get("info", {})
    if not isinstance(info, dict):
        failures.append("PyPI response omits project metadata")
    elif (
        info.get("name") != "ml4t-specs"
        or info.get("version") != version
        or _pypi_metadata(info) != metadata
    ):
        failures.append("PyPI metadata differs from the qualified candidate")

    pypi_files = {
        str(record.get("filename", "")): (
            str(record.get("digests", {}).get("sha256", "")),
            int(record.get("size", 0)),
        )
        for record in pypi.get("urls", [])
        if isinstance(record, dict)
    }
    if pypi_files != artifacts:
        failures.append("PyPI artifact names, sizes, or digests differ from the candidate")

    assets = [asset for asset in release.get("assets", []) if isinstance(asset, dict)]
    release_assets = {
        str(asset.get("name", "")): str(asset.get("digest", "")).removeprefix("sha256:")
        for asset in assets
        if str(asset.get("name", "")) in artifacts
    }
    expected_digests = {filename: digest for filename, (digest, _) in artifacts.items()}
    if release.get("tag_name") != f"v{version}" or release.get("target_commitish") != commit:
        failures.append("GitHub release tag or target differs from the candidate")
    if release_assets != expected_digests:
        failures.append("GitHub release artifact digests differ from the candidate")
    if "candidate.json" not in {str(asset.get("name", "")) for asset in assets}:
        failures.append("GitHub release does not attach the candidate manifest")
    if (
        repository_metadata.get("description") != EXPECTED_DESCRIPTION
        or repository_metadata.get("homepage") != EXPECTED_GITHUB_HOMEPAGE
        or not set(repository_metadata.get("topics", [])) >= EXPECTED_GITHUB_TOPICS
    ):
        failures.append("GitHub repository metadata differs from the qualified candidate")
    return failures


def _read_json(url: str, *, token: str | None = None) -> dict[str, Any]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ml4t-specs-release",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError(f"{url} did not return a JSON object")
    return payload


def remote_release_failures(
    manifest: dict[str, Any], repository: str, *, attempts: int = 12, wait_seconds: float = 10.0
) -> list[str]:
    """Poll public records until publication propagation completes."""
    version = urllib.parse.quote(str(manifest.get("version", "")), safe="")
    tag = urllib.parse.quote(f"v{manifest.get('version', '')}", safe="")
    failures: list[str] = []
    for attempt in range(attempts):
        try:
            failures = published_release_failures(
                manifest,
                _read_json(f"https://pypi.org/pypi/ml4t-specs/{version}/json"),
                _read_json(
                    f"https://api.github.com/repos/{repository}/releases/tags/{tag}",
                    token=os.environ.get("GITHUB_TOKEN"),
                ),
                _read_json(
                    f"https://api.github.com/repos/{repository}",
                    token=os.environ.get("GITHUB_TOKEN"),
                ),
            )
        except Exception as error:  # noqa: BLE001
            failures = [f"public release records are unavailable: {error}"]
        if not failures:
            return []
        if attempt + 1 < attempts:
            time.sleep(wait_seconds)
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--repository", default="ml4t/specs")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    failures = remote_release_failures(manifest, args.repository)
    print(f"published release identity: {'PASS' if not failures else 'FAIL'}")
    for failure in failures:
        print(f"- {failure}")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
