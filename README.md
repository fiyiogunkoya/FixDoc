# FixDoc

A CLI tool for cloud engineers to capture and search infrastructure fixes. Stop losing tribal knowledge in Slack threads and personal notes.

## The Problem and my proposed solution

Many bugs and issues in the devops/cloud domain today show themselves in different forms. You may realize an error in azure from the portal for example (a key vault rbac issue or an access policy issue), you may realize an error in your terraform in a resource block that had a firewall disabled when it should not have been and this causes errors down the line. Even in a Kubernetes cluster, your self-hosted agent goes down because of wrong permissions for your secret/PAT and then you log in to the cluster and fix it. Many errors show themselves in different ways. Fixdoc’s mission is to try and capture all these errors and give you a couple of things. 



Reference to your old bugs that you have fixed before
Suggestions when you’re writing terraform that references issues you have had in the past
Capture your errors and actually turn them into documentation that can be searched through keywords
Before running terraform apply, during the plan phase, show me different issues that could arise from previous work.


Let’s run through a basic example:



After terraform deployment, my developer comes to me and tells me they are having issues accessing a storage account and they show me an error excerpt, I take that error excerpt and then I am able to fix that error, maybe I needed to add them to a group in Active Directory that had storage blob data contributor. I should be able to run fix doc and potentially post that error excerpt or a very succinct version of it and then detail what I did to fix it. Or it may be machine to machine permissions so it may not be the user that needs permissions but another application like say data factory needed blob contributor access. Once this error is captured in fix doc, should I face any errors like this again, I should search my fix repo and see all the similar fixes and what I did to fix them. I should be able to search by text through the cli what I can do to fix it and finally should my terraform see any issues that may relate to an older issue I fixed, it should warn me that said line is an issue



NB: At fix doc we must do it as quickly as possible as engineers do not like the overhead of detailing bugs while they’re working. We need to capture the information is as short a time as possible.





Technical approach and methodologies:



Tech stack:

Python will be used for the cli
Local storage will be used for the fix repo
The documentation will be created using markdown


The cli tool will detail a fix and have some flags/keywords



Fixdoc capture will prompt the user for our “fix questions”(this is not exhaustive and some will be optional fields)



What was the issue
How was it resolved
Error excerpt
Misleading directions
Extra info/tags


Fix doc search will allow you to search our fix database/repo eventually it will be indexed but it does not need to start out so robust, we can do regex matching. 





Fix doc analyze will take in a terraform plan as a json and analyze the plan for any issues seen with the terraform error tags and then give us an analysis on if there are any issues it has seen before. 



A fix will be its own object and the object will be populated based on the user input from when a capture is sent. the entire “fix” object will be sent to create the markdown documentation and then the fix, with a unique id will then be stored in some form of local repo.



We will use the src-layout approach in python.

1. **Reference** to your old bugs that you've fixed before
2. **Searchable documentation** through keywords
3. **Proactive warnings** during `terraform plan` about issues you've encountered before

## Installation

```bash
# Clone the repo
git clone <repo-url>
cd fixdoc

#I recommend you set up a python virtual environment to isolate your dependencies

# Install in development mode
pip install -e .
```

## Quick Start

### Capture a Fix

**Interactive mode** - guided prompts for all fields:
```bash
fixdoc capture
```

**Quick mode** - for when you're in a hurry:
```bash
fixdoc capture --quick "User couldn't access storage account | Added them to storage blob data contributor group" --tags azurerm_storage_account,rbac
```

### Search Your Fixes

```bash
fixdoc search "storage account"
fixdoc search rbac
fixdoc search "access denied"
```

### Analyze Terraform Plans(In Development)

Before running `terraform apply`, check for known issues:

```bash
# Generate plan JSON
terraform plan -out=plan.tfplan
terraform show -json plan.tfplan > plan.json

# Analyze against your fix history
fixdoc analyze plan.json
```

Output:
```
Found 1 potential issue(s) based on your fix history:

⚠  azurerm_storage_account.main may relate to FIX-a1b2c3d4
   Previous issue: Users couldn't access blob storage
   Resolution: Added storage blob data contributor role
   Tags: azurerm_storage_account,rbac

Run `fixdoc show <fix-id>` for full details on any fix.
```

### Other Commands

```bash
# List all fixes
fixdoc list

# Show full details of a fix
fixdoc show a1b2c3d4

# Delete a fix
fixdoc delete a1b2c3d4

# View statistics
fixdoc stats
```

## Fix Fields

When capturing a fix, you'll be prompted for:

| Field | Required | Description |
|-------|----------|-------------|
| Issue | Yes | What was the problem? |
| Resolution | Yes | How did you fix it? |
| Error excerpt | No | Relevant error message or logs |
| Tags |No | Comma-separated keywords (resource types, categories) |
| Notes |No | Gotchas, misleading directions, additional context |

**Tip**: Use resource types as tags (e.g., `azurerm_storage_account`, `azurerm_key_vault`) to enable terraform plan analysis.

## Storage(In Dev)

FixDoc stores everything locally(will be migrated to cloud storage in the future):

```
~/.fixdoc/
├── fixes.json      # JSON database of all fixes
└── docs/           # Generated markdown files
    ├── <uuid>.md
    └── ...
```

Markdown files are generated alongside the JSON database, so you can:
- Push them to a wiki
- Commit them to a repo
- Share them with your team

## Philosophy

**Speed is everything.** Engineers won't document fixes if it takes too long. FixDoc is designed to capture information in seconds:

- Quick mode for one-liner captures(my favorite feature)
- Optional fields you can skip
- Tags for fast categorization

The goal is to build a searchable knowledge base over time, not to write perfect documentation for each fix.
