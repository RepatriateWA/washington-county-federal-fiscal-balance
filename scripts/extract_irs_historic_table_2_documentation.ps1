<#
ETL-172B-3A
IRS Historic Table 2 documentation text extraction.

Reads preserved IRS legacy Word .doc files for TY2015-TY2023.
Writes UTF-8 text derivatives and an extraction manifest.

Source files are not modified.

NO semantic certification.
NO liability calculation.
NO FY/TY mapping.
NO TY2024 estimation.
NO database writes.
NO ledger authorization.
#>

$ErrorActionPreference = "Stop"

$RepoRoot = (Get-Location).Path

$SourceDir = Join-Path `
    $RepoRoot `
    "data\raw\irs\historic_table_2\documentation"

$OutputDir = Join-Path `
    $RepoRoot `
    "data\raw\irs\historic_table_2\validation\documentation_text_v0_1"

$ManifestPath = Join-Path `
    $OutputDir `
    "extraction_manifest.csv"

$TaxYears = 2015..2023

$TargetVariables = @(
    "A06500",
    "A85530",
    "A85300"
)

Write-Host ("=" * 80)
Write-Host "IRS HISTORIC TABLE 2 DOCUMENTATION EXTRACTION - ETL-172B-3A"
Write-Host ("=" * 80)
Write-Host ""
Write-Host "Tax years       : 2015-2023"
Write-Host "Source mutation : NONE"
Write-Host "Semantic ruling : NONE"
Write-Host "Liability calc  : NONE"
Write-Host "FY/TY mapping   : NONE"
Write-Host "Database writes : NONE"
Write-Host ""

New-Item `
    -ItemType Directory `
    -Force `
    -Path $OutputDir |
    Out-Null

if (Test-Path $ManifestPath) {
    throw "Refusing silent overwrite of manifest: $ManifestPath"
}

$ExistingTextFiles = @(
    Get-ChildItem `
        -Path $OutputDir `
        -Filter "*.txt" `
        -File `
        -ErrorAction SilentlyContinue
)

if ($ExistingTextFiles.Count -gt 0) {
    throw "Refusing silent overwrite of existing extracted text files."
}

$Word = $null
$ManifestRows = @()

try {

    $Word = New-Object -ComObject Word.Application
    $Word.Visible = $false
    $Word.DisplayAlerts = 0

    Write-Host "Word version     : $($Word.Version)"
    Write-Host ""

    foreach ($TaxYear in $TaxYears) {

        $SourceName = "irs_historic_table_2_documentation_ty$TaxYear.doc"
        $OutputName = "irs_historic_table_2_documentation_ty$TaxYear.txt"

        $SourcePath = Join-Path $SourceDir $SourceName
        $OutputPath = Join-Path $OutputDir $OutputName

        if (-not (Test-Path $SourcePath)) {
            throw "Missing source file: $SourcePath"
        }

        if (Test-Path $OutputPath) {
            throw "Refusing silent overwrite: $OutputPath"
        }

        Write-Host "TY$TaxYear"

        $Document = $null

        try {

            $Document = $Word.Documents.Open(
                $SourcePath,
                $false,
                $true,
                $false
            )

            $ExtractedText = $Document.Content.Text

            if ([string]::IsNullOrWhiteSpace($ExtractedText)) {
                throw "Empty text extraction for TY$TaxYear"
            }

            # Word paragraph marks.
           # Normalize Word paragraph marks to Windows CRLF.
            $ExtractedText = $ExtractedText.Replace(
                ([char]13).ToString(),
                [Environment]::NewLine
            )

            # Normalize Word table cell markers to tabs.
            $ExtractedText = $ExtractedText.Replace(
                ([char]7).ToString(),
                "`t"
            )

            $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

            [System.IO.File]::WriteAllText(
                $OutputPath,
                $ExtractedText,
                $Utf8NoBom
            )
        }
        finally {

            if ($null -ne $Document) {

                $Document.Close($false)

                [System.Runtime.InteropServices.Marshal]::ReleaseComObject(
                    $Document
                ) | Out-Null

                $Document = $null
            }
        }

        $SourceItem = Get-Item $SourcePath
        $OutputItem = Get-Item $OutputPath

        $SourceHash = (
            Get-FileHash -Algorithm SHA256 -Path $SourcePath
        ).Hash

        $OutputHash = (
            Get-FileHash -Algorithm SHA256 -Path $OutputPath
        ).Hash

        $Text = Get-Content `
            -Raw `
            -Encoding UTF8 `
            -Path $OutputPath

        $A06500Present = $Text -match "(?i)\bA06500\b"
        $A85530Present = $Text -match "(?i)\bA85530\b"
        $A85300Present = $Text -match "(?i)\bA85300\b"

        Write-Host "  source bytes : $($SourceItem.Length)"
        Write-Host "  output bytes : $($OutputItem.Length)"
        Write-Host "  characters   : $($Text.Length)"
        Write-Host "  A06500       : $A06500Present"
        Write-Host "  A85530       : $A85530Present"
        Write-Host "  A85300       : $A85300Present"
        Write-Host ""

        $RelativeSource = $SourcePath.Replace(
            $RepoRoot + "\",
            ""
        )

        $RelativeOutput = $OutputPath.Replace(
            $RepoRoot + "\",
            ""
        )

        $ManifestRows += [PSCustomObject]@{
            tax_year              = $TaxYear
            source_path           = $RelativeSource
            source_bytes          = $SourceItem.Length
            source_sha256         = $SourceHash
            output_path           = $RelativeOutput
            output_bytes          = $OutputItem.Length
            output_sha256         = $OutputHash
            extracted_characters  = $Text.Length
            A06500_present        = $A06500Present
            A85530_present        = $A85530Present
            A85300_present        = $A85300Present
            extraction_method     = "Microsoft Word COM"
            word_version          = $Word.Version
            semantic_certification = "NOT_PERFORMED"
        }
    }
}
finally {

    if ($null -ne $Word) {

        $Word.Quit()

        [System.Runtime.InteropServices.Marshal]::ReleaseComObject(
            $Word
        ) | Out-Null

        $Word = $null
    }

    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}

$ManifestRows |
    Export-Csv `
        -Path $ManifestPath `
        -NoTypeInformation `
        -Encoding UTF8

