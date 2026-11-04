# API Develop Studio

API Develop Studio is a self-hosted workspace for designing and testing HTTP APIs. It combines a React web interface with a Python test runner, so developers and QA engineers can turn API requests into reusable test cases and multi-step workflows.

Use it to describe an API, define its expected behavior, and check actual responses. Projects, cases, and pipelines have revision history in a local SQLite database and JSON files for command-line execution.

## What you can do

- **Design APIs:** Import OpenAPI or Swagger documents, draft test cases from examples, and author OpenAPI 3.x operations in the browser.
- **Configure requests:** Set parameters, headers, JSON or multipart bodies, proxies, and TLS verification. Reuse project variables and encrypted project or case secrets.
- **Validate responses:** Check HTTP status codes, compare JSON bodies, and apply field conditions for ranges, types, presence, length, and string formats.
- **Build test workflows:** Chain cases into pipelines with retries and values passed from earlier responses into later URLs, headers, or bodies.
- **Generate client SDKs:** Download clients for Python, JavaScript, TypeScript (Axios), Java, Kotlin, Go, and C# using OpenAPI Generator.
- **Track changes and results:** Keep document revisions, detect conflicting edits, and inspect execution logs with response differences and per-tag summaries.

This README describes the `main` branch. Additional work on FastAPI, PostgreSQL/Redis, asynchronous execution, contract validation, mocks, and load-test dashboards is available on the [development branch](https://github.com/OnSe-MiRo/api-develop-studio/tree/develop). See its [documentation index](https://github.com/OnSe-MiRo/api-develop-studio/blob/develop/docs/README.md) for details and implementation status.

## How it works

1. **Create a project** with a base URL and optional OpenAPI document, variables, and proxy settings.
2. **Create a case** that defines an HTTP request and the response you expect. Cases live at `case/{tag}/{api_name}/{case_file}.json`.
3. **Build a pipeline** when several requests belong to one workflow, such as creating a user and then retrieving that user by the returned ID.
4. **Run and inspect** cases or pipelines in the browser or CLI. The web editor can run unsaved changes or save them before execution.

## Quick start

### Docker Compose

Install Docker with Docker Compose, then run these commands from the repository root:

```bash
cp .env.example .env
```

Review `.env` for proxy settings and data directories, then start the services:

```bash
docker compose up --build
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). Compose starts the React development server, Python API server, and an internal encryption service. The API server is available at [http://127.0.0.1:8765](http://127.0.0.1:8765).

With the default `EXAMPLE_PROJECT=true`, select **Example API** and run the `example-api.json` pipeline. It creates a user, then retrieves that user using the returned ID. The example API runs locally and needs no external service.

Keep `.env` out of version control. Preserve the configured data directories and the `encryption_keys` volume when rebuilding; losing the key prevents decryption of existing secret variables.

Stop the services with:

```bash
docker compose down
```

### Native development

The Docker images use Python 3.12 and Node.js 22; use matching versions for local development. SDK generation also requires Java 11 or later.

Create a Python environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows PowerShell, use `python -m venv .venv` and `.venv/Scripts/Activate.ps1` instead.

Start the backend in the first terminal:

```bash
python react_server.py
```

In a second terminal, start the frontend:

```bash
cd web
npm ci
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). The development server forwards `/api` requests to the Python server at `127.0.0.1:8765`. The built-in example project is enabled by default.

Native execution does not load `.env` automatically. Set variables in the shell or service environment. To store encrypted secrets, generate a Fernet key and set `API_TEST_ENCRYPTION_KEY` before starting the server:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Keep this key across restarts and back it up separately from the data.

To serve a built frontend from the Python server, run `npm run build` inside `web/`, then open [http://127.0.0.1:8765](http://127.0.0.1:8765).

## Command-line usage

Run commands from the repository root with the Python environment activated. Keep the API server running when testing the built-in examples.

```bash
# Run the built-in example pipeline.
python run_api_tests.py pipelines/example-api.json

# Run a saved case (the path is relative to case/).
python run_api_tests.py --case example/users/get_user.json

# Run all JSON pipelines under pipelines/.
python run_api_tests.py

# Choose a timeout and log directory.
python run_api_tests.py pipelines/example-api.json --timeout 15 --log-dir test-logs
```

Use `python run_api_tests.py --help` for custom case, project, and attachment directories. Execution logs are written to `logs/` by default and include failures, response differences, and summaries by API tag. Recognized sensitive fields and resolved secret variable values are redacted in logs.

Exit codes: `0` means success, `1` means a test failure or request error, and `2` means a configuration error.

## Example test case

Create `projects/demo-api.json` with your API's base URL:

```json
{
  "name": "Demo API",
  "base_url": "https://api.example.com"
}
```

Save the following as `case/demo/users/create_user.json`:

```json
{
  "project": "demo-api.json",
  "request": {
    "method": "POST",
    "url": "/users",
    "body": { "name": "Ada" }
  },
  "expected": {
    "status": 201,
    "strict": false,
    "body": { "name": "Ada" }
  }
}
```

This case expects a `201` response and a JSON body containing `"name": "Ada"`. With `strict: false`, additional response fields such as a generated ID are allowed. Strict comparison checks the full structure, values, and types. Field assertions can be used alongside body comparison or on their own.

A pipeline references saved case paths and can pass earlier response values into later URLs, headers, or bodies. Project variables use `{{project.variable_name}}`; case-specific secrets use `{{case.variable_name}}`.

## Architecture and storage

| Component | Role |
| --- | --- |
| React + Vite | Browser workspace for API design, cases, and pipelines |
| Python HTTP server | Document management, file uploads, and execution coordination |
| Python runner | JSON-driven case and pipeline execution with assertions and logs |
| SQLite | Persistent project, case, and pipeline revisions |
| Encryption service | Secret-variable encryption in Docker Compose |
| OpenAPI Generator | Client SDK generation |

Studio saves document revisions in `data/studio.db` by default and writes the current versions to JSON for CLI compatibility. Revision checks reject conflicting edits. `STUDIO_DB_PATH` changes the database location; Compose volume settings are listed in [.env.example](.env.example).

```text
api_test/       Python test runner, storage, and encryption utilities
web/            React frontend
react_server.py HTTP server for the web workspace
run_api_tests.py Command-line entry point
projects/       Project JSON files
case/           Test cases: {tag}/{api_name}/{case_file}.json
pipelines/      Ordered test workflows
tests/          Python tests
```

Use `/` separators in stored file references on all platforms, including Windows.

## Development checks

With Python and frontend dependencies installed, run:

```bash
python -m unittest discover -s tests -v
cd web
npm run build
```

## License

[GNU Affero General Public License v3.0](LICENSE).
