# CI/CD

CamReview uses reusable documentation workflows and a separate release workflow. A published
GitHub release builds, tests, validates, and publishes the matching Python distribution to
the Python Package Index (PyPI).

## Workflows

| Workflow | Trigger | Purpose |
| --- | --- | --- |
| `docs.yml` | Documentation changes on `main` or manual dispatch | Build and deploy the MkDocs site |
| `docs-lint.yml` | Documentation pull requests or manual dispatch | Lint Markdown, build strictly, and check external links |
| `publish.yml` | Published GitHub release | Test, build, validate, and upload the Python package |

The documentation callers delegate their implementation to the shared
[`willtheorangeguy/mkdocs`](https://github.com/willtheorangeguy/mkdocs) workflows. The release
workflow keeps distribution construction separate from publication and transfers the wheel
and source archive through a GitHub Actions artifact.

## Release contract

The GitHub release tag must equal the version in `pyproject.toml`, with an optional leading
`v`. For version `1.0.1`, publish a release tagged `v1.0.1` or `1.0.1`. A mismatch fails before
dependencies are installed or artifacts are uploaded.

The build job runs this sequence on Python 3.12:

```bash
python -m pip install --upgrade build twine ".[dev]"
python -m pytest -q
python -m build
python -m twine check dist/*
```

It produces both `camreview-VERSION-py3-none-any.whl` and
`camreview-VERSION.tar.gz`. `twine check` validates package metadata and the rendered README.

## Trusted Publishing

The publish job uses PyPI Trusted Publishing through OpenID Connect (OIDC). It has
`id-token: write`, runs in the `pypi` GitHub environment, and passes no long-lived PyPI token
to the action. PyPI must trust this exact identity:

| Field | Value |
| --- | --- |
| PyPI project | `camreview` |
| GitHub owner | `willtheorangeguy` |
| Repository | `camera-review` |
| Workflow | `publish.yml` |
| Environment | `pypi` |

Configure that publisher in PyPI before publishing the first GitHub release. The first
successful pending-publisher upload creates the project. Later releases use the normal
publisher attached to the project.

## Publish a release

1. Update the version in both `pyproject.toml` and `camreview/__init__.py`.
2. Run the tests and distribution checks shown above.
3. Commit and push the release revision to `main`.
4. Publish a GitHub release whose tag matches the package version.
5. Approve the `pypi` environment deployment if environment protection requires it.
6. Verify the release from a clean environment with `python -m pip install camreview`.

PyPI doesn't permit replacing a file for an existing project version. If an upload is wrong,
increment the version and publish a new release rather than rerunning the same version.
