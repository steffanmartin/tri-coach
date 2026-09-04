# Deploying tri-coach to Azure Container Apps

Two templates, deployed in order, because the container app cannot start until
its Key Vault secrets have values.

- `main.bicep` — ACR, Key Vault, user-assigned identity + role assignments,
  Log Analytics, Container Apps environment.
- `app.bicep` — the container app itself.

## 1. Resource group + platform

`main.bicep` is subscription-scoped: it creates the `tri-coach` resource group
itself, then deploys the platform resources (`platform.bicep`) into it as a
module. No separate `az group create` step.

```bash
az deployment sub create -l westeurope -f infra/main.bicep -p infra/main.bicepparam
az deployment sub show -n main --query properties.outputs
```

## 2. Build and push the image

Container Apps runs `linux/amd64` only. `az acr build` builds server-side, so this
is correct even from an Apple Silicon Mac:

```bash
ACR=$(az deployment group show -g tri-coach -n main --query properties.outputs.acrName.value -o tsv)
TAG=$(git rev-parse --short HEAD)
az acr build -r "$ACR" -t tri-coach:$TAG --platform linux/amd64 .
```

## 3. Load the secrets

Generate a deploy key and add the **public** half to the `triathlon-brain` repo
under Settings → Deploy keys, with **write access**:

```bash
ssh-keygen -t ed25519 -f ./vault_deploy -N ""
KV=$(az deployment group show -g tri-coach -n main --query properties.outputs.keyVaultName.value -o tsv)

az keyvault secret set --vault-name "$KV" -n vault-ssh-key   --file ./vault_deploy
az keyvault secret set --vault-name "$KV" -n anthropic-api-key  --value "sk-ant-..."
az keyvault secret set --vault-name "$KV" -n intervals-api-key  --value "..."
az keyvault secret set --vault-name "$KV" -n telegram-bot-token --value "123456:ABC..."
```

The Google grant, minted on a laptop with `scripts/google_auth.py` (see the
project README). Two refresh tokens from one client, and they must stay separate
— the Health API 403s a token that also carries the calendar scope:

```bash
az keyvault secret set --vault-name "$KV" -n google-health-client-id      --value "....apps.googleusercontent.com"
az keyvault secret set --vault-name "$KV" -n google-health-client-secret  --value "..."
az keyvault secret set --vault-name "$KV" -n google-health-refresh-token   --value "1//..."   # --scopes health
az keyvault secret set --vault-name "$KV" -n google-calendar-refresh-token --value "1//..."   # --scopes calendar
```

Without these four the container starts fine and the coach answers messages, but
the 06:15 wellness sync dies on `GOOGLE_HEALTH_REFRESH_TOKEN` every morning and
the calendar snapshot quietly goes stale — the sync is the agent's only source of
HRV, resting HR, sleep and steps.

Setting secrets requires **Key Vault Secrets Officer** on the vault for *you* —
the template grants the app's identity read access, not your user account:

```bash
az role assignment create --role "Key Vault Secrets Officer" \
  --assignee $(az ad signed-in-user show --query id -o tsv) \
  --scope $(az keyvault show -n "$KV" --query id -o tsv)
```

## 4. Deploy the app

Fill `infra/app.bicepparam` with the outputs from step 1 and the tag from step 2:

```bash
az deployment group create -g tri-coach -f infra/app.bicep -p infra/app.bicepparam
az containerapp logs show -g tri-coach -n tricoach-bot --follow
```

## Verify

- Logs show `vault: cloning` once, then the bot polling with no traceback.
- `/status` in Telegram returns CTL/ATL/TSB — proves the SDK path and the
  intervals.icu MCP both work.
- `/today` returns a readiness call — proves the skills were found at
  `/vault/.claude`, which is what `entrypoint.sh` puts in place.
- A commit authored by `tri-coach` appears in the vault repo — proves the deploy
  key and the push path.

## Redeploying after a code change

```bash
TAG=$(git rev-parse --short HEAD)
az acr build -r "$ACR" -t tri-coach:$TAG --platform linux/amd64 .
az deployment group create -g tri-coach -f infra/app.bicep -p infra/app.bicepparam -p imageTag=$TAG
```

