# Singapore GLB V1 Benefits Review Runbook

This runbook deploys and invokes the Benefits Review hosted agent with:

- Singapore Company and Market profiles
- The authoritative `GLB_Benefit_Datapoints_Full_v1.csv` catalog
- A maximum of 15 datapoints per model batch
- GPT-5.6 Luna with `low` reasoning effort
- Omitted-key retry and processing-loss diagnostics

Run all commands from Windows PowerShell. Paste complete code blocks, and do not
include the visible `PS C:\...>` prompt text.

## 1. Download the Updated Source

Git is not required on the VM. The following commands download the updated
branch from GitHub when the target directory does not already exist:

```powershell
$ErrorActionPreference = "Stop"
$VmRepo = "C:\watson\benefits-intelligence-agents-terra"
$BranchZip = "C:\watson\benefits-review-terra.zip"
$DownloadUrl = "https://codeload.github.com/ratul442/benefits-intelligence-agents/zip/refs/heads/benefits-review-terra"
$TempFolder = "C:\watson\benefits-review-terra-download"
if (!(Test-Path $VmRepo)) {
	Remove-Item $BranchZip -Force -ErrorAction SilentlyContinue
	Remove-Item $TempFolder -Recurse -Force -ErrorAction SilentlyContinue
	Invoke-WebRequest -Uri $DownloadUrl -OutFile $BranchZip
	New-Item -ItemType Directory -Path $TempFolder -Force | Out-Null
	Expand-Archive $BranchZip -DestinationPath $TempFolder -Force
	$ExtractedRepo = Get-ChildItem $TempFolder -Directory | Select-Object -First 1
	if (!$ExtractedRepo) { throw "Extracted repository was not found" }
	Move-Item $ExtractedRepo.FullName $VmRepo
	Remove-Item $TempFolder -Recurse -Force
	Remove-Item $BranchZip -Force
}
$ReviewDir = Join-Path $VmRepo "benefits-review"
if (!(Test-Path $ReviewDir)) { throw "Missing source directory: $ReviewDir" }
Set-Location $ReviewDir
```

If the directory already exists, the commands retain it without overwriting
the current VM changes.

## 2. Verify Prerequisites

The VM must have Docker Desktop running with Linux containers and Azure CLI
authenticated to the correct subscription.

Required files:

```text
C:\watson\GLB_Benefit_Datapoints_Full_v1.csv
C:\watson\SGP-BA_CompanyProfile.md
C:\watson\SGP-BA_MarketProfile.md
```

The source directory used below is:

```text
C:\watson\benefits-intelligence-agents-terra\benefits-review
```

Verify the environment and Azure session:

```powershell
$ErrorActionPreference = "Stop"
$ReviewDir = "C:\watson\benefits-intelligence-agents-terra\benefits-review"
Set-Location $ReviewDir
docker version
docker info --format '{{.OSType}}'
az account show --output table
```

The Docker OS type must be `linux`. If Azure CLI is not authenticated, run:

```powershell
az login --use-device-code
az account show --output table
```

If the displayed subscription is incorrect, select the approved subscription:

```powershell
az account set --subscription "<SUBSCRIPTION_ID_OR_NAME>"
```

Confirm all required input files and source files exist:

```powershell
@("C:\watson\GLB_Benefit_Datapoints_Full_v1.csv", "C:\watson\SGP-BA_CompanyProfile.md", "C:\watson\SGP-BA_MarketProfile.md", "$ReviewDir\scripts\convert_glb_catalog.py", "$ReviewDir\src\main.py") | ForEach-Object { if (!(Test-Path $_)) { throw "Missing required file: $_" } }
```

## 3. Apply the Alignment Correction

This patch is idempotent. It adds explicit negative handling for the GLB value
`Not offered` if the downloaded source does not already contain the correction.

