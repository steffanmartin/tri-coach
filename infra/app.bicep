// The tri-coach container app. Deploy after main.bicep, and after the four Key
// Vault secrets below have real values — the app fails to start a revision if a
// referenced secret does not exist yet.
targetScope = 'resourceGroup'

param name string = 'tricoach'
param location string = resourceGroup().location

@description('From main.bicep outputs.')
param environmentId string
param identityId string
param acrLoginServer string
param keyVaultUri string

@description('Image tag. Avoid "latest" — a fixed tag is what makes a rollback possible.')
param imageTag string

// --- Non-secret configuration --------------------------------------------
param coachModel string = 'claude-sonnet-5'
param plannerModel string = 'claude-opus-5'
param intervalsAthleteId string
param telegramAllowedChatId string
param vaultRepo string
param gitAuthorName string = 'tri-coach'
param gitAuthorEmail string = 'coach@localhost'
param timeZone string = 'Europe/Copenhagen'
param dailyBriefHour int = 6
param dailyBriefMinute int = 30

// Key Vault secret names. Values are set out-of-band with `az keyvault secret set`
// so no secret ever passes through a template, a parameter file, or a deployment
// history entry.
var secretNames = {
  anthropic: 'anthropic-api-key'
  intervals: 'intervals-api-key'
  telegram: 'telegram-bot-token'
  vaultSshKey: 'vault-ssh-key'
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${name}-bot'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identityId}': {} }
  }
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      activeRevisionsMode: 'Single'
      // No ingress at all. The bot long-polls Telegram outbound and serves
      // nothing, so there is no port to expose and no public surface to defend.
      registries: [
        {
          server: acrLoginServer
          identity: identityId
        }
      ]
      secrets: [
        {
          name: secretNames.anthropic
          keyVaultUrl: '${keyVaultUri}secrets/${secretNames.anthropic}'
          identity: identityId
        }
        {
          name: secretNames.intervals
          keyVaultUrl: '${keyVaultUri}secrets/${secretNames.intervals}'
          identity: identityId
        }
        {
          name: secretNames.telegram
          keyVaultUrl: '${keyVaultUri}secrets/${secretNames.telegram}'
          identity: identityId
        }
        {
          name: secretNames.vaultSshKey
          keyVaultUrl: '${keyVaultUri}secrets/${secretNames.vaultSshKey}'
          identity: identityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'coach'
          image: '${acrLoginServer}/tri-coach:${imageTag}'
          resources: {
            // 2 vCPU / 4Gi is the top of the Consumption profile and the smallest
            // size that fits the Claude Code CLI plus the bot plus the MCP server.
            cpu: json('2.0')
            memory: '4.0Gi'
          }
          env: [
            { name: 'ANTHROPIC_API_KEY', secretRef: secretNames.anthropic }
            { name: 'INTERVALS_API_KEY', secretRef: secretNames.intervals }
            { name: 'TELEGRAM_BOT_TOKEN', secretRef: secretNames.telegram }
            { name: 'COACH_MODEL', value: coachModel }
            { name: 'PLANNER_MODEL', value: plannerModel }
            { name: 'INTERVALS_ATHLETE_ID', value: intervalsAthleteId }
            { name: 'TELEGRAM_ALLOWED_CHAT_ID', value: telegramAllowedChatId }
            { name: 'VAULT_REPO', value: vaultRepo }
            { name: 'VAULT_PATH', value: '/vault' }
            { name: 'GIT_AUTHOR_NAME', value: gitAuthorName }
            { name: 'GIT_AUTHOR_EMAIL', value: gitAuthorEmail }
            { name: 'TZ', value: timeZone }
            { name: 'DAILY_BRIEF_CRON_HOUR', value: string(dailyBriefHour) }
            { name: 'DAILY_BRIEF_CRON_MINUTE', value: string(dailyBriefMinute) }
            // entrypoint.sh copies this to /root/.ssh and chmods it to 600.
            { name: 'VAULT_SSH_KEY_FILE', value: '/mnt/secrets/id_ed25519' }
          ]
          volumeMounts: [
            {
              volumeName: 'vault-ssh'
              mountPath: '/mnt/secrets'
            }
          ]
        }
      ]
      volumes: [
        {
          name: 'vault-ssh'
          storageType: 'Secret'
          secrets: [
            {
              secretRef: secretNames.vaultSshKey
              path: 'id_ed25519'
            }
          ]
        }
      ]
      scale: {
        // Pinned to exactly one replica, and this is not negotiable: Telegram
        // allows a single getUpdates poller per token, so a second replica makes
        // both replicas fail with 409 Conflict. minReplicas 1 also keeps the
        // 07:00 APScheduler job alive — scale-to-zero would silently kill it.
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

output appName string = app.name
