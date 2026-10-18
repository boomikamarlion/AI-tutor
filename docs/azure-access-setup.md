# Giving the Claude Code cloud session Azure access

Do this once. Afterwards Claude can run `az` / `azd` in a new session and build and deploy
on its own.

## 1. Create a deployment identity (Azure Cloud Shell, ~3 minutes)

Open https://shell.azure.com (Bash) while signed in to the subscription that holds the
Founders Hub credits, then run:

```bash
SUB_ID=$(az account show --query id -o tsv)
RG=rg-ecosys-prod
LOCATION=southindia          # Chennai. Use centralindia (Pune) if a service isn't offered here.

az group create -n $RG -l $LOCATION

# Resource providers are registered per subscription, which the deployer below is not
# allowed to do. Register the ones the templates use that a new subscription may lack.
for ns in Microsoft.Cache Microsoft.App Microsoft.DBforPostgreSQL Microsoft.CognitiveServices \
          Microsoft.ContainerRegistry Microsoft.KeyVault Microsoft.OperationalInsights; do
  az provider register -n $ns --wait
done

# Service principal that Claude will log in as, scoped to this resource group only.
az ad sp create-for-rbac \
  --name sp-ecosys-claude-deployer \
  --role Contributor \
  --scopes /subscriptions/$SUB_ID/resourceGroups/$RG \
  --query "{AZURE_CLIENT_ID:appId, AZURE_CLIENT_SECRET:password, AZURE_TENANT_ID:tenant}" -o json

# The Bicep templates give the app's managed identity access to Foundry, Key Vault and
# Storage, which needs permission to create role assignments. Scope it to the resource group.
APP_ID=$(az ad sp list --display-name sp-ecosys-claude-deployer --query "[0].appId" -o tsv)
az role assignment create --assignee $APP_ID \
  --role "Role Based Access Control Administrator" \
  --scope /subscriptions/$SUB_ID/resourceGroups/$RG

# Lets the deployer smoke-test the model deployments.
# ("Azure AI User" is not available in every tenant; these two cover the same need.)
az role assignment create --assignee $APP_ID --role "Cognitive Services OpenAI User" \
  --scope /subscriptions/$SUB_ID/resourceGroups/$RG
az role assignment create --assignee $APP_ID --role "Azure AI Developer" \
  --scope /subscriptions/$SUB_ID/resourceGroups/$RG

echo "AZURE_SUBSCRIPTION_ID=$SUB_ID"
```

Keep the JSON output somewhere safe. Never paste the secret into a chat.

If your Foundry project (with the GPT-6 Astra / GPT-6.1 Sol deployments) is in a
**different** resource group, also run the two model-access assignments with that group as
`--scope`, or tell Claude to create a new Foundry project inside `rg-ecosys-prod`.

## 2. Add the credentials to the cloud environment

In Claude Code on the web, open the cloud environment menu in the session's title bar →
**Edit** → environment variables, and add:

```
AZURE_CLIENT_ID=<appId>
AZURE_CLIENT_SECRET=<password>
AZURE_TENANT_ID=<tenant>
AZURE_SUBSCRIPTION_ID=<subscription id>
AZURE_RESOURCE_GROUP=rg-ecosys-prod
AZURE_LOCATION=southindia
```

PostgreSQL defaults to `centralindia` (`POSTGRES_LOCATION`), because some subscriptions are
restricted from creating Postgres servers in `southindia`. Check yours with
`az postgres flexible-server list-skus -l southindia`; if it lists versions, you can set
`azd env set POSTGRES_LOCATION southindia`.

## 3. Allow Azure hosts in the environment's network access

In the same **Edit** screen → **Network access**, keep "Allow package managers" ticked and
add these allowed domains:

```
login.microsoftonline.com
management.azure.com
graph.microsoft.com
*.azure.com
*.azure.net
*.microsoft.com
*.windows.net
*.azurecr.io
*.ciamlogin.com
*.cognitiveservices.azure.com
*.openai.azure.com
*.services.ai.azure.com
aka.ms
github.com
objects.githubusercontent.com
```

## 4. Start a new session

Environment changes apply only to sessions started after the change. In the new session,
ask Claude to "deploy to Azure". It will run:

```bash
az login --service-principal -u $AZURE_CLIENT_ID -p $AZURE_CLIENT_SECRET --tenant $AZURE_TENANT_ID
azd auth login --client-id $AZURE_CLIENT_ID --client-secret $AZURE_CLIENT_SECRET --tenant-id $AZURE_TENANT_ID
azd env new prod && azd up
```

## What still needs a human (one time)

- **Entra External ID tenant.** Creating a new external tenant is a portal action:
  Microsoft Entra admin center → Overview → Manage tenants → Create → **External**.
  Then add the deployer's app as an **Application Administrator** in that tenant (or give
  Claude a second service principal created there) so it can register the web/API apps,
  app roles and the sign-up user flow by script.
- **Model quota.** If `gpt-6-luna` isn't deployed yet and quota is short, request it in
  Foundry → Quotas. Until then the router falls back to `gpt-6.1-sol` (see `config/models.yaml`).