```powershell
$AlignmentPath = Join-Path $ReviewDir "src\alignment.py"
$AlignmentBackup = Join-Path $ReviewDir "src\alignment.py.before-not-offered-fix"
Copy-Item $AlignmentPath $AlignmentBackup -Force
$Text = [System.IO.File]::ReadAllText($AlignmentPath)
$NegativeCheck = '    if val in ("not offered", "benefit not offered"):'
$Needle = '    if val.startswith("yes") or val.startswith("above statutory"):'
$NewLine = if ($Text.Contains("`r`n")) { "`r`n" } else { "`n" }
if (!$Text.Contains($NegativeCheck)) {
	if (!$Text.Contains($Needle)) { throw "Alignment insertion point was not found" }
	$Replacement = $NegativeCheck + $NewLine + "        return False" + $NewLine + $Needle
	$UpdatedText = $Text.Replace($Needle, $Replacement)
	[System.IO.File]::WriteAllText($AlignmentPath, $UpdatedText, [System.Text.UTF8Encoding]::new($false))
}
Select-String -LiteralPath $AlignmentPath -SimpleMatch "not offered" -Context 2,2
```

## 4. Generate the Authoritative GLB V1 Catalog

```powershell
$V1Source = "C:\watson\GLB_Benefit_Datapoints_Full_v1.csv"
$SourceDir = Join-Path $ReviewDir "data\source_catalogs"
if (!(Test-Path $V1Source)) { throw "Missing $V1Source" }
New-Item -ItemType Directory -Path $SourceDir -Force | Out-Null
Copy-Item $V1Source "$SourceDir\GLB_Benefit_Datapoints_Full_v1.csv" -Force
```

```powershell
docker run --rm --volume "${ReviewDir}:/app" --workdir /app python:3.12-slim python scripts/convert_glb_catalog.py data/source_catalogs/GLB_Benefit_Datapoints_Full_v1.csv data/catalog/datapoints_catalog.json --version glb-v1-standard-2026-07-31
```

Validate the active catalog:

```powershell
$Catalog = Get-Content ".\data\catalog\datapoints_catalog.json" -Raw | ConvertFrom-Json
[PSCustomObject]@{ Source=$Catalog.source_file; Version=$Catalog.catalog_version; Rows=$Catalog.items.Count; UniqueKeys=@($Catalog.items.comparison_key | Sort-Object -Unique).Count; FirstKey=$Catalog.items[0].comparison_key } | Format-List
```

Expected values:

```text
Source     : GLB_Benefit_Datapoints_Full_v1.csv
Version    : glb-v1-standard-2026-07-31
Rows       : 160
UniqueKeys : 160
FirstKey   : risk_benefits_life_insurance_benefit_offered
```

Stop if any value differs.

## 5. Validate Source and Tests

Confirm the explicit `Not offered` normalization fix is present:

```powershell
$AlignmentPath = Join-Path $ReviewDir "src\alignment.py"
Select-String -LiteralPath $AlignmentPath -SimpleMatch 'if val in ("not offered", "benefit not offered"):'
```

Run the test suite in Docker:

```powershell
docker run --rm --volume "${ReviewDir}:/app" --workdir /app python:3.12-slim sh -c "pip install --quiet -r requirements.txt && python -m unittest discover -s tests -v"
```

Validate the corrected outcomes in the same temporary Python environment:

```powershell
docker run --rm --volume "${ReviewDir}:/app" --workdir /app python:3.12-slim sh -c "pip install --quiet -r requirements.txt && python -c \"from src.alignment import compute_prevalence_alignment as c; assert c('Not offered','0% of peers offer benefit')[0]=='= Broadly Aligned (0.0%)'; assert c('Not offered','66.7% of peers offer benefit')[0]=='-- Significantly Below (66.7%)'; print('Prevalence alignment: PASS')\""
```

Do not continue unless the tests report `OK` and the direct validation reports
`Prevalence alignment: PASS`.

## 6. Build and Verify the Image

Use a unique tag for each build:

```powershell
$AcrName = "RSGBDTESTN20ACR01"
$LoginServer = "rsgbdtestn20acr01.azurecr.io"
$Tag = "sgp-glb-v1-luna-" + (Get-Date -Format "yyyyMMdd-HHmmss")
$ImageTag = "${LoginServer}/benefits-review:${Tag}"
docker build --no-cache --platform linux/amd64 --tag $ImageTag .
```

Verify the catalog and alignment fix inside the built image:

```powershell
docker run --rm $ImageTag python -c "import json; from src.alignment import _is_company_yes; c=json.load(open('/app/data/catalog/datapoints_catalog.json')); assert c['source_file']=='GLB_Benefit_Datapoints_Full_v1.csv'; assert c['catalog_version']=='glb-v1-standard-2026-07-31'; assert len(c['items'])==160; assert len({x['comparison_key'] for x in c['items']})==160; assert _is_company_yes('Not offered') is False; assert _is_company_yes('Benefit not offered') is False; assert _is_company_yes('Offered') is True; print('Image validation: PASS')"
```

Validate the two observed prevalence cases:

```powershell
docker run --rm $ImageTag python -c "from src.alignment import compute_prevalence_alignment as c; assert c('Not offered','0% of peers offer benefit')[0]=='= Broadly Aligned (0.0%)'; assert c('Not offered','66.7% of peers offer benefit')[0]=='-- Significantly Below (66.7%)'; print('Prevalence alignment: PASS')"
```

## 7. Push the Image and Capture Its Digest

```powershell
az acr login --name $AcrName
docker push $ImageTag
$Digest = az acr repository show --name $AcrName --image "benefits-review:$Tag" --query digest --output tsv
$ImageDigest = "${LoginServer}/benefits-review@${Digest}"
$ImageDigest
```

Use the immutable digest for deployment, not the mutable tag.

## 8. Deploy a New Foundry Agent Version

```powershell
$BaseUrl = "https://rsg-hwt-t-n20-ai-foundry-04.services.ai.azure.com/api/projects/BDS-TEST"
$Token = az account get-access-token --resource "https://ai.azure.com" --query accessToken --output tsv
if (!$Token) { throw "Unable to obtain Azure token" }
```

GPT-5 models must not receive `temperature` or `top_p`.

```powershell
$DeploymentBody = @{ name="benefits-review"; definition=@{ kind="hosted"; image=$ImageDigest; cpu="1"; memory="2Gi"; container_protocol_versions=@(@{ protocol="invocations"; version="1.0.0" }); environment_variables=@{ AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-5.6-luna"; LLM_REASONING_EFFORT="low"; CONTAINER_TAG=$Tag; PROMPT_VERSION="2026-11-extraction-accuracy-v3" } } } | ConvertTo-Json -Depth 10
```

```powershell
Invoke-RestMethod -Method Post -Uri "$BaseUrl/agents/benefits-review?api-version=v1" -Headers @{ Authorization="Bearer $Token"; "Foundry-Features"="HostedAgents=V1Preview" } -ContentType "application/json" -Body $DeploymentBody
```

Refresh the agent with a new GET request until the latest version is active:

```powershell
$Token = az account get-access-token --resource "https://ai.azure.com" --query accessToken --output tsv
$Agent = Invoke-RestMethod -Method Get -Uri "$BaseUrl/agents/benefits-review?api-version=v1" -Headers @{ Authorization="Bearer $Token"; "Foundry-Features"="HostedAgents=V1Preview" }
$Agent.versions.latest | Format-List version,status
$Agent.versions.latest.definition.image
$Agent.versions.latest.definition.environment_variables
```

Printing an existing `$Agent` variable does not refresh its status. Repeat the
GET request when the status is `creating`. If the status becomes `failed`, run:

```powershell
$Agent.versions.latest | ConvertTo-Json -Depth 30
```

## 9. Invoke the Singapore Run

Use the original Company and Market profiles. The GLB CSV is the catalog source;
it must not replace the Market profile.

```powershell
$CompanyFile = "C:\watson\SGP-BA_CompanyProfile.md"
$MarketFile = "C:\watson\SGP-BA_MarketProfile.md"
if (!(Test-Path $CompanyFile)) { throw "Missing $CompanyFile" }
if (!(Test-Path $MarketFile)) { throw "Missing $MarketFile" }
$RequestId = "sgp-glb-v1-luna-" + (Get-Date -Format "yyyyMMdd-HHmmss")
$RunDir = "C:\watson\results\$RequestId"
New-Item -ItemType Directory -Path $RunDir -Force | Out-Null
$RequestFile = "$RunDir\request.json"
$SseFile = "$RunDir\response.sse"
$ResultFile = "$RunDir\result.json"
$Request = @{ input=@{ request_id=$RequestId; country="SGP"; company_payload=Get-Content $CompanyFile -Raw; market_payload=Get-Content $MarketFile -Raw } }
[System.IO.File]::WriteAllText($RequestFile, ($Request | ConvertTo-Json -Depth 10), [System.Text.UTF8Encoding]::new($false))
```

```powershell
$Token = az account get-access-token --resource "https://ai.azure.com" --query accessToken --output tsv
$Url = "$BaseUrl/agents/benefits-review/endpoint/protocols/invocations?api-version=v1"
curl.exe --no-buffer --max-time 3600 --url $Url --header "Authorization: Bearer $Token" --header "Content-Type: application/json" --header "Accept: text/event-stream" --header "Foundry-Features: HostedAgents=V1Preview" --data-binary "@$RequestFile" | Tee-Object -FilePath $SseFile
```

Wait for the `done` event.

## 10. Extract and Validate the Result

Run each command as a complete line. Do not end a pasted line with a pipe.

```powershell
$DataLines = Get-Content -LiteralPath $SseFile | Where-Object { $_ -like "data: *" }
$ParsedEvents = @($DataLines | ForEach-Object { try { $_.Substring(6) | ConvertFrom-Json -ErrorAction Stop } catch {} })
$DoneEvent = $ParsedEvents | Where-Object { $_.type -eq "done" } | Select-Object -Last 1
if ($null -eq $DoneEvent) { throw "No done event found in $SseFile" }
$Result = $DoneEvent.result
$ResultJson = $Result | ConvertTo-Json -Depth 100
[System.IO.File]::WriteAllText($ResultFile, $ResultJson, [System.Text.UTF8Encoding]::new($false))
```

Review the summary and diagnostics:

```powershell
$Result.report.validation_summary | Format-List
$Result.metadata | Format-List
```

Required structural checks:

```powershell
$Rows = @($Result.report.rows)
[PSCustomObject]@{ Status=$Result.status; CatalogVersion=$Result.report.catalog_version; Rows=$Rows.Count; UniqueKeys=@($Rows.comparison_key | Sort-Object -Unique).Count; Missing=$Result.report.validation_summary.missing; Failed=$Result.report.validation_summary.failed; ModelOmissions=$Result.metadata.model_omitted_datapoints; ParserLosses=$Result.metadata.parser_dropped_datapoints; MissingBeforeFill=$Result.metadata.missing_before_placeholder_fill } | Format-List
```

Expected structural values:

```text
Status            : completed
CatalogVersion    : glb-v1-standard-2026-07-31
Rows              : 160
UniqueKeys        : 160
Missing           : 0
Failed            : 0
ParserLosses      : 0
MissingBeforeFill : 0
```

Structural success does not prove factual accuracy. Compare Company Provision
and Market Practice facts against the source profiles and golden dataset.

## 11. Export Review Artifacts

```powershell
$ReviewFile = "$RunDir\review-required.json"
$Result.report.rows | Where-Object { $_.validation_status -eq "review" } | ConvertTo-Json -Depth 30 | Set-Content $ReviewFile -Encoding utf8
$Result.report.rows | Export-Csv "$RunDir\all-results.csv" -NoTypeInformation -Encoding utf8
$ShareDir = "$RunDir\review-artifacts"
New-Item -ItemType Directory -Path $ShareDir -Force | Out-Null
Copy-Item "$RunDir\all-results.csv" $ShareDir
Copy-Item $ResultFile $ShareDir
Copy-Item $ReviewFile $ShareDir
Compress-Archive -Path "$ShareDir\*" -DestinationPath "$RunDir\benefits-review-progress.zip" -Force
```

Share the ZIP as progress output, not as a final factual-accuracy benchmark.
Do not share `request.json`, `response.sse`, deployment bodies, tokens, failed
runs, or older outputs.

## Troubleshooting

### Docker tries to run `python:latest`

An image variable was empty. Print and reset the intended variable before
running Docker:

```powershell
$ImageTag
if (!$ImageTag) { throw "ImageTag is empty" }
```

### `elseif` or `else` is not recognized

PowerShell received portions of an `if/elseif/else` block separately. Paste the
complete block at once, or use the single-line commands in this runbook.

### `An empty pipe element is not allowed`

PowerShell received a line ending in `|` as a complete command. Use the
single-line result-extraction commands in section 10.

### A relative .NET file path resolves under `C:\Windows\System32`

Use an absolute path created with `Join-Path $ReviewDir`, then pass it to the
.NET file API.
