#!/usr/bin/env bash
# Registers Ecosys in a Microsoft Entra External ID (customer) tenant:
#   - API app  (audience for access tokens, scope access_as_user, app roles admin + author)
#   - Web app  (confidential client for Auth.js, redirect to <web-url>/api/auth/callback/microsoft-entra-id)
#   - a sign-up / sign-in user flow (email one-time passcode) linked to the web app
#
# Run it signed in to the EXTERNAL tenant (not your workforce tenant):
#   az login --tenant <external-tenant-id> --allow-no-subscriptions
#   ./scripts/setup-entra.sh https://<your-web-app-url>
# It prints the azd env values to set afterwards.
set -euo pipefail

WEB_URL="${1:?usage: setup-entra.sh <web-url>}"
TENANT_ID=$(az account show --query tenantId -o tsv)
GRAPH=https://graph.microsoft.com/v1.0

uuid() { python3 -c 'import uuid; print(uuid.uuid4())'; }

echo "Tenant: $TENANT_ID"

# ---------------------------------------------------------------- API app
SCOPE_ID=$(uuid)
ADMIN_ROLE_ID=$(uuid)
AUTHOR_ROLE_ID=$(uuid)
API_APP_ID=$(az ad app create --display-name "ecosys-api" --sign-in-audience AzureADMyOrg \
  --app-roles "[
    {\"allowedMemberTypes\":[\"User\"],\"description\":\"Platform administrators\",\"displayName\":\"Admin\",\"id\":\"$ADMIN_ROLE_ID\",\"isEnabled\":true,\"value\":\"admin\"},
    {\"allowedMemberTypes\":[\"User\"],\"description\":\"Content authors\",\"displayName\":\"Author\",\"id\":\"$AUTHOR_ROLE_ID\",\"isEnabled\":true,\"value\":\"author\"}
  ]" --query appId -o tsv)
API_OBJ_ID=$(az ad app show --id "$API_APP_ID" --query id -o tsv)
az rest --method PATCH --uri "$GRAPH/applications/$API_OBJ_ID" --headers Content-Type=application/json --body "{
  \"identifierUris\": [\"api://$API_APP_ID\"],
  \"api\": {
    \"requestedAccessTokenVersion\": 2,
    \"oauth2PermissionScopes\": [{
      \"id\": \"$SCOPE_ID\", \"value\": \"access_as_user\", \"type\": \"User\", \"isEnabled\": true,
      \"adminConsentDisplayName\": \"Use Ecosys\", \"adminConsentDescription\": \"Lets the Ecosys web app call the API as the signed-in learner.\",
      \"userConsentDisplayName\": \"Use Ecosys\", \"userConsentDescription\": \"Lets Ecosys use your learning workspace.\"
    }]
  }
}"
az ad sp create --id "$API_APP_ID" >/dev/null
echo "API app: $API_APP_ID"

# ---------------------------------------------------------------- Web app
WEB_APP_ID=$(az ad app create --display-name "ecosys-web" --sign-in-audience AzureADMyOrg \
  --web-redirect-uris "$WEB_URL/api/auth/callback/microsoft-entra-id" "http://localhost:3000/api/auth/callback/microsoft-entra-id" \
  --enable-id-token-issuance true --query appId -o tsv)
az ad app permission add --id "$WEB_APP_ID" --api "$API_APP_ID" --api-permissions "$SCOPE_ID=Scope" >/dev/null
# openid, offline_access, email, profile on Microsoft Graph
az ad app permission add --id "$WEB_APP_ID" --api 00000003-0000-0000-c000-000000000000 --api-permissions \
  37f7f235-527c-4136-accd-4a02d197296e=Scope 7427e0e9-2fba-42fe-b0c0-848c9e6a8182=Scope \
  64a6cdd6-aab1-4aaf-94b8-3cc8405e90d0=Scope 14dad69e-099b-42c9-810b-d002981feec1=Scope >/dev/null
az ad sp create --id "$WEB_APP_ID" >/dev/null
sleep 10
az ad app permission admin-consent --id "$WEB_APP_ID" || echo "! Grant admin consent for ecosys-web in the portal"
WEB_SECRET=$(az ad app credential reset --id "$WEB_APP_ID" --display-name azd --years 1 --query password -o tsv)
echo "Web app: $WEB_APP_ID"

# ---------------------------------------------------------------- user flow (email OTP sign-up / sign-in)
FLOW_ID=$(az rest --method POST --uri "$GRAPH/identity/authenticationEventsFlows" --headers Content-Type=application/json --body '{
  "@odata.type": "#microsoft.graph.externalUsersSelfServiceSignUpEventsFlow",
  "displayName": "Ecosys sign up and sign in",
  "onAuthenticationMethodLoadStart": {
    "@odata.type": "#microsoft.graph.onAuthenticationMethodLoadStartExternalUsersSelfServiceSignUp",
    "identityProviders": [{ "id": "EmailOtpSignup-OAUTH" }]
  },
  "onInteractiveAuthFlowStart": {
    "@odata.type": "#microsoft.graph.onInteractiveAuthFlowStartExternalUsersSelfServiceSignUp",
    "isSignUpAllowed": true
  },
  "onAttributeCollection": {
    "@odata.type": "#microsoft.graph.onAttributeCollectionExternalUsersSelfServiceSignUp",
    "attributes": [{ "id": "email" }, { "id": "displayName" }],
    "attributeCollectionPage": { "views": [{ "inputs": [
      { "attribute": "email", "label": "Email Address", "inputType": "text", "hidden": true, "editable": false, "writeToDirectory": true, "required": true, "validationRegEx": "^[a-zA-Z0-9.!#$%&’''*+/=?^_`{|}~-]+@[a-zA-Z0-9-]+(?:\\.[a-zA-Z0-9-]+)*$" },
      { "attribute": "displayName", "label": "Your name", "inputType": "text", "hidden": false, "editable": true, "writeToDirectory": true, "required": true, "validationRegEx": "^.*" }
    ] }] }
  }
}' --query id -o tsv) || FLOW_ID=""
if [[ -n "$FLOW_ID" ]]; then
  az rest --method POST --uri "$GRAPH/identity/authenticationEventsFlows/$FLOW_ID/conditions/applications/includeApplications" \
    --headers Content-Type=application/json --body "{\"@odata.type\":\"#microsoft.graph.authenticationConditionApplication\",\"appId\":\"$WEB_APP_ID\"}" >/dev/null
  echo "User flow: $FLOW_ID (linked to ecosys-web)"
else
  echo "! Could not create the user flow by script. Create it in the Entra admin center:"
  echo "  External Identities → User flows → New → Email one-time passcode, then add the ecosys-web application."
fi

SUBDOMAIN=$(az rest --method GET --uri "$GRAPH/domains" --query "value[?ends_with(id, '.onmicrosoft.com')].id | [0]" -o tsv | cut -d. -f1)

cat <<EOF

Done. Set these on the azd environment, then run 'azd provision':

  azd env set ENTRA_TENANT_ID $TENANT_ID
  azd env set ENTRA_TENANT_SUBDOMAIN $SUBDOMAIN
  azd env set ENTRA_API_CLIENT_ID $API_APP_ID
  azd env set ENTRA_WEB_CLIENT_ID $WEB_APP_ID
  azd env set ENTRA_WEB_CLIENT_SECRET '<printed below — store it, it is shown once>'

ENTRA_WEB_CLIENT_SECRET=$WEB_SECRET

To make someone a platform admin: Enterprise applications → ecosys-api → Users and groups → Add → role Admin.
EOF
