// Platform resources for tri-coach: registry, secret store, identity, and the
// Container Apps environment. Deployed as a module by main.bicep, which creates
// the resource group first — the container app itself lives in app.bicep and
// expects the Key Vault secrets to already have values.
targetScope = 'resourceGroup'

@description('Short name used as a prefix for every resource.')
param name string = 'tricoach'

@description('Region. Container Apps + ACR + Key Vault must all support it.')
param location string = resourceGroup().location

@description('Log retention. 30 days is the free-tier ceiling and plenty for one bot.')
param logRetentionDays int = 30

@description('''
GitHub OIDC subject prefix (repo:...) allowed to deploy via federation. Not
plain "owner/repo": this account has GitHub's immutable-subject default on, so
the token's actual subject embeds numeric owner/repo IDs
(`repo:<owner>@<ownerId>/<repo>@<repoId>`) — confirmed via
`gh api repos/OWNER/REPO/actions/oidc/customization/sub`, which is the source
of truth if this repo is ever renamed or forked into a new one.
''')
param githubOidcSubjectPrefix string = 'repo:steffanmartin@55839566/tri-coach@1343576713'

var uniq = uniqueString(resourceGroup().id)
var acrName = '${name}acr${uniq}'
var kvName = '${name}-kv-${substring(uniq, 0, 8)}'

// --- Identity -------------------------------------------------------------
// User-assigned rather than system-assigned: the container app needs ACR pull
// rights at *creation* time to start its first revision, and a system-assigned
// identity does not exist until after the app is created.
resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${name}-id'
  location: location
}

// --- Container registry ---------------------------------------------------
resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: acrName
  location: location
  sku: { name: 'Basic' }
  properties: {
    // Admin user is off: the app pulls with its managed identity instead, so
    // there is no registry password to leak or rotate.
    adminUserEnabled: false
  }
}

var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, identity.id, acrPullRoleId)
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// --- Secret store ---------------------------------------------------------
resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: kvName
  location: location
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    publicNetworkAccess: 'Enabled'
  }
}

var kvSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'

resource kvRead 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vault.id, identity.id, kvSecretsUserRoleId)
  scope: vault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', kvSecretsUserRoleId)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// --- CI/CD identity ---------------------------------------------------------
// GitHub Actions authenticates as this identity via OIDC federation. A
// federated credential on a user-assigned identity rather than an app
// registration: app registrations live behind Microsoft Graph, which this
// tenant's Conditional Access blocks from unmanaged devices, but federated
// credentials on a UAMI are a plain ARM resource and need no Graph access at
// all — so this can be deployed from anywhere `az` can reach the ARM API.
resource ciIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${name}-ci-id'
  location: location
}

resource ciFederatedCredential 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31' = {
  parent: ciIdentity
  name: 'github-actions-main'
  properties: {
    issuer: 'https://token.actions.githubusercontent.com'
    // Covers both `push` to main and `workflow_dispatch` run from main — GitHub
    // issues the same subject for both as long as the run is on that branch.
    subject: '${githubOidcSubjectPrefix}:ref:refs/heads/main'
    audiences: ['api://AzureADTokenExchange']
  }
}

var contributorRoleId = 'b24988ac-6180-42a0-ab88-20f7382dd24c'

resource ciContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, ciIdentity.id, contributorRoleId)
  scope: resourceGroup()
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', contributorRoleId)
    principalId: ciIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// --- Logs -----------------------------------------------------------------
resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${name}-logs'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: logRetentionDays
  }
}

// --- Container Apps environment -------------------------------------------
resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${name}-env'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
    zoneRedundant: false
  }
}

output acrName string = acr.name
output acrLoginServer string = acr.properties.loginServer
output keyVaultName string = vault.name
output keyVaultUri string = vault.properties.vaultUri
output identityId string = identity.id
output environmentId string = env.id
output ciClientId string = ciIdentity.properties.clientId
