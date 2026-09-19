"""Reject an ambiguous or already-published ml4t-specs release candidate."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from packaging.version import InvalidVersion, Version

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

COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")
SOURCE_VERSION_PATTERN = re.compile(r'^__version__ = "([^"]+)"$', re.MULTILINE)


@dataclass(frozen=True)
class PublicationState:
    """Existing public records for one proposed version."""

    git_tag: bool
    github_release: bool
    pypi_version: bool


@dataclass(frozen=True)
class RepositoryMetadata:
    """Public GitHub identity fields that must agree with the release."""

    description: str
    homepage: str
    topics: frozenset[str]


def repository_metadata_failures(metadata: RepositoryMetadata) -> list[str]:
    """Return public GitHub identity mismatches."""
    failures = []
    if metadata.description != EXPECTED_DESCRIPTION:
        failures.append("GitHub description differs from the canonical package description")
    if metadata.homepage != EXPECTED_GITHUB_HOMEPAGE:
        failures.append("GitHub homepage differs from the canonical documentation route")
    if not metadata.topics >= EXPECTED_GITHUB_TOPICS:
        failures.append("GitHub topics omit required ecosystem or package-specific terms")
    return failures


def version_failure(value: str) -> str | None:
    """Return why a version cannot identify a new stable release."""
    try:
        version = Version(value)
    except InvalidVersion:
        return "release version is not PEP 440 compliant"
    if (
        str(version) != value
        or len(version.release) != 3
        or version.is_prerelease
        or version.is_devrelease
        or version.local is not None
    ):
        return "release version must be a normalized stable X.Y.Z or X.Y.Z.postN version"
    return None


def preflight_failures(
    *,
    version: str,
    source_version: str,
    candidate_sha: str,
    checked_out_sha: str,
    workflow_sha: str,
    main_sha: str,
    publication: PublicationState,
    repository_metadata: RepositoryMetadata,
) -> list[str]:
    """Return every condition that makes publication unsafe."""
    failures = []
    if failure := version_failure(version):
        failures.append(failure)
    if source_version != version:
        failures.append("source version differs from the requested release version")
    if not COMMIT_PATTERN.fullmatch(candidate_sha):
        failures.append("candidate commit is not a full lowercase SHA")
    if checked_out_sha != candidate_sha:
        failures.append("checked-out commit differs from the requested candidate")
    if workflow_sha != candidate_sha:
        failures.append("workflow revision differs from the requested candidate")
    if main_sha != candidate_sha:
        failures.append("candidate commit is not the current origin/main revision")
    if publication.git_tag:
        failures.append(f"Git tag v{version} already exists")
    if publication.github_release:
        failures.append(f"GitHub release v{version} already exists")
    if publication.pypi_version:
        failures.append(f"PyPI version {version} already exists")
    failures.extend(repository_metadata_failures(repository_metadata))
    return failures


def _git_output(*arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _resource_exists(url: str, *, token: str | None = None) -> bool:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ml4t-specs-release",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30):  # noqa: S310
            return True
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return False
        raise


def publication_state(repository: str, version: str) -> PublicationState:
    """Read tag, release, and PyPI existence without changing public state."""
    encoded_tag = urllib.parse.quote(f"tags/v{version}", safe="")
    encoded_version = urllib.parse.quote(version, safe="")
    return PublicationState(
        git_tag=_resource_exists(
            f"https://api.github.com/repos/{repository}/git/ref/{encoded_tag}",
            token=os.environ.get("GITHUB_TOKEN"),
        ),
        github_release=_resource_exists(
            f"https://api.github.com/repos/{repository}/releases/tags/v{encoded_version}",
            token=os.environ.get("GITHUB_TOKEN"),
        ),
        pypi_version=_resource_exists(f"https://pypi.org/pypi/ml4t-specs/{encoded_version}/json"),
    )


def github_repository_metadata(repository: str) -> RepositoryMetadata:
    """Read public repository identity from GitHub."""
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "User-Agent": "ml4t-specs-release",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("GitHub repository response must be a JSON object")
    return RepositoryMetadata(
        description=str(payload.get("description") or ""),
        homepage=str(payload.get("homepage") or ""),
        topics=frozenset(str(topic) for topic in payload.get("topics", [])),
    )


def source_version() -> str:
    """Read the release version without importing the source package."""
    source = Path("src/ml4t/specs/__init__.py").read_text(encoding="utf-8")
    match = SOURCE_VERSION_PATTERN.search(source)
    if match is None:
        raise ValueError("source package does not declare __version__")
    return match.group(1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--repository", default="ml4t/specs")
    parser.add_argument("--workflow-sha", required=True)
    args = parser.parse_args()
    failures = preflight_failures(
        version=args.version,
        source_version=source_version(),
        candidate_sha=args.candidate_sha,
        checked_out_sha=_git_output("rev-parse", "HEAD"),
        workflow_sha=args.workflow_sha,
        main_sha=_git_output("rev-parse", "refs/remotes/origin/main"),
        publication=publication_state(args.repository, args.version),
        repository_metadata=github_repository_metadata(args.repository),
    )
    print(f"release preflight: {'PASS' if not failures else 'FAIL'}")
    for failure in failures:
        print(f"- {failure}")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
