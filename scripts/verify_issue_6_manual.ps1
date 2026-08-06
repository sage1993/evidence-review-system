#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ExpectedCommit,

    [string]$RepoRoot = (Get-Location).Path,

    [string]$Python311 = "",

    [string]$Python313 = "",

    [string]$VectorPdf = "",

    [string]$Raster600Dpi = "",

    [string]$RejectedQualityFixture = "",

    [string]$BrowserEvidenceJson = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
$ReportRoot = Join-Path $RepoRoot "build\issue-6-manual-verification"
$WheelRoot = Join-Path $ReportRoot "wheels"
New-Item -ItemType Directory -Path $ReportRoot -Force | Out-Null
New-Item -ItemType Directory -Path $WheelRoot -Force | Out-Null

$Results = New-Object System.Collections.Generic.List[object]

function Add-Result {
    param(
        [string]$Name,
        [ValidateSet("PASS", "FAIL", "BLOCKED")]
        [string]$Status,
        [string]$Details,
        [string]$Command = ""
    )

    $script:Results.Add([pscustomobject]@{
        name = $Name
        status = $Status
        command = $Command
        details = $Details
    })
}

function Invoke-Checked {
    param(
        [string]$Name,
        [string]$Executable,
        [string[]]$Arguments
    )

    if ([string]::IsNullOrWhiteSpace($Executable)) {
        Add-Result -Name $Name -Status "BLOCKED" -Details "Interpreter path was not supplied."
        return
    }

    $commandText = ($Executable + " " + ($Arguments -join " ")).Trim()
    $output = ""
    $exitCode = 1
    try {
        Push-Location $RepoRoot
        try {
            $output = (& $Executable @Arguments 2>&1 | Out-String).Trim()
            $exitCode = $LASTEXITCODE
        }
        finally {
            Pop-Location
        }
    }
    catch {
        $output = $_.Exception.Message
        $exitCode = 1
    }

    $status = if ($exitCode -eq 0) { "PASS" } else { "FAIL" }
    $details = "exit_code=$exitCode" + [Environment]::NewLine + $output
    Add-Result -Name $Name -Status $status -Details $details -Command $commandText
}

function Get-GitValue {
    param([string[]]$Arguments)

    try {
        $value = (& git -C $RepoRoot @Arguments 2>&1 | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) {
            return ""
        }
        return $value
    }
    catch {
        return ""
    }
}

function Add-FixtureCheck {
    param(
        [string]$Name,
        [string]$Path,
        [string[]]$AllowedExtensions
    )

    if ([string]::IsNullOrWhiteSpace($Path)) {
        Add-Result -Name $Name -Status "BLOCKED" -Details "Supply the fixture path explicitly."
        return
    }

    $resolved = Resolve-Path -LiteralPath $Path -ErrorAction SilentlyContinue
    if ($null -eq $resolved -or -not (Test-Path -LiteralPath $resolved.Path -PathType Leaf)) {
        Add-Result -Name $Name -Status "FAIL" -Details "Fixture file does not exist: $Path"
        return
    }

    $extension = [IO.Path]::GetExtension($resolved.Path).ToLowerInvariant()
    if ($AllowedExtensions -notcontains $extension) {
        Add-Result -Name $Name -Status "FAIL" -Details "Unexpected fixture extension '$extension'."
        return
    }

    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $resolved.Path).Hash.ToLowerInvariant()
    $bytes = (Get-Item -LiteralPath $resolved.Path).Length

    Add-Result -Name $Name -Status "PASS" -Details (
        "Fixture is present for manual inspection. bytes=$bytes sha256=$hash path=$($resolved.Path). " +
        "This check does not classify vector/raster semantics automatically."
    )
}

$actualTop = Get-GitValue -Arguments @("rev-parse", "--show-toplevel")
$actualCommit = Get-GitValue -Arguments @("rev-parse", "HEAD")
$actualBranch = Get-GitValue -Arguments @("symbolic-ref", "--short", "-q", "HEAD")
$worktree = Get-GitValue -Arguments @("status", "--porcelain")

if ([string]::IsNullOrWhiteSpace($actualTop)) {
    Add-Result -Name "git-checkout" -Status "FAIL" -Details "RepoRoot is not a Git checkout: $RepoRoot"
}
else {
    Add-Result -Name "git-checkout" -Status "PASS" -Details "top=$actualTop branch=$actualBranch commit=$actualCommit"
}

if ($actualCommit.ToLowerInvariant() -eq $ExpectedCommit.Trim().ToLowerInvariant()) {
    Add-Result -Name "exact-commit" -Status "PASS" -Details "HEAD matches ExpectedCommit=$ExpectedCommit"
}
else {
    Add-Result -Name "exact-commit" -Status "FAIL" -Details "Expected $ExpectedCommit but found $actualCommit"
}

if ([string]::IsNullOrWhiteSpace($worktree)) {
    Add-Result -Name "clean-worktree" -Status "PASS" -Details "No uncommitted changes before verification."
}
else {
    Add-Result -Name "clean-worktree" -Status "FAIL" -Details "Working tree is dirty:" + [Environment]::NewLine + $worktree
}

