# legacy-domain-certificate-renewer

Renews certificates for legacy domain services (cdn-broker and domains-broker)

## development

Most development tasks are automated through the `dev` script. Notably:
- `./dev tests` runs tests once
- `./dev watch-tests` runs tests on a file-watcher
- `./dev update-requirements` updates requirements.txt and pip-tools/dev-requirements.txt based on pip-tools/requirements.in and pip-tools/dev-requirements.in

Code should be formatted with `black`. We have `black` config in `pyproject.toml`, so this should be as simple as `black .`.
