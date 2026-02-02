"""Sample data for the fixdoc demo command."""

from .models import Fix


# --- Sample error output strings for the tour ---

TERRAFORM_AWS_ERROR = """\
\u2502 Error: error creating S3 Bucket (my-app-data-bucket): BucketAlreadyExists:
\u2502   The requested bucket name is not available.
\u2502
\u2502   with aws_s3_bucket.data,
\u2502   on storage.tf line 12, in resource "aws_s3_bucket" "data":
\u2502   12: resource "aws_s3_bucket" "data" {
"""

SAMPLE_TERRAFORM_PLAN = {
    "format_version": "1.2",
    "terraform_version": "1.5.0",
    "resource_changes": [
        {
            "address": "aws_s3_bucket.app_data",
            "type": "aws_s3_bucket",
            "name": "app_data",
            "provider_name": "registry.terraform.io/hashicorp/aws",
            "change": {"actions": ["create"]},
        },
        {
            "address": "aws_instance.web_server",
            "type": "aws_instance",
            "name": "web_server",
            "provider_name": "registry.terraform.io/hashicorp/aws",
            "change": {"actions": ["create"]},
        },
        {
            "address": "aws_security_group.web_sg",
            "type": "aws_security_group",
            "name": "web_sg",
            "provider_name": "registry.terraform.io/hashicorp/aws",
            "change": {"actions": ["create"]},
        },
    ],
}

KUBERNETES_CRASHLOOP_ERROR = """\
NAME                     READY   STATUS             RESTARTS   AGE
api-server-7d4b8c6f9-x2 0/1     CrashLoopBackOff   5          10m

Warning  BackOff  pod/api-server-7d4b8c6f9-x2  Back-off restarting failed container
Exit Code: 1
Restart Count: 5
Namespace: production
"""


# --- Sample Fix objects for seeding ---

DEMO_TAG = "demo"


def _demo_tags(*tags: str) -> str:
    """Build a comma-separated tag string that always includes 'demo'."""
    return ",".join([DEMO_TAG, *tags])


def get_seed_fixes() -> list[Fix]:
    """Return a list of realistic sample fixes for seeding the database."""
    return [
        Fix(
            issue="Terraform AWS: S3 BucketAlreadyExists - "
            'error creating S3 Bucket (my-app-data-bucket): '
            "The requested bucket name is not available.",
            resolution="S3 bucket names are globally unique. Add a random suffix "
            "or use a naming convention with your account ID: "
            '"my-app-data-${data.aws_caller_identity.current.account_id}"',
            error_excerpt=TERRAFORM_AWS_ERROR,
            tags=_demo_tags("terraform", "aws", "s3", "aws_s3_bucket"),
            notes="File: storage.tf:12\nS3 bucket names must be globally unique "
            "across all AWS accounts.",
        ),
        Fix(
            issue="Terraform AWS: EC2 InsufficientInstanceCapacity - "
            "We currently do not have sufficient capacity in the "
            "Availability Zone you requested.",
            resolution="Try a different availability zone or instance type. "
            "Use `availability_zone` to target a specific AZ, or add "
            "multiple subnets across AZs for auto-placement.",
            error_excerpt=(
                '\u2502 Error: creating EC2 Instance: InsufficientInstanceCapacity: '
                "We currently do not have sufficient\n"
                "\u2502   capacity in the Availability Zone you requested (us-east-1a).\n"
                "\u2502\n"
                '\u2502   with aws_instance.web_server,\n'
                '\u2502   on compute.tf line 25, in resource "aws_instance" "web_server":'
            ),
            tags=_demo_tags("terraform", "aws", "ec2", "aws_instance"),
            notes="File: compute.tf:25\nThis is transient - retrying often works. "
            "Consider using launch templates with mixed instance types.",
        ),
        Fix(
            issue="Terraform Azure: StorageAccountAlreadyTaken - "
            "The storage account named myappstorage is already taken.",
            resolution="Azure storage account names are globally unique (3-24 chars, "
            "lowercase + numbers only). Use a random suffix: "
            '"myappstorage${random_string.suffix.result}"',
            error_excerpt=(
                "\u2502 Error: creating Storage Account (myappstorage): "
                "storage.AccountsClient#Create: The storage account named "
                "myappstorage is already taken.\n"
                "\u2502\n"
                '\u2502   with azurerm_storage_account.main,\n'
                '\u2502   on storage.tf line 8, in resource '
                '"azurerm_storage_account" "main":'
            ),
            tags=_demo_tags(
                "terraform", "azure", "storage", "azurerm_storage_account"
            ),
            notes="File: storage.tf:8\nStorage account names must be globally unique "
            "across all of Azure, 3-24 chars, lowercase letters and numbers only.",
        ),
        Fix(
            issue="Kubernetes: CrashLoopBackOff - "
            "pod/api-server-7d4b8c6f9-x2 in namespace production "
            "is crash-looping with exit code 1.",
            resolution="Checked logs with `kubectl logs api-server-7d4b8c6f9-x2 "
            "-n production --previous`. The app was missing the DATABASE_URL "
            "env var. Added it to the deployment spec from a ConfigMap.",
            error_excerpt=KUBERNETES_CRASHLOOP_ERROR,
            tags=_demo_tags("kubernetes", "crashloopbackoff", "pod"),
            notes="Namespace: production\nPod: api-server-7d4b8c6f9-x2\n"
            "Always check `kubectl logs --previous` for the last crash output.",
        ),
        Fix(
            issue="Kubernetes: ImagePullBackOff - "
            "Failed to pull image myregistry.io/api:v2.1.0 - "
            "unauthorized: authentication required.",
            resolution="The image pull secret was missing from the namespace. "
            "Created it with: `kubectl create secret docker-registry regcred "
            "--docker-server=myregistry.io --docker-username=... "
            "-n production` and added `imagePullSecrets` to the pod spec.",
            error_excerpt=(
                "NAME                    READY   STATUS             RESTARTS   AGE\n"
                "api-deploy-5f6d7c8-q1  0/1     ImagePullBackOff   0          3m\n\n"
                "Warning  Failed  pod/api-deploy-5f6d7c8-q1  "
                "Failed to pull image \"myregistry.io/api:v2.1.0\": "
                "unauthorized: authentication required\n"
                "Namespace: production"
            ),
            tags=_demo_tags("kubernetes", "imagepullbackoff", "pod", "registry"),
            notes="Namespace: production\nEnsure imagePullSecrets is set in the "
            "service account or pod spec for private registries.",
        ),
        Fix(
            issue="Helm: release my-api already exists - "
            'cannot re-use a name that is still in use.',
            resolution="The previous release was stuck in a failed state. "
            "Ran `helm uninstall my-api -n production` to clean up, then "
            "re-ran `helm install`. Alternatively, use `helm upgrade --install` "
            "to make the command idempotent.",
            error_excerpt=(
                "Error: INSTALLATION FAILED: cannot re-use a name that is "
                "still in use\n"
                "Release: my-api\n"
                "Namespace: production\n"
                "Chart: my-api-chart-1.2.0"
            ),
            tags=_demo_tags("helm", "kubernetes", "release"),
            notes="Use `helm upgrade --install` instead of `helm install` to "
            "avoid this. Check `helm list -a -n production` to see stuck releases.",
        ),
    ]