A new tag creates a new revision; `activeRevisionsMode: Single` retires the old
one automatically.

## CI deploy

`.github/workflows/deploy.yml` runs the "build, push, redeploy" sequence above
on every push to `main` (and on manual dispatch). It authenticates to Azure
via OIDC — no client secret to rotate — so it needs a one-time setup:

```bash
APP_ID=$(az ad app create --display-name tri-coach-gha --query appId -o tsv)
az ad sp create --id "$APP_ID"

az ad app federated-credential create --id "$APP_ID" --parameters '{
  "name": "tri-coach-main",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:<owner>/<repo>:ref:refs/heads/main",
  "audiences": ["api://AzureADTokenExchange"]
}'

az role assignment create --assignee "$APP_ID" --role Contributor \
  --scope "$(az group show -n tri-coach --query id -o tsv)"
```

Then set these as GitHub Actions repo secrets:

- `AZURE_CLIENT_ID` — the `$APP_ID` above
- `AZURE_TENANT_ID` — `az account show --query tenantId -o tsv`
- `AZURE_SUBSCRIPTION_ID` — `az account show --query id -o tsv`

The workflow reads `acrName`, `acrLoginServer`, `environmentId`, `identityId`,
and `keyVaultUri` from the `platform` deployment's outputs at run time (`az
deployment group show -n platform`), so nothing from step 1 needs to be
duplicated as a secret. It still expects `infra/app.bicepparam` to carry the
non-secret config (`intervalsAthleteId`, `telegramAllowedChatId`, `vaultRepo`,
etc.) and the Key Vault secrets from step 3 to already exist.

## CI infra deploy

A push to `main` that touches `infra/` runs `.github/workflows/infra.yml`
first, and `deploy.yml` only builds and ships the image once it succeeds — so
a template change and the code change that depends on it land in one push. A
push that leaves `infra/` alone skips it entirely; `workflow_dispatch` always
runs it.

That workflow deploys **`platform.bicep` at resource-group scope**, not
`main.bicep`: `main.bicep` is subscription-scoped and creates the resource
group, which the CI identity has no rights to do. The resource group already
exists, and the deployment is named `platform` — the same name `main.bicep`'s
module produces — so the outputs stay in exactly one place. `app.bicep` is not
deployed there; `deploy.yml` still owns it, because it needs the image tag it
has just built.

It authenticates as the same `tricoach-ci-id` identity (`secrets: inherit`
passes the three `AZURE_*` secrets through), but Contributor is not enough on
its own: `platform.bicep` contains four role assignments, and Contributor
cannot write those. Grant the CI identity RBAC rights on the resource group
once:

```bash
az role assignment create \
  --assignee-object-id "$(az identity show -g rg-tri-coach -n tricoach-ci-id --query principalId -o tsv)" \
  --assignee-principal-type ServicePrincipal \
  --role "Role Based Access Control Administrator" \
  --scope "$(az group show -n rg-tri-coach --query id -o tsv)"
```

Without it the platform job fails on the first `Microsoft.Authorization/roleAssignments`
resource with `AuthorizationFailed`, and `deploy.yml` stops before building —
deliberately, so a half-applied platform never gets a new revision pointed at it.

## Things that will bite

- **Never raise `maxReplicas` above 1.** Telegram permits one `getUpdates` poller
  per token; a second replica makes both fail with 409 Conflict.
- **The vault is re-cloned on every cold start.** Replica storage is ephemeral, and
  that is deliberate: git is the source of truth and the repo is small markdown.
  Anything the agent had written but not yet pushed is lost on a restart.
- **Changing a Key Vault secret does not restart the app.** Deploy a new revision
  or restart the current one to pick up a rotated value.
- **Adding config to the app means editing `app.bicep`, not just `.env`.** The
  two lists drift silently: a new var in `.env.example` that never reaches the
  `env` block here fails only on the code path that reads it, which for the
  wellness sync is once a day at 06:15.
