<#
ETL-172C-1
Rockefeller Institute Balance of Payments source preservation.

Purpose
-------
Preserve the official Rockefeller Institute Balance of Payments report
PDFs relevant to the WCFFBP study period.

Acquisition roots are the eight verified Rockefeller report pages:
2017, 2019, 2020, 2021, 2022, 2023, 2024, 2025.

The script:
- retrieves each official Rockefeller report page,
- discovers candidate PDF links,
- requires a rockinst.org destination,
- downloads the original PDF,
- validates the PDF signature,
- records source page and PDF URL,
- records byte size and SHA-256,
- refuses silent overwrite,
- writes an acquisition manifest.

It does NOT:
- interpret methodology,
- extract report values,
- select final vs preliminary estimates,
- calculate Washington receipts,
- write to PostgreSQL,
- authorize ledger inclusion.
#>

$ErrorActionPreference = "Stop"

$RepoRoot = (Get-Location).Path

$BaseDir = Join-Path `
    $RepoRoot `
    "data\raw\rockefeller\balance_of_payments"

$SourceDir = Join-Path $BaseDir "source"
$ValidationDir = Join-Path $BaseDir "validation"

$ManifestPath = Join-Path `
    $ValidationDir `
    "acquisition_manifest.csv"

$Reports = @(
    [PSCustomObject]@{
        report_year = 2017
        series_number = 1
        page_url = "https://rockinst.org/issue-area/giving-getting-new-yorks-balance-payments-federal-government-2/"
    },
    [PSCustomObject]@{
        report_year = 2019
        series_number = 2
        page_url = "https://rockinst.org/issue-area/new-yorks-balance-of-payments-with-the-federal-government/"
    },
    [PSCustomObject]@{
        report_year = 2020
        series_number = 3
        page_url = "https://rockinst.org/issue-area/balance-of-payments-2020/"
    },
    [PSCustomObject]@{
        report_year = 2021
        series_number = 4
        page_url = "https://rockinst.org/issue-area/balance-of-payments-2021/"
    },
    [PSCustomObject]@{
        report_year = 2022
        series_number = 5
        page_url = "https://rockinst.org/issue-area/balance-of-payments-2022/"
    },
    [PSCustomObject]@{
        report_year = 2023
        series_number = 6
        page_url = "https://rockinst.org/issue-area/balance-of-payments-2023/"
    },
    [PSCustomObject]@{
        report_year = 2024
        series_number = 7
        page_url = "https://rockinst.org/issue-area/new-yorks-balance-of-payments-with-the-federal-government-2024/"
    },
    [PSCustomObject]@{
        report_year = 2025
        series_number = 8
        page_url = "https://rockinst.org/issue-area/bop-2025/"
    }
)

Write-Host ("=" * 88)
Write-Host "ROCKEFELLER BALANCE OF PAYMENTS ACQUISITION - ETL-172C-1"
Write-Host ("=" * 88)
Write-Host ""
Write-Host "Report vintages : 2017, 2019-2025"
Write-Host "Expected reports: 8"
Write-Host "Source mutation : NONE"
Write-Host "Methodology     : NOT INTERPRETED"
Write-Host "Database writes : NONE"
Write-Host ""

New-Item -ItemType Directory -Force -Path $SourceDir |
    Out-Null

New-Item -ItemType Directory -Force -Path $ValidationDir |
    Out-Null

if (Test-Path $ManifestPath) {
    throw "Refusing silent overwrite of manifest: $ManifestPath"
}

$ExistingPdfFiles = @(
    Get-ChildItem `
        -Path $SourceDir `
        -Filter "*.pdf" `
        -File `
        -ErrorAction SilentlyContinue
)

if ($ExistingPdfFiles.Count -gt 0) {
    throw "Refusing silent overwrite: PDF files already exist in $SourceDir"
}

function Test-PdfSignature {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $Stream = [System.IO.File]::OpenRead($Path)

    try {
        $Buffer = New-Object byte[] 5
        $Read = $Stream.Read($Buffer, 0, 5)

        if ($Read -ne 5) {
            return $false
        }

        $Signature = [System.Text.Encoding]::ASCII.GetString($Buffer)

        return $Signature -eq "%PDF-"
    }
    finally {
        $Stream.Dispose()
    }
}

function Get-AbsoluteUrl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$BaseUrl,

        [Parameter(Mandatory = $true)]
        [string]$Href
    )

    $BaseUri = [System.Uri]$BaseUrl
    $AbsoluteUri = New-Object System.Uri($BaseUri, $Href)

    return $AbsoluteUri.AbsoluteUri
}

$ManifestRows = @()

