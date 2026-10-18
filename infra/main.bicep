// Ecosys on Azure — everything in one resource group (the deployer is scoped to it).
//
//   Container Apps env ─┬─ web    (Next.js, public ingress)
//                       ├─ api    (FastAPI, internal ingress — only web calls it)
//                       └─ worker (arq run executor, no ingress)
//   Postgres Flexible (Entra-only, passwordless) · Azure Managed Redis · Key Vault · ACR
//   Microsoft Foundry (AIServices account + project + GPT-6 deployments) · App Insights
//   One user-assigned managed identity holds every data-plane permission.
targetScope = 'resourceGroup'

@minLength(1)
@maxLength(64)
@description('azd environment name, e.g. prod or staging')
param environmentName string

param location string = resourceGroup().location

@description('Region for Microsoft Foundry. GPT-6 Global Standard deployments are not offered in every region.')
param foundryLocation string = 'eastus2'

@description('Region for PostgreSQL. Some subscriptions are restricted from provisioning Postgres in southindia.')
param postgresLocation string = location

@description('Leave empty to create a Foundry account + project here. Set to an existing project endpoint to reuse it.')
param existingFoundryProjectEndpoint string = ''

@description('Model deployments to create when Foundry is created here. Set version to "" to take the default.')
param modelDeployments array = [
  { name: 'gpt-6-luna', model: 'gpt-6-luna', version: '', capacity: 500 }
  { name: 'gpt-6.1-sol', model: 'gpt-6.1-sol', version: '', capacity: 200 }
  { name: 'gpt-6-astra', model: 'gpt-6-astra', version: '', capacity: 50 }
]

// ---- Entra External ID (leave empty for a passcode-gated staging deploy)
param entraTenantId string = ''
param entraTenantSubdomain string = ''
param entraApiClientId string = ''
param entraWebClientId string = ''
@secure()
param entraWebClientSecret string = ''

@description('Emails that are always platform admins (comma separated).')
param bootstrapAdmins string = ''

// Images are set by azd after the first deploy; placeholders until then.
param webImageName string = ''
param apiImageName string = ''
param workerImageName string = ''

@description('Generated on first provision; later provisions reuse the value stored in Key Vault.')
@secure()
param authSecret string
@secure()
param devLoginCode string

var token = toLower(uniqueString(subscription().id, resourceGroup().id, environmentName))
var tags = { 'azd-env-name': environmentName, app: 'ecosys' }
var placeholderImage = 'mcr.microsoft.com/k8se/quickstart:latest'
var useEntra = !empty(entraTenantId)
var createFoundry = empty(existingFoundryProjectEndpoint)

// Built-in role definition ids
var roles = {
  acrPull: '7f951dda-4ed3-4680-a7ca-43fe172d538d'
  keyVaultSecretsUser: '4633458b-17de-408a-b874-0445c86b69e6'
  storageBlobDataContributor: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
  cognitiveServicesUser: 'a97b65f3-24c7-4388-baec-2e87135dc908'
  cognitiveServicesOpenAIUser: '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
  azureAIDeveloper: '64702f94-c441-49e6-a78b-ef80e0188fee'
}

// ---------------------------------------------------------------- identity & observability

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-ecosys-${token}'
  location: location
  tags: tags
}

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-ecosys-${token}'
  location: location
  tags: tags
  properties: { sku: { name: 'PerGB2018' }, retentionInDays: 30 }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-ecosys-${token}'
  location: location
  tags: tags
  kind: 'web'
  properties: { Application_Type: 'web', WorkspaceResourceId: logs.id }
}

// ---------------------------------------------------------------- registry, secrets, storage

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'crecosys${token}'
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: acr
  name: guid(acr.id, identity.id, roles.acrPull)
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.acrPull)
  }
}

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-ecosys-${take(token, 13)}'
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
  }
}

resource kvUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: vault
  name: guid(vault.id, identity.id, roles.keyVaultSecretsUser)
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.keyVaultSecretsUser)
  }
}

resource secretAuth 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'auth-secret'
  properties: { value: authSecret }
}

resource secretDevCode 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'dev-login-code'
  properties: { value: devLoginCode }
}

resource secretDevJwt 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'dev-jwt-secret'
  properties: { value: guid(authSecret, 'dev-jwt') }
}

resource secretEntraWeb 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (useEntra) {
  parent: vault
  name: 'entra-web-client-secret'
  properties: { value: entraWebClientSecret }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'stecosys${take(token, 15)}'
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    minimumTlsVersion: 'TLS1_2'
  }
}

resource blobContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, identity.id, roles.storageBlobDataContributor)
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDataContributor)
  }
}

