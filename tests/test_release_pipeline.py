"""Behavioral contracts for the commit-bound release helpers."""

from __future__ import annotations

import io
import json
import re
import tarfile
import zipfile
from email.message import Message
from pathlib import Path
from urllib.request import Request

import pytest
import yaml

from scripts.check_readme_links import USER_AGENT, check, targets
from scripts.check_release_preflight import (
    PublicationState,
    RepositoryMetadata,
    preflight_failures,
    version_failure,
)
from scripts.release_candidate import (
    EXPECTED_AUTHOR,
    EXPECTED_CLASSIFIERS,
    EXPECTED_DESCRIPTION,
    EXPECTED_GITHUB_HOMEPAGE,
    EXPECTED_GITHUB_TOPICS,
    EXPECTED_KEYWORDS,
    EXPECTED_MAINTAINER,
    EXPECTED_URLS,
    create,
    metadata_failures,
    verify,
)
from scripts.run_readme_quickstart import extract_quick_start
from scripts.verify_documentation_identity import identity_failures
from scripts.verify_published_release import published_release_failures

COMMIT = "a" * 40
TREE = "b" * 40
VERSION = "1.2.3"
REPOSITORY_ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize("version", ["1.2", "v1.2.3", "1.2.3rc1", "1.2.3+local"])
def test_release_preflight_rejects_nonstable_versions(version: str) -> None:
    assert version_failure(version) is not None


def test_release_preflight_requires_exact_unpublished_main_candidate() -> None:
    assert (
        preflight_failures(
            version=VERSION,
            source_version=VERSION,
            candidate_sha=COMMIT,
            checked_out_sha=COMMIT,
            workflow_sha=COMMIT,
            main_sha=COMMIT,
            publication=PublicationState(False, False, False),
            repository_metadata=RepositoryMetadata(
                EXPECTED_DESCRIPTION,
                EXPECTED_GITHUB_HOMEPAGE,
                frozenset(EXPECTED_GITHUB_TOPICS),
            ),
        )
        == []
    )
    failures = preflight_failures(
        version=VERSION,
        source_version="1.2.2",
        candidate_sha=COMMIT,
        checked_out_sha="c" * 40,
        workflow_sha="d" * 40,
        main_sha="e" * 40,
        publication=PublicationState(True, True, True),
        repository_metadata=RepositoryMetadata("", "", frozenset()),
    )
    assert len(failures) == 10


def canonical_metadata() -> Message:
    metadata = Message()
    for name, value in {
        "Name": "ml4t-specs",
        "Version": VERSION,
        "Summary": EXPECTED_DESCRIPTION,
        "Author-email": EXPECTED_AUTHOR,
        "Maintainer-email": EXPECTED_MAINTAINER,
        "License-Expression": "MIT",
        "Requires-Python": ">=3.12",
        "Keywords": ",".join(sorted(EXPECTED_KEYWORDS)),
        "License-File": "LICENSE",
    }.items():
        metadata[name] = value
    for classifier in sorted(EXPECTED_CLASSIFIERS):
        metadata["Classifier"] = classifier
    for label, url in EXPECTED_URLS.items():
        metadata["Project-URL"] = f"{label}, {url}"
    return metadata


def _candidate(tmp_path: Path) -> Path:
    candidate = tmp_path / "candidate"
    dist = candidate / "dist"
    dist.mkdir(parents=True)
    metadata = canonical_metadata().as_bytes()
    wheel = dist / "ml4t_specs-1.2.3-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("ml4t_specs-1.2.3.dist-info/METADATA", metadata)
    sdist = dist / "ml4t_specs-1.2.3.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        info = tarfile.TarInfo("ml4t_specs-1.2.3/PKG-INFO")
        info.size = len(metadata)
        archive.addfile(info, io.BytesIO(metadata))
    create(candidate, COMMIT, TREE)
    return candidate


def test_candidate_manifest_binds_identity_metadata_and_exact_bytes(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)

    verify(
        candidate,
        expected_commit=COMMIT,
        expected_tree=TREE,
        expected_tag=f"v{VERSION}",
    )

    wheel = next((candidate / "dist").glob("*.whl"))
    wheel.write_bytes(wheel.read_bytes() + b"modified")
    with pytest.raises(ValueError, match="integrity check failed"):
        verify(candidate)


def test_metadata_validation_detects_identity_drift() -> None:
    metadata = canonical_metadata()
    assert metadata_failures(metadata, expected_version=VERSION) == []
    metadata.replace_header("Maintainer-email", "Template Team <dev@example.com>")
    assert any(
        "Maintainer-email" in failure
        for failure in metadata_failures(metadata, expected_version=VERSION)
    )


