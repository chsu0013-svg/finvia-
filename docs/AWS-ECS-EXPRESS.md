# Deploying Finvia to AWS (GitHub → ECR → ECS Express Mode)

Finvia ships as **one Docker container** (FastAPI backend + the frontend). A push to `main` runs
`.github/workflows/deploy-ecs-express.yml`, which tests the code, builds the image, pushes it to
Amazon ECR and deploys it to **ECS Express Mode** (AWS creates the load balancer and HTTPS URL for you).

## One-time setup (about 10 minutes)

### 1. Put the code on GitHub
```bash
cd finvia
git remote add origin https://github.com/<owner>/<repo>.git
git push -u origin main
```
The first run of the workflow will pass the **test** job and then stop at **deploy** until step 3 is done
(it prints a clear error listing any missing GitHub variable).

### 2. Create the AWS pieces (ECR repo, GitHub trust, IAM roles)
Open **AWS CloudShell** in the account/region you want to use, upload or paste `aws/setup.sh`, then:
```bash
bash aws/setup.sh <owner>/<repo> ap-southeast-1
```
It creates the ECR repository `finvia`, the GitHub OIDC provider, `github-actions-ecs-role`
(trusted **only** for your repo's `production` environment), `ecsTaskExecutionRole` and
`ecsInfrastructureRoleForExpressServices`. Re-running is safe.

### 3. Add GitHub variables and the environment
In your repo: **Settings → Secrets and variables → Actions → Variables**, add the five values
the script prints (`AWS_REGION`, `AWS_ACCOUNT_ID`, `ECR_REPOSITORY`, `ECS_CLUSTER`, `ECS_SERVICE`).
Then **Settings → Environments → New environment** named `production`.

### 4. Deploy
Re-run the workflow (Actions tab → *Run workflow*) or push to `main`. When it finishes, the last
step prints the live URL (also visible in the ECS console under the Express service).

No AWS access keys are stored in GitHub — the workflow uses short-lived OIDC credentials.

## Container settings
| Setting | Value |
|---|---|
| Port | `8080` |
| Health check | `/health` |
| Tasks | exactly **1** (workspace data is held in memory per container) |
| CPU / memory | 0.5 vCPU / 1 GB |

Optional environment variables: `ALLOWED_ORIGINS` (only if the frontend is hosted elsewhere).

## Troubleshooting
- **"Could not assume role"** – the `production` environment is missing, or the repo name given to `setup.sh` doesn't exactly match `<owner>/<repo>` (case-sensitive).
- **Deployment times out** – check CloudWatch logs for the service; the container must answer `GET /health` with 200.
- **ECS_CLUSTER** – `default` is created automatically. A custom cluster name must already exist.

## Prototype limitations
Workspace state is held in memory (one private workspace per browser, lost on restart) and uploaded
files live on the container's disk. Before real SME data: add authentication, a database, object
storage, encryption, audit logging and retention rules.