foreach ($Report in $Reports) {

    $Year = $Report.report_year
    $PageUrl = $Report.page_url

    Write-Host "Report $Year"
    Write-Host "  page: $PageUrl"

    $Page = Invoke-WebRequest `
        -Uri $PageUrl `
        -UseBasicParsing

    if ($Page.StatusCode -ne 200) {
        throw "Report page request failed for $Year"
    }

    $HrefMatches = @(
        [regex]::Matches(
            $Page.Content,
            'href\s*=\s*["''](?<href>[^"'']+\.pdf(?:\?[^"'']*)?)["'']',
            [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
        )
    )

    $PdfCandidates = @()

    foreach ($Match in $HrefMatches) {

        $Href = $Match.Groups["href"].Value

        if ([string]::IsNullOrWhiteSpace($Href)) {
            continue
        }

        $AbsoluteUrl = Get-AbsoluteUrl `
            -BaseUrl $PageUrl `
            -Href $Href

        $Uri = [System.Uri]$AbsoluteUrl

        if ($Uri.Host -notmatch '(^|\.)rockinst\.org$') {
            continue
        }

        $PdfCandidates += $AbsoluteUrl
    }

    $PdfCandidates = @(
        $PdfCandidates |
        Sort-Object -Unique
    )

    if ($PdfCandidates.Count -eq 0) {
        throw "No Rockefeller-hosted PDF discovered for report $Year"
    }

    #
    # Prefer candidate links that appear to be BOP/report documents.
    # If discovery remains ambiguous, fail rather than guess.
    #
    $PreferredCandidates = @(
        $PdfCandidates |
        Where-Object {
            $_ -match '(?i)(bop|balance|payment|report)'
        }
    )

    if ($PreferredCandidates.Count -eq 1) {
        $PdfUrl = $PreferredCandidates[0]
    }
    elseif (
        $PreferredCandidates.Count -eq 0 -and
        $PdfCandidates.Count -eq 1
    ) {
        $PdfUrl = $PdfCandidates[0]
    }
    else {
        Write-Host ""
        Write-Host "Candidate PDFs discovered for ${Year}:"

        foreach ($Candidate in $PdfCandidates) {
            Write-Host "  $Candidate"
        }

        throw "Ambiguous PDF discovery for report $Year. No file downloaded."
    }

    $PdfUri = [System.Uri]$PdfUrl

    if ($PdfUri.Host -notmatch '(^|\.)rockinst\.org$') {
        throw "Non-Rockefeller PDF destination rejected: $PdfUrl"
    }

    $OriginalFilename = [System.IO.Path]::GetFileName(
        $PdfUri.AbsolutePath
    )

    if ([string]::IsNullOrWhiteSpace($OriginalFilename)) {
        throw "Could not determine PDF filename for report $Year"
    }

    #
    # Normalize local filename while retaining original filename
    # in the manifest.
    #
    $LocalFilename = "rockefeller_bop_report_$Year.pdf"
    $LocalPath = Join-Path $SourceDir $LocalFilename

    if (Test-Path $LocalPath) {
        throw "Refusing silent overwrite: $LocalPath"
    }

    Write-Host "  pdf : $PdfUrl"

    try {
        Invoke-WebRequest `
            -Uri $PdfUrl `
            -OutFile $LocalPath `
            -UseBasicParsing
    }
    catch {
        if (Test-Path $LocalPath) {
            Remove-Item $LocalPath -Force
        }

        throw
    }

    if (-not (Test-Path $LocalPath)) {
        throw "Download did not create expected file for $Year"
    }

    if (-not (Test-PdfSignature -Path $LocalPath)) {

        Remove-Item $LocalPath -Force

        throw "Downloaded artifact is not a valid PDF for report $Year"
    }

    $FileItem = Get-Item $LocalPath

    if ($FileItem.Length -le 0) {
        Remove-Item $LocalPath -Force
        throw "Downloaded PDF is empty for report $Year"
    }

    $Sha256 = (
        Get-FileHash `
            -Algorithm SHA256 `
            -Path $LocalPath
    ).Hash

    $RelativePath = $LocalPath.Replace(
        $RepoRoot + "\",
        ""
    )

    $RetrievedUtc = (
        Get-Date
    ).ToUniversalTime().ToString("o")

    Write-Host "  file: $RelativePath"
    Write-Host "  bytes: $($FileItem.Length)"
    Write-Host "  sha256: $Sha256"
    Write-Host ""

    $ManifestRows += [PSCustomObject]@{
        report_year       = $Year
        series_number     = $Report.series_number
        source_page_url   = $PageUrl
        pdf_url           = $PdfUrl
        original_filename = $OriginalFilename
        local_path        = $RelativePath
        bytes             = $FileItem.Length
        sha256            = $Sha256
        retrieved_utc     = $RetrievedUtc
        pdf_signature     = "PASS"
        acquisition_status = "PASS"
    }
}

$ManifestRows |
    Export-Csv `
        -Path $ManifestPath `
        -NoTypeInformation `
        -Encoding UTF8

$ExpectedCount = $Reports.Count
$ActualCount = $ManifestRows.Count

Write-Host ("=" * 88)
Write-Host "ACQUISITION SUMMARY"
Write-Host ("=" * 88)
Write-Host ""
Write-Host "Expected reports : $ExpectedCount"
Write-Host "Acquired reports : $ActualCount"
Write-Host ""

foreach ($Row in $ManifestRows) {
    Write-Host (
        "  " +
        $Row.report_year +
        " | " +
        $Row.bytes +
        " bytes | " +
        $Row.acquisition_status
    )
}

Write-Host ""
Write-Host "Manifest:"
Write-Host "  $ManifestPath"
Write-Host ""

if ($ActualCount -eq $ExpectedCount) {
    Write-Host "ETL-172C-1 RESULT: PASS"
}
else {
    Write-Host "ETL-172C-1 RESULT: FAIL"
    exit 1
}

Write-Host ""
Write-Host "Acquisition PASS certifies source preservation only."
Write-Host "No Rockefeller methodology or numerical result has been certified."