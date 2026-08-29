// Subscription-scoped entry point: creates the resource group, then deploys the
// platform resources (registry, secret store, identity, Container Apps
// environment — defined in platform.bicep) into it as a module. Deploy this
// first — the container app itself lives in app.bicep and expects the Key
// Vault secrets to already have values.
targetScope = 'subscription'

@description('Short name used as a prefix for every resource.')
param name string = 'tricoach'

@description('Region. Container Apps + ACR + Key Vault must all support it.')
param location string = 'westeurope'

@description('Resource group to create and deploy the platform resources into.')
param resourceGroupName string = 'tri-coach'

@description('Log retention. 30 days is the free-tier ceiling and plenty for one bot.')
param logRetentionDays int = 30

@description('GitHub repo (owner/name) allowed to deploy via OIDC federation.')
param githubRepo string = 'steffanmartin/tri-coach'

resource rg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: resourceGroupName
  location: location
}

module platform 'platform.bicep' = {
  name: 'platform'
  scope: rg
  params: {
    name: name
    location: location
    logRetentionDays: logRetentionDays
    githubRepo: githubRepo
  }
}

output acrName string = platform.outputs.acrName
output acrLoginServer string = platform.outputs.acrLoginServer
output keyVaultName string = platform.outputs.keyVaultName
output keyVaultUri string = platform.outputs.keyVaultUri
output identityId string = platform.outputs.identityId
output environmentId string = platform.outputs.environmentId
output ciClientId string = platform.outputs.ciClientId
