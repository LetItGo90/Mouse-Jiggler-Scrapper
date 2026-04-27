# ==============================================================
#   Proofpoint vs SharePoint Counter + Discrepancy Analyzer
# ==============================================================

$DefaultCsvPath = ".\alerts_export.csv"

# ---- HELPERS ----

function Get-WeekDates {
    $today = Get-Date
    $dow = [int]$today.DayOfWeek
    if ($dow -eq 0) { $dow = 7 }
    $monday = $today.AddDays(1 - $dow)
    return 0..6 | ForEach-Object { $monday.AddDays($_) }
}

function Parse-AnyDate([string]$val) {
    if ([string]::IsNullOrWhiteSpace($val)) { return $null }
    $d = [datetime]::MinValue
    if ([datetime]::TryParse($val.Trim(), [ref]$d)) { return $d }
    return $null
}

function Get-BizDayDiff([datetime]$from, [datetime]$to) {
    $n = 0; $cur = $from.Date
    while ($cur -lt $to.Date) {
        $cur = $cur.AddDays(1)
        if ($cur.DayOfWeek -ne 'Saturday' -and $cur.DayOfWeek -ne 'Sunday') { $n++ }
    }
    return $n
}

function IsSuspicious([string]$val) {
    if ([string]::IsNullOrWhiteSpace($val)) { return $true }
    $t = $val.Trim().ToLower()
    return ($t -in '_empty','n/a','none','null','unknown','-','na' -or $t.Length -le 1)
}

function Get-SessionNum([string]$id) {
    # Handles "CAI-26012035" or plain numbers
    $num = $id -replace '[^\d]', ''
    if ($num) { return [long]$num } else { return [long]0 }
}

# ---- LOAD CSV ----

$csvPath = $DefaultCsvPath
if (-not (Test-Path $csvPath)) {
    $csvPath = Read-Host "CSV not found. Enter path to alerts_export.csv"
    if (-not (Test-Path $csvPath)) {
        Write-Host "File not found. Exiting." -ForegroundColor Red
        exit
    }
}

$allRows   = Import-Csv $csvPath
$weekDates = Get-WeekDates
$dayNames  = 'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'

# ---- COUNT SP PER DAY ----

$spCounts = @{}
for ($i = 0; $i -le 6; $i++) {
    $d = $weekDates[$i]
    $spCounts[$i] = @($allRows | Where-Object {
        $ad = Parse-AnyDate $_.'Alert Date'
        $ad -and $ad.Date -eq $d.Date
    }).Count
}
$totalSP = ($spCounts.Values | Measure-Object -Sum).Sum

Write-Host ""
Write-Host ("─" * 54)
Write-Host ("  SharePoint Total this week: {0}" -f $totalSP)
Write-Host ("─" * 54)

# ---- ENTER PP COUNTS ----

$yn = Read-Host "`nEnter Proofpoint counts per day? (y/n)"
if ($yn -ne 'y') { Write-Host "Done."; exit }

Write-Host ""
Write-Host ("=" * 60)
Write-Host ("{0,-12}{1,-14}{2,-12}{3,-10}{4}" -f "Day","Date","Proofpoint","SharePoint","Status")
Write-Host ("=" * 60)

$ppCounts = @{}
for ($i = 0; $i -le 6; $i++) {
    $d    = $weekDates[$i]
    $name = $dayNames[$i]
    $raw  = Read-Host ("  {0} ({1}) - PP count (Enter to skip)" -f $name, $d.ToString('MM/dd'))

    if ([string]::IsNullOrWhiteSpace($raw)) { $ppCounts[$i] = $null; continue }

    $pp = [int]$raw
    $sp = $spCounts[$i]
    $ppCounts[$i] = $pp

    $diff   = $sp - $pp
    $status = if ($diff -eq 0) { "✓" } elseif ($diff -gt 0) { "X  SP +$diff" } else { "X  PP +$([Math]::Abs($diff))" }

    Write-Host ("{0,-12}{1,-14}{2,-12}{3,-10}{4}" -f $name, $d.ToString('MM/dd/yyyy'), $pp, $sp, $status)
}

$totalPP = ($ppCounts.Values | Where-Object { $_ -ne $null } | Measure-Object -Sum).Sum
Write-Host ("─" * 60)
Write-Host ("{0,-26}{1,-12}{2}" -f "TOTAL", $totalPP, $totalSP)
Write-Host ""

# ---- FIND DISCREPANCIES ----

