# Deploying tri-coach to Azure Container Apps

Two templates, deployed in order, because the container app cannot start until
its Key Vault secrets have values.

- `main.bicep` — ACR, Key Vault, user-assigned identity + role assignments,
  Log Analytics, Container Apps environment.
- `app.bicep` — the container app itself.

## 1. Resource group + platform

```bash
az group create -n tri-coach -l westeurope
az deployment group create -g tri-coach -f infra/main.bicep -p infra/main.bicepparam
az deployment group show -g tri-coach -n main --query properties.outputs
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

shred -u ./vault_deploy   # the private half now lives only in Key Vault
```

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

## Things that will bite

- **Never raise `maxReplicas` above 1.** Telegram permits one `getUpdates` poller
  per token; a second replica makes both fail with 409 Conflict.
- **The vault is re-cloned on every cold start.** Replica storage is ephemeral, and
  that is deliberate: git is the source of truth and the repo is small markdown.
  Anything the agent had written but not yet pushed is lost on a restart.
- **Changing a Key Vault secret does not restart the app.** Deploy a new revision
  or restart the current one to pick up a rotated value.