// ---------------------------------------------------------------- data

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: 'psql-ecosys-${token}'
  location: postgresLocation
  tags: tags
  sku: { name: 'Standard_B2s', tier: 'Burstable' }
  properties: {
    version: '16'
    storage: { storageSizeGB: 32, autoGrow: 'Enabled' }
    backup: { backupRetentionDays: 7, geoRedundantBackup: 'Disabled' }
    highAvailability: { mode: 'Disabled' }
    authConfig: { activeDirectoryAuth: 'Enabled', passwordAuth: 'Disabled', tenantId: subscription().tenantId }
  }
}

resource postgresDb 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgres
  name: 'ecosys'
  properties: { charset: 'UTF8', collation: 'en_US.utf8' }
}

resource postgresAllowAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  parent: postgres
  name: 'AllowAzureServices'
  properties: { startIpAddress: '0.0.0.0', endIpAddress: '0.0.0.0' }
}

// The app identity is the Entra admin, so it connects without any password.
module postgresAdmin 'modules/postgres-admin.bicep' = {
  name: 'postgres-admin'
  dependsOn: [postgresDb, postgresAllowAzure]
  params: { serverName: postgres.name, principalId: identity.properties.principalId, principalName: identity.name }
}

resource redis 'Microsoft.Cache/redisEnterprise@2026-09-01' = {
  name: 'redis-ecosys-${token}'
  location: location
  tags: tags
  sku: { name: 'Balanced_B0' }
  properties: { minimumTlsVersion: '1.2', publicNetworkAccess: 'Enabled' }
}

resource redisDb 'Microsoft.Cache/redisEnterprise/databases@2026-09-01' = {
  parent: redis
  name: 'default'
  properties: {
    clientProtocol: 'Encrypted'
    port: 10000
    clusteringPolicy: 'NoCluster'
    evictionPolicy: 'NoEviction'
    accessKeysAuthentication: 'Enabled'
  }
}

var redisUrl = 'rediss://:${redisDb.listKeys().primaryKey}@${redis.properties.hostName}:10000/0'

// ---------------------------------------------------------------- Microsoft Foundry

resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' = if (createFoundry) {
  name: 'aif-ecosys-${token}'
  location: foundryLocation
  tags: tags
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: 'aif-ecosys-${token}'
    allowProjectManagement: true
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: true
  }
}

resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = if (createFoundry) {
  parent: foundry
  name: 'ecosys'
  location: foundryLocation
  identity: { type: 'SystemAssigned' }
  properties: { displayName: 'Ecosys learning platform', description: 'Learner runs, critique and coach' }
}

@batchSize(1)
resource deployments 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = [
  for d in (createFoundry ? modelDeployments : []): {
    parent: foundry
    name: d.name
    // Writing deployments while the project is still being created fails with RequestConflict.
    dependsOn: [foundryProject]
    sku: { name: 'GlobalStandard', capacity: d.capacity }
    properties: {
      model: empty(d.version) ? { format: 'OpenAI', name: d.model } : { format: 'OpenAI', name: d.model, version: d.version }
      versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
    }
  }
]

var foundryRoleIds = [roles.cognitiveServicesUser, roles.cognitiveServicesOpenAIUser, roles.azureAIDeveloper]
resource foundryRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for r in (createFoundry ? foundryRoleIds : []): {
    scope: foundry
    name: guid(foundry.id, identity.id, r)
    properties: {
      principalId: identity.properties.principalId
      principalType: 'ServicePrincipal'
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', r)
    }
  }
]

var foundryEndpoint = createFoundry
  ? 'https://${foundry!.properties.customSubDomainName}.services.ai.azure.com/api/projects/${foundryProject.name}'
  : existingFoundryProjectEndpoint

// ---------------------------------------------------------------- Container Apps

resource cae 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-ecosys-${token}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: { customerId: logs.properties.customerId, sharedKey: logs.listKeys().primarySharedKey }
    }
    workloadProfiles: [{ name: 'Consumption', workloadProfileType: 'Consumption' }]
  }
}

var databaseUrl = 'postgresql+asyncpg://${identity.name}@${postgres.properties.fullyQualifiedDomainName}:5432/ecosys?ssl=require'