$AllExtracted = $ManifestRows.Count -eq $TaxYears.Count

$MissingA06500 = @(
    $ManifestRows |
    Where-Object { -not $_.A06500_present }
)

$MissingA85530 = @(
    $ManifestRows |
    Where-Object { -not $_.A85530_present }
)

$MissingA85300 = @(
    $ManifestRows |
    Where-Object { -not $_.A85300_present }
)

Write-Host ("=" * 80)
Write-Host "EXTRACTION SUMMARY"
Write-Host ("=" * 80)
Write-Host ""

Write-Host "Documents extracted : $($ManifestRows.Count)"
Write-Host "Expected documents  : $($TaxYears.Count)"
Write-Host ""

if ($MissingA06500.Count -eq 0) {
    Write-Host "A06500 documented   : ALL YEARS"
}
else {
    Write-Host "A06500 documented   : NOT ALL YEARS"
}

if ($MissingA85530.Count -eq 0) {
    Write-Host "A85530 documented   : ALL YEARS"
}
else {
    Write-Host "A85530 documented   : NOT ALL YEARS"
}

if ($MissingA85300.Count -eq 0) {
    Write-Host "A85300 documented   : ALL YEARS"
}
else {
    Write-Host "A85300 documented   : NOT ALL YEARS"
}

Write-Host ""
Write-Host "Manifest:"
Write-Host "  $ManifestPath"
Write-Host ""

if ($AllExtracted) {
    Write-Host "EXTRACTION RESULT: PASS"
}
else {
    Write-Host "EXTRACTION RESULT: FAIL"
    exit 1
}

Write-Host ""
Write-Host "Target-code presence is diagnostic only."
Write-Host "No semantic meaning has been certified."