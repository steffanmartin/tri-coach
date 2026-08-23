using './app.bicep'

// Fill these from `az deployment group show` outputs of main.bicep.
param environmentId = ''
param identityId = ''
param acrLoginServer = ''
param keyVaultUri = ''

param imageTag = ''

param intervalsAthleteId = 'i123456'
param telegramAllowedChatId = '123456789'
param vaultRepo = 'git@github.com:you/triathlon-brain.git'
param timeZone = 'Europe/Copenhagen'
