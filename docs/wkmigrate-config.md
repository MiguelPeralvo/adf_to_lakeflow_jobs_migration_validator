# wkmigrate Repository & Branch Configuration

The Lakeflow Migration Validator uses [wkmigrate](https://github.com/MiguelPeralvo/wkmigrate)
to translate ADF pipelines into Databricks Lakeflow Jobs. You can configure which
wkmigrate repository and branch the validator uses for translation.

## Configured Repositories

Two repositories are configured by default:

| Repository | Default Branch | Description |
|---|---|---|
| `MiguelPeralvo/wkmigrate` | `alpha` | Primary development repository |
| `ghanse/wkmigrate` | `main` | Contributor fork |

Additional repositories can be added via the API.

## How to Configure

### Via the UI

1. Navigate to **Batch Validation** page
2. Click the **wkmigrate** config bar (shows current repo @ branch)
3. Select a repository from the dropdown — branches load automatically from GitHub
4. Select a branch (ordered by recency)
5. Click **Save Config**

### Via the API

```bash
# Get current config
curl http://localhost:8000/api/config/wkmigrate

# Set active repo + branch
curl -X POST http://localhost:8000/api/config/wkmigrate \
  -H 'Content-Type: application/json' \
  -d '{"active_repo": "https://github.com/MiguelPeralvo/wkmigrate", "active_branch": "alpha"}'

# List branches for a repo (fetched from GitHub API)
curl "http://localhost:8000/api/config/wkmigrate/branches?repo_url=https://github.com/MiguelPeralvo/wkmigrate"

# Add a new repository
curl -X POST http://localhost:8000/api/config/wkmigrate \
  -H 'Content-Type: application/json' \
  -d '{"repos": [
    {"url": "https://github.com/MiguelPeralvo/wkmigrate", "default_branch": "alpha"},
    {"url": "https://github.com/ghanse/wkmigrate", "default_branch": "main"},
    {"url": "https://github.com/youruser/wkmigrate", "default_branch": "main"}
  ]}'
```

## Applying Changes

**Important:** Changing the repo/branch in the config stores the selection but
does NOT hot-swap the running wkmigrate package. To apply changes:

1. Save the config via the UI or API
2. Install the desired version:
   ```bash
   pip install -e "git+https://github.com/MiguelPeralvo/wkmigrate@alpha#egg=wkmigrate"
   ```
3. Restart the server

## Synthetic Output Folder Structure

Each synthetic generation run produces a batch directory:

```
/tmp/lmv_synthetic/{timestamp}/
    suite.json                          # Full suite (loadable by batch validation)
    000_pipeline_name/
        adf_pipeline.json               # Raw ADF JSON for this pipeline
    001_another_pipeline/
        adf_pipeline.json
    ...
```

### Linking Synthetic → Batch Validation

1. Generate pipelines on the **Synthetic** page
2. Click **Run Batch Validation** on the results
3. The Batch Validation page opens with the folder pre-filled
4. Click **Run Batch Validation** to score all generated pipelines

Alternatively, past synthetic runs appear in the **Recent Synthetic Runs** panel
on the Batch Validation page — click any run to select it.

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/config/wkmigrate` | GET | Current repo/branch config |
| `/api/config/wkmigrate` | POST | Update active repo/branch |
| `/api/config/wkmigrate/branches` | GET | List GitHub branches for a repo |
| `/api/synthetic/runs` | GET | List past synthetic generation runs |
| `/api/validate/folder` | POST | Batch validate all JSON files in a folder |