var apiEnv = [
  { name: 'ENV', value: useEntra ? 'prod' : 'dev' }
  { name: 'DATABASE_URL', value: databaseUrl }
  { name: 'DATABASE_ENTRA_USER', value: identity.name }
  { name: 'REDIS_URL', secretRef: 'redis-url' }
  { name: 'MODEL_PROVIDER', value: 'foundry' }
  { name: 'FOUNDRY_PROJECT_ENDPOINT', value: foundryEndpoint }
  { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
  { name: 'AUTH_MODE', value: useEntra ? 'entra' : 'dev' }
  { name: 'DEV_JWT_SECRET', secretRef: 'dev-jwt-secret' }
  { name: 'ENTRA_TENANT_ID', value: entraTenantId }
  { name: 'ENTRA_TENANT_SUBDOMAIN', value: entraTenantSubdomain }
  { name: 'ENTRA_API_CLIENT_ID', value: entraApiClientId }
  { name: 'BOOTSTRAP_ADMINS', value: bootstrapAdmins }
  { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
]

var apiSecrets = [
  { name: 'redis-url', value: redisUrl }
  { name: 'dev-jwt-secret', keyVaultUrl: secretDevJwt.properties.secretUri, identity: identity.id }
]

resource api 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-api-${token}'
  location: location
  tags: union(tags, { 'azd-service-name': 'api' })
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${identity.id}': {} } }
  dependsOn: [acrPull, kvUser, postgresAdmin]
  properties: {
    environmentId: cae.id
    workloadProfileName: 'Consumption'
    configuration: {
      ingress: { external: false, targetPort: 8000, transport: 'http' }
      registries: [{ server: acr.properties.loginServer, identity: identity.id }]
      secrets: apiSecrets
    }
    template: {
      containers: [
        {
          name: 'api'
          image: empty(apiImageName) ? placeholderImage : apiImageName
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: apiEnv
          probes: [
            { type: 'Readiness', httpGet: { path: '/healthz', port: 8000 }, initialDelaySeconds: 10, periodSeconds: 10 }
          ]
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 6, rules: [{ name: 'http', http: { metadata: { concurrentRequests: '60' } } }] }
    }
  }
}

resource worker 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-worker-${token}'
  location: location
  tags: union(tags, { 'azd-service-name': 'worker' })
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${identity.id}': {} } }
  dependsOn: [acrPull, kvUser, postgresAdmin]
  properties: {
    environmentId: cae.id
    workloadProfileName: 'Consumption'
    configuration: {
      registries: [{ server: acr.properties.loginServer, identity: identity.id }]
      secrets: apiSecrets
    }
    template: {
      containers: [
        {
          name: 'worker'
          image: empty(workerImageName) ? placeholderImage : workerImageName
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: concat(apiEnv, [{ name: 'ROLE', value: 'worker' }])
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 4 }
    }
  }
}

var webSecrets = concat(
  [
    { name: 'auth-secret', keyVaultUrl: secretAuth.properties.secretUri, identity: identity.id }
    { name: 'dev-jwt-secret', keyVaultUrl: secretDevJwt.properties.secretUri, identity: identity.id }
    { name: 'dev-login-code', keyVaultUrl: secretDevCode.properties.secretUri, identity: identity.id }
  ],
  useEntra ? [{ name: 'entra-web-secret', keyVaultUrl: secretEntraWeb!.properties.secretUri, identity: identity.id }] : []
)

var webEnv = concat(
  [
    { name: 'API_URL', value: 'https://${api.properties.configuration.ingress.fqdn}' }
    { name: 'AUTH_SECRET', secretRef: 'auth-secret' }
    { name: 'AUTH_TRUST_HOST', value: 'true' }
    { name: 'DEV_JWT_SECRET', secretRef: 'dev-jwt-secret' }
  ],
  useEntra
    ? [
        { name: 'AUTH_MICROSOFT_ENTRA_ID_ID', value: entraWebClientId }
        { name: 'AUTH_MICROSOFT_ENTRA_ID_SECRET', secretRef: 'entra-web-secret' }
        { name: 'AUTH_MICROSOFT_ENTRA_ID_ISSUER', value: 'https://${entraTenantId}.ciamlogin.com/${entraTenantId}/v2.0' }
        { name: 'ENTRA_API_SCOPE', value: 'api://${entraApiClientId}/access_as_user' }
      ]
    : [
        { name: 'AUTH_DEV_LOGIN', value: 'true' }
        { name: 'AUTH_DEV_LOGIN_CODE', secretRef: 'dev-login-code' }
      ]
)

resource web 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-web-${token}'
  location: location
  tags: union(tags, { 'azd-service-name': 'web' })
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${identity.id}': {} } }
  dependsOn: [acrPull, kvUser]
  properties: {
    environmentId: cae.id
    workloadProfileName: 'Consumption'
    configuration: {
      ingress: { external: true, targetPort: 3000, transport: 'http' }
      registries: [{ server: acr.properties.loginServer, identity: identity.id }]
      secrets: webSecrets
    }
    template: {
      containers: [
        {
          name: 'web'
          image: empty(webImageName) ? placeholderImage : webImageName
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: webEnv
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 6, rules: [{ name: 'http', http: { metadata: { concurrentRequests: '80' } } }] }
    }
  }
}

// ---------------------------------------------------------------- outputs (read by azd)

output AZURE_CONTAINER_REGISTRY_ENDPOINT string = acr.properties.loginServer
output AZURE_KEY_VAULT_NAME string = vault.name
output WEB_URL string = 'https://${web.properties.configuration.ingress.fqdn}'
output FOUNDRY_PROJECT_ENDPOINT string = foundryEndpoint
output POSTGRES_HOST string = postgres.properties.fullyQualifiedDomainName
output AZURE_MANAGED_IDENTITY_NAME string = identity.name
output AUTH_MODE string = useEntra ? 'entra' : 'staging-passcode'