$focusedTests = @(
    "tests/unit/math_engine/test_drawing_formulas.py",
    "tests/unit/parsing/test_drawing_calibration.py",
    "tests/unit/parsing/test_drawing_extractors.py",
    "tests/integration/review_packet/test_drawing_evidence_renderer.py"
)

$pythonTargets = @(
    [pscustomobject]@{ label = "Python 3.11"; executable = $Python311; mypy_version = "3.11" },
    [pscustomobject]@{ label = "Python 3.13"; executable = $Python313; mypy_version = "3.13" }
)

foreach ($target in $pythonTargets) {
    $label = $target.label
    $python = $target.executable
    if ([string]::IsNullOrWhiteSpace($python)) {
        Add-Result -Name "$label interpreter" -Status "BLOCKED" -Details "Pass the full python.exe path for this target."
        continue
    }

    Invoke-Checked -Name "$label version" -Executable $python -Arguments @("--version")
    Invoke-Checked -Name "$label focused pytest" -Executable $python -Arguments (@("-m", "pytest", "-q") + $focusedTests)
    Invoke-Checked -Name "$label full pytest" -Executable $python -Arguments @("-m", "pytest", "-q")
    Invoke-Checked -Name "$label Ruff" -Executable $python -Arguments @("-m", "ruff", "check", "src", "tests")
    Invoke-Checked -Name "$label strict mypy" -Executable $python -Arguments @(
        "-m", "mypy", "--python-version", $target.mypy_version, "src"
    )

    $compilePaths = @("src", "scripts", "web_runtime") |
        Where-Object { Test-Path -LiteralPath (Join-Path $RepoRoot $_) }
    Invoke-Checked -Name "$label compileall" -Executable $python -Arguments (@("-m", "compileall", "-q") + $compilePaths)

    $wheelDir = Join-Path $WheelRoot ($label.Replace(" ", "-").Replace(".", "_"))
    New-Item -ItemType Directory -Path $wheelDir -Force | Out-Null
    Invoke-Checked -Name "$label wheel build" -Executable $python -Arguments @(
        "-m", "pip", "wheel", "--no-deps", "--no-build-isolation",
        "--wheel-dir", $wheelDir, "."
    )

    $resourceCode = "from importlib.resources import files; import ansim_review.review_packet as rp; import ansim_review.drawing_review as dr; assert files(rp).joinpath('assets').is_dir(); assert files(dr).joinpath('assets').is_dir(); print('PACKAGE_RESOURCES_OK')"
    Invoke-Checked -Name "$label package-resource smoke" -Executable $python -Arguments @("-c", $resourceCode)
}

Add-FixtureCheck -Name "vector-PDF fixture" -Path $VectorPdf -AllowedExtensions @(".pdf")
Add-FixtureCheck -Name "600dpi raster fixture" -Path $Raster600Dpi -AllowedExtensions @(".png", ".jpg", ".jpeg", ".tif", ".tiff")
Add-FixtureCheck -Name "rejected-quality fixture" -Path $RejectedQualityFixture -AllowedExtensions @(".json", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".pdf")

if ([string]::IsNullOrWhiteSpace($BrowserEvidenceJson)) {
    Add-Result -Name "browser QA evidence" -Status "BLOCKED" -Details (
        "Browser QA is intentionally manual. Supply a JSON evidence file with true values for " +
        "candidate_confirmation, calibration_handoff, and review_packet_rendering."
    )
}
elseif (-not (Test-Path -LiteralPath $BrowserEvidenceJson -PathType Leaf)) {
    Add-Result -Name "browser QA evidence" -Status "FAIL" -Details "Evidence file does not exist: $BrowserEvidenceJson"
}
else {
    try {
        $browser = Get-Content -Raw -LiteralPath $BrowserEvidenceJson | ConvertFrom-Json
        $required = @("candidate_confirmation", "calibration_handoff", "review_packet_rendering")
        $missing = @($required | Where-Object { $null -eq $browser.$_ -or -not [bool]$browser.$_ })
        if ($missing.Count -eq 0) {
            Add-Result -Name "browser QA evidence" -Status "PASS" -Details "All required browser checks are explicitly true."
        }
        else {
            Add-Result -Name "browser QA evidence" -Status "FAIL" -Details ("Missing or false checks: " + ($missing -join ", "))
        }
    }
    catch {
        Add-Result -Name "browser QA evidence" -Status "FAIL" -Details $_.Exception.Message
    }
}

$failures = @($Results | Where-Object { $_.status -eq "FAIL" })
$blocked = @($Results | Where-Object { $_.status -eq "BLOCKED" })
$overall = if ($failures.Count -gt 0) { "FAIL" } elseif ($blocked.Count -gt 0) { "BLOCKED" } else { "PASS" }

$report = [ordered]@{
    format = "evidence-review/issue-6-manual-verification"
    version = 1
    generated_at_utc = [DateTime]::UtcNow.ToString("o")
    repo_root = $RepoRoot
    branch = $actualBranch
    expected_commit = $ExpectedCommit
    actual_commit = $actualCommit
    overall = $overall
    github_actions_used = $false
    results = @($Results.ToArray())
}

$reportPath = Join-Path $ReportRoot "report.json"
$report | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $reportPath -Encoding UTF8

Write-Host "Issue #6 manual verification: $overall"
Write-Host "Report: $reportPath"
if ($overall -ne "PASS") {
    exit 2
}
