#!/usr/bin/env bash
# One-time AWS setup for Finvia. Run in AWS CloudShell (or any shell logged in
# to the target AWS account with admin rights):
#
#   bash aws/setup.sh <github-owner>/<github-repo> [aws-region]
#   e.g. bash aws/setup.sh tsungyu/finvia ap-southeast-1
#
# Safe to re-run: resources that already exist are left alone.
set -euo pipefail

REPO_SLUG="${1:?Usage: bash aws/setup.sh <github-owner>/<github-repo> [aws-region]}"
REGION="${2:-ap-southeast-1}"
ECR_REPO="finvia"
ENVIRONMENT="production"          # must match `environment:` in the workflow
GH_ROLE="github-actions-ecs-role"
EXEC_ROLE="ecsTaskExecutionRole"
INFRA_ROLE="ecsInfrastructureRoleForExpressServices"

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
echo "Account: $ACCOUNT_ID  Region: $REGION  Repo: $REPO_SLUG"

# 1) ECR repository
aws ecr describe-repositories --repository-names "$ECR_REPO" --region "$REGION" >/dev/null 2>&1 \
  || aws ecr create-repository --repository-name "$ECR_REPO" --region "$REGION" \
       --image-scanning-configuration scanOnPush=true >/dev/null
echo "ECR repository ready: $ECR_REPO"

# 2) GitHub OIDC identity provider
OIDC_ARN="arn:aws:iam::${ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
aws iam get-open-id-connect-provider --open-id-connect-provider-arn "$OIDC_ARN" >/dev/null 2>&1 \
  || aws iam create-open-id-connect-provider \
       --url https://token.actions.githubusercontent.com \
       --client-id-list sts.amazonaws.com \
       --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 >/dev/null
echo "GitHub OIDC provider ready"

create_role () {  # name, trust-policy-json
  aws iam get-role --role-name "$1" >/dev/null 2>&1 \
    || aws iam create-role --role-name "$1" --assume-role-policy-document "$2" >/dev/null
}

# 3) Role GitHub Actions assumes (trusted only for THIS repo + the production environment)
GH_TRUST=$(cat <<JSON
{"Version":"2012-10-17","Statement":[{"Effect":"Allow",
 "Principal":{"Federated":"${OIDC_ARN}"},
 "Action":"sts:AssumeRoleWithWebIdentity",
 "Condition":{"StringEquals":{"token.actions.githubusercontent.com:aud":"sts.amazonaws.com",
   "token.actions.githubusercontent.com:sub":"repo:${REPO_SLUG}:environment:${ENVIRONMENT}"}}}]}
JSON
)
create_role "$GH_ROLE" "$GH_TRUST"
aws iam update-assume-role-policy --role-name "$GH_ROLE" --policy-document "$GH_TRUST"

GH_POLICY=$(cat <<JSON
{"Version":"2012-10-17","Statement":[
 {"Effect":"Allow","Action":"ecr:GetAuthorizationToken","Resource":"*"},
 {"Effect":"Allow","Action":["ecr:BatchCheckLayerAvailability","ecr:BatchGetImage","ecr:GetDownloadUrlForLayer",
   "ecr:InitiateLayerUpload","ecr:UploadLayerPart","ecr:CompleteLayerUpload","ecr:PutImage","ecr:DescribeImages"],
  "Resource":"arn:aws:ecr:${REGION}:${ACCOUNT_ID}:repository/${ECR_REPO}"},
 {"Effect":"Allow","Action":["ecs:CreateCluster","ecs:RegisterTaskDefinition","ecs:CreateExpressGatewayService",
   "ecs:UpdateExpressGatewayService","ecs:DescribeExpressGatewayService","ecs:DescribeClusters","ecs:DescribeServices",
   "ecs:ListServiceDeployments","ecs:DescribeServiceDeployments","ecs:TagResource","ecs:UntagResource"],"Resource":"*"},
 {"Effect":"Allow","Action":"iam:PassRole",
  "Resource":["arn:aws:iam::${ACCOUNT_ID}:role/${EXEC_ROLE}","arn:aws:iam::${ACCOUNT_ID}:role/${INFRA_ROLE}"]}]}
JSON
)
aws iam put-role-policy --role-name "$GH_ROLE" --policy-name finvia-deploy --policy-document "$GH_POLICY"
echo "GitHub Actions role ready: $GH_ROLE"

# 4) ECS task execution role (pulls the image from ECR, writes logs)
create_role "$EXEC_ROLE" '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
aws iam attach-role-policy --role-name "$EXEC_ROLE" --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

# 5) ECS Express Mode infrastructure role (creates the load balancer, security groups, ...)
create_role "$INFRA_ROLE" '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
aws iam attach-role-policy --role-name "$INFRA_ROLE" --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices
echo "ECS roles ready"

cat <<OUT

============================================================
AWS is ready. Now add these in GitHub:
  Settings > Secrets and variables > Actions > Variables > New repository variable

  AWS_REGION      = ${REGION}
  AWS_ACCOUNT_ID  = ${ACCOUNT_ID}
  ECR_REPOSITORY  = ${ECR_REPO}
  ECS_CLUSTER     = default
  ECS_SERVICE     = finvia

And create an Environment named:  ${ENVIRONMENT}
  (Settings > Environments > New environment)

Then push to main (or run the workflow manually from the Actions tab).
============================================================
OUT