def published_fixture(candidate: Path) -> tuple[dict, dict, dict, dict]:
    manifest = json.loads((candidate / "candidate.json").read_text(encoding="utf-8"))
    artifacts = manifest["artifacts"]
    metadata = manifest["metadata"]
    pypi = {
        "info": {
            "name": "ml4t-specs",
            "version": VERSION,
            "summary": metadata["description"],
            "author_email": metadata["author_email"],
            "maintainer_email": metadata["maintainer_email"],
            "license_expression": metadata["license"],
            "requires_python": metadata["requires_python"],
            "project_urls": metadata["project_urls"],
            "keywords": ",".join(metadata["keywords"]),
            "classifiers": metadata["classifiers"],
        },
        "urls": [
            {
                "filename": record["filename"],
                "digests": {"sha256": record["sha256"]},
                "size": record["size"],
            }
            for record in artifacts
        ],
    }
    release = {
        "tag_name": f"v{VERSION}",
        "target_commitish": COMMIT,
        "assets": [
            {"name": record["filename"], "digest": f"sha256:{record['sha256']}"}
            for record in artifacts
        ]
        + [{"name": "candidate.json", "digest": "sha256:" + "d" * 64}],
    }
    repository = {
        "description": EXPECTED_DESCRIPTION,
        "homepage": EXPECTED_GITHUB_HOMEPAGE,
        "topics": sorted(EXPECTED_GITHUB_TOPICS),
    }
    return manifest, pypi, release, repository


def test_published_release_must_match_candidate(tmp_path: Path) -> None:
    manifest, pypi, release, repository = published_fixture(_candidate(tmp_path))
    assert published_release_failures(manifest, pypi, release, repository) == []
    release["assets"][0]["digest"] = "sha256:" + "d" * 64
    assert "GitHub release artifact digests differ from the candidate" in (
        published_release_failures(manifest, pypi, release, repository)
    )


def test_documentation_identity_and_quickstart_are_executable_contracts() -> None:
    html = (
        '<meta name="ml4t-library" content="specs">'
        f'<meta name="ml4t-version" content="{VERSION}">'
        f'<meta name="ml4t-commit" content="{COMMIT}">'
    )
    assert (
        identity_failures(
            html,
            expected_library="specs",
            expected_version=VERSION,
            expected_commit=COMMIT,
            source="index.html",
        )
        == []
    )
    assert extract_quick_start("## Quick Start\n\n```python\nvalue = 1\n```\n") == "value = 1\n"


def test_readme_link_checker_validates_local_and_http_targets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "LICENSE").write_text("license\n", encoding="utf-8")
    readme = tmp_path / "README.md"
    readme.write_text("[local](LICENSE) [remote](https://example.test/docs)\n", encoding="utf-8")
    requests: list[Request] = []

    class Response(io.BytesIO):
        status = 200

    def open_url(request: Request, *, timeout: int) -> Response:
        requests.append(request)
        assert timeout == 20
        return Response(b"ok")

    monkeypatch.setattr("scripts.check_readme_links.urlopen", open_url)
    check(readme)
    assert requests[0].get_header("User-agent") == USER_AGENT


def test_readme_link_checker_includes_badge_image_and_destination(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        "[![PyPI](https://img.example.test/badge.svg)](https://pypi.example.test/project)\n",
        encoding="utf-8",
    )
    assert targets(readme) == (
        "https://img.example.test/badge.svg",
        "https://pypi.example.test/project",
    )


def test_workflows_enforce_documented_release_and_docs_contracts() -> None:
    release = yaml.load(
        (REPOSITORY_ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    docs = yaml.load(
        (REPOSITORY_ROOT / ".github/workflows/docs.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )

    assert set(release["on"]) == {"workflow_dispatch"}
    assert set(release["on"]["workflow_dispatch"]["inputs"]) == {"version", "candidate-sha"}
    assert release["concurrency"]["cancel-in-progress"] == "false"
    assert {
        "preflight",
        "ecosystem-qualification",
        "qualification",
        "build",
        "documentation",
        "publish",
        "github-release",
        "post-publication",
        "recovery",
    } == set(release["jobs"])
    assert "pull_request" in docs["on"]
    assert docs["concurrency"]["cancel-in-progress"] == "true"

    candidate_name = "release-candidate-${{ needs.preflight.outputs.commit }}"
    docs_name = "docs-${{ needs.preflight.outputs.commit }}"

    def artifact_names(job: str, action: str) -> list[str]:
        return [
            step["with"]["name"]
            for step in release["jobs"][job]["steps"]
            if action in step.get("uses", "") and "name" in step.get("with", {})
        ]

    assert candidate_name in artifact_names("build", "actions/upload-artifact")
    assert docs_name in artifact_names("build", "actions/upload-artifact")
    assert artifact_names("documentation", "actions/download-artifact") == [docs_name]
    for job in ("publish", "github-release", "post-publication"):
        assert artifact_names(job, "actions/download-artifact") == [candidate_name]
    assert release["jobs"]["publish"]["needs"] == ["preflight", "documentation"]
    assert release["jobs"]["github-release"]["needs"] == ["preflight", "publish"]
    assert release["jobs"]["post-publication"]["needs"] == ["preflight", "github-release"]


def test_external_workflow_actions_use_full_commit_pins() -> None:
    action = re.compile(r"^\s*uses:\s*(?!\./)([^\s#]+)@([^\s#]+)", re.MULTILINE)
    failures = []
    for workflow in sorted((REPOSITORY_ROOT / ".github/workflows").glob("*.yml")):
        for name, revision in action.findall(workflow.read_text(encoding="utf-8")):
            if not re.fullmatch(r"[0-9a-f]{40}", revision):
                failures.append(f"{workflow.name}: {name}@{revision}")
    assert failures == []
