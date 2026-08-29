using './app.bicep'

// Fill these from `az deployment group show` outputs of main.bicep.
param environmentId = ''
param identityId = ''
param acrLoginServer = ''
param keyVaultUri = ''

param imageTag = ''

param intervalsAthleteId = 'i668762'
param telegramAllowedChatId = '8679015003'
param vaultRepo = 'git@github.com:steffanmartin/triathlon-brain.git'
param timeZone = 'Europe/Copenhagen'