$badDays = 0..6 | Where-Object { $ppCounts[$_] -ne $null -and $ppCounts[$_] -ne $spCounts[$_] }

if (-not $badDays) {
    Write-Host "✓ All counts match!" -ForegroundColor Green
    Write-Host "Done."
    exit
}

Write-Host "⚠  DISCREPANCIES FOUND:" -ForegroundColor Yellow
foreach ($i in $badDays) {
    $diff = $spCounts[$i] - $ppCounts[$i]
    $dir  = if ($diff -gt 0) { "SP EXTRA $diff" } else { "PP EXTRA $([Math]::Abs($diff))" }
    Write-Host ("   {0} ({1}): {2}  [PP={3} vs SP={4}]" -f `
        $dayNames[$i], $weekDates[$i].ToString('MM/dd'), $dir, $ppCounts[$i], $spCounts[$i]) -ForegroundColor Yellow
}

Write-Host ""
$doAnalysis = Read-Host "Run deep analysis on discrepancy days? (y/n)"
if ($doAnalysis -ne 'y') { Write-Host "Done."; exit }

# ---- DEEP ANALYSIS PER BAD DAY ----

foreach ($i in $badDays) {
    $date    = $weekDates[$i]
    $dayName = $dayNames[$i]

    Write-Host ""
    Write-Host ("=" * 60) -ForegroundColor Cyan
    Write-Host ("  DEEP ANALYSIS — {0}  {1}" -f $dayName, $date.ToString('MM/dd/yyyy')) -ForegroundColor Cyan
    Write-Host ("=" * 60) -ForegroundColor Cyan

    $dayRows = @($allRows | Where-Object {
        $ad = Parse-AnyDate $_.'Alert Date'
        $ad -and $ad.Date -eq $date.Date
    } | Sort-Object { Get-SessionNum $_.'Session ID' })

    Write-Host ("  SP records for this day: {0}" -f $dayRows.Count)

    # Next business day
    $nextBiz = $date.AddDays(1)
    while ($nextBiz.DayOfWeek -eq 'Saturday' -or $nextBiz.DayOfWeek -eq 'Sunday') {
        $nextBiz = $nextBiz.AddDays(1)
    }

    # ── CHECK 1: Session ID Sequence Anomaly ──────────────────
    Write-Host ""
    Write-Host "  [1] Session ID Sequence Check" -ForegroundColor Cyan

    if ($dayRows.Count -ge 2) {
        $ids   = $dayRows | ForEach-Object { Get-SessionNum $_.'Session ID' }
        $minId = ($ids | Measure-Object -Min).Minimum
        $maxId = ($ids | Measure-Object -Max).Maximum

        $gapRows = @($allRows | Where-Object {
            $n  = Get-SessionNum $_.'Session ID'
            $ad = Parse-AnyDate $_.'Alert Date'
            $n -gt $minId -and $n -lt $maxId -and $ad -and $ad.Date -ne $date.Date
        })

        if ($gapRows.Count -gt 0) {
            Write-Host ("  ⚠ {0} record(s) inside this day's Session ID range but have a DIFFERENT Alert Date:" -f $gapRows.Count) -ForegroundColor Yellow
            foreach ($r in $gapRows) {
                Write-Host ("    {0}  →  Alert Date: {1}" -f $r.'Session ID', $r.'Alert Date') -ForegroundColor Yellow
            }
        } else {
            Write-Host "  ✓ No sequence anomalies" -ForegroundColor Green
        }
    } else {
        Write-Host "  (Not enough records to check sequence)" -ForegroundColor DarkGray
    }

    # ── CHECK 2: Impossible Timeline Violations ───────────────
    Write-Host ""
    Write-Host "  [2] Timeline Violations" -ForegroundColor Cyan
    # NOTE: Alert Date → Action Date being next day is NORMAL (end of day alerts)
    # Only flagging truly impossible or very long gaps

    $tlIssues = @()
    foreach ($r in $dayRows) {
        $sid  = $r.'Session ID'
        $ad   = Parse-AnyDate $r.'Alert Date'
        $act  = Parse-AnyDate $r.'Action Date'
        $comp = Parse-AnyDate $r.'AnalysisCompletionDate'
        $prS  = Parse-AnyDate $r.'Peer_Review_Start'
        $prE  = Parse-AnyDate $r.'Peer_Review_End'

        # Impossible: Action before Alert
        if ($act -and $ad -and $act.Date -lt $ad.Date) {
            $tlIssues += "$sid : Action Date ($($r.'Action Date')) BEFORE Alert Date ($($r.'Alert Date'))  ← impossible"
        }
        # Impossible: Completion before Action
        if ($comp -and $act -and $comp.Date -lt $act.Date) {
            $tlIssues += "$sid : Completion ($($r.'AnalysisCompletionDate')) BEFORE Action Date ($($r.'Action Date'))  ← impossible"
        }
        # Impossible: Peer Review End before Start
        if ($prE -and $prS -and $prE.Date -lt $prS.Date) {
            $tlIssues += "$sid : Peer Review End ($($r.'Peer_Review_End')) BEFORE Start ($($r.'Peer_Review_Start'))  ← impossible"
        }
        # Unusually long: Alert to Completion > 5 business days
        if ($comp -and $ad) {
            $biz = Get-BizDayDiff $ad $comp
            if ($biz -gt 5) {
                $tlIssues += "$sid : Alert → Completion = $biz business days ($($r.'Alert Date') → $($r.'AnalysisCompletionDate'))  ← unusually long"
            }
        }
    }

    if ($tlIssues) {
        Write-Host "  ⚠ Issues found:" -ForegroundColor Yellow
        $tlIssues | ForEach-Object { Write-Host "    $_" -ForegroundColor Yellow }
    } else {
        Write-Host "  ✓ No timeline violations" -ForegroundColor Green
    }

    # ── CHECK 3: Empty / Suspicious Fields ───────────────────
    Write-Host ""
    Write-Host "  [3] Empty / Suspicious Fields" -ForegroundColor Cyan

    $critFields = 'Alert Rule','Status','ACF2ID','Analyst Name','Sign-off status'
    $fldIssues  = @()

    foreach ($r in $dayRows) {
        foreach ($f in $critFields) {
            if (IsSuspicious $r.$f) {
                $fldIssues += "$($r.'Session ID') : '$f' empty/suspicious  →  '$($r.$f)'"
            }
        }
    }

    if ($fldIssues) {
        Write-Host "  ⚠ Issues found:" -ForegroundColor Yellow
        $fldIssues | ForEach-Object { Write-Host "    $_" -ForegroundColor Yellow }
    } else {
        Write-Host "  ✓ All critical fields look populated" -ForegroundColor Green
    }

    # ── CHECK 4: Next Business Day Bleed ─────────────────────
    Write-Host ""
    Write-Host ("  [4] Adjacent Day Bleed Check  ({0} ↔ {1})" -f $date.ToString('MM/dd'), $nextBiz.ToString('MM/dd')) -ForegroundColor Cyan

    $nextRows = @($allRows | Where-Object {
        $ad = Parse-AnyDate $_.'Alert Date'
        $ad -and $ad.Date -eq $nextBiz.Date
    })

    if ($dayRows.Count -gt 0 -and $nextRows.Count -gt 0) {
        $dayIds  = $dayRows  | ForEach-Object { Get-SessionNum $_.'Session ID' }
        $nextIds = $nextRows | ForEach-Object { Get-SessionNum $_.'Session ID' }
        $dayMax  = ($dayIds  | Measure-Object -Max).Maximum
        $nxtMin  = ($nextIds | Measure-Object -Min).Minimum

        if ($nxtMin -le $dayMax) {
            Write-Host "  ⚠ Session ID overlap — possible bleed between days:" -ForegroundColor Yellow
            Write-Host ("    {0} max Session ID : {1}" -f $dayName, $dayMax) -ForegroundColor Yellow
            Write-Host ("    {0} min Session ID : {1}" -f $nextBiz.ToString('MM/dd'), $nxtMin) -ForegroundColor Yellow
        } else {
            Write-Host "  ✓ Session IDs cleanly separated between days" -ForegroundColor Green
        }
    } else {
        Write-Host "  (Not enough data on one or both days to compare)" -ForegroundColor DarkGray
    }

    # ── SUGGESTED ACTION ─────────────────────────────────────
    Write-Host ""
    Write-Host "  ► Suggested Action:" -ForegroundColor White
    Write-Host ("    1. Filter SP by Alert Date = {0}" -f $date.ToString('MM/dd/yyyy')) -ForegroundColor White
    Write-Host ("    2. Also check {0} for any bleed-over alerts" -f $nextBiz.ToString('MM/dd/yyyy')) -ForegroundColor White
    Write-Host ("    3. Review flagged Session IDs above manually" ) -ForegroundColor White
}

Write-Host ""
Write-Host "Done."
