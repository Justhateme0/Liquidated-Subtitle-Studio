param(
    [string] $Version = "1.0.0"
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Drawing

$root = Split-Path -Parent $PSScriptRoot
$assetsDir = Join-Path $root "installer-assets"
$iconPath = Join-Path $root "icon\icon.ico"

if (-not (Test-Path -LiteralPath $iconPath)) {
    throw "Installer icon was not found: $iconPath"
}

New-Item -ItemType Directory -Force -Path $assetsDir | Out-Null

$accent = [System.Drawing.ColorTranslator]::FromHtml("#8ACE00")
$dark = [System.Drawing.ColorTranslator]::FromHtml("#101113")
$mid = [System.Drawing.ColorTranslator]::FromHtml("#1C1F24")
$light = [System.Drawing.ColorTranslator]::FromHtml("#F4F7F8")
$muted = [System.Drawing.ColorTranslator]::FromHtml("#D7E0E2")

function New-GradientBrush {
    param(
        [System.Drawing.Rectangle] $Rect,
        [System.Drawing.Color] $StartColor,
        [System.Drawing.Color] $EndColor,
        [single] $Angle
    )

    return [System.Drawing.Drawing2D.LinearGradientBrush]::new($Rect, $StartColor, $EndColor, $Angle)
}

function Save-WizardImage {
    param(
        [int] $Width,
        [int] $Height,
        [string] $OutputPath,
        [bool] $Compact
    )

    $bitmap = [System.Drawing.Bitmap]::new($Width, $Height)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::ClearTypeGridFit

    try {
        $rect = [System.Drawing.Rectangle]::new(0, 0, $Width, $Height)
        $background = New-GradientBrush -Rect $rect -StartColor $dark -EndColor $mid -Angle 90
        $graphics.FillRectangle($background, $rect)
        $background.Dispose()

        $glowBrush = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(60, $accent))
        $graphics.FillEllipse($glowBrush, [System.Drawing.Rectangle]::new([int]($Width * 0.22), -24, [int]($Width * 0.88), [int]($Height * 0.6)))
        $graphics.FillEllipse($glowBrush, [System.Drawing.Rectangle]::new(-20, [int]($Height * 0.55), [int]($Width * 0.75), [int]($Height * 0.45)))
        $glowBrush.Dispose()

        $linePen = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(42, $light), 2)
        $graphics.DrawLine($linePen, -20, [int]($Height * 0.18), [int]($Width * 0.8), [int]($Height * 0.05))
        $graphics.DrawLine($linePen, [int]($Width * 0.35), [int]($Height * 0.68), [int]($Width + 24), [int]($Height * 0.88))
        $linePen.Dispose()

        $iconSize = if ($Compact) { [int]($Width * 0.58) } else { 86 }
        $iconX = [int](($Width - $iconSize) / 2)
        $iconY = if ($Compact) { 8 } else { 26 }
        $iconBitmap = [System.Drawing.Image]::FromFile($iconPath)
        $graphics.DrawImage($iconBitmap, $iconX, $iconY, $iconSize, $iconSize)
        $iconBitmap.Dispose()

        if (-not $Compact) {
            $titleFont = [System.Drawing.Font]::new("Segoe UI Semibold", 18, [System.Drawing.FontStyle]::Bold)
            $subtitleFont = [System.Drawing.Font]::new("Segoe UI", 8.5, [System.Drawing.FontStyle]::Regular)
            $captionFont = [System.Drawing.Font]::new("Segoe UI Semibold", 10, [System.Drawing.FontStyle]::Bold)
            $bodyFont = [System.Drawing.Font]::new("Segoe UI", 9, [System.Drawing.FontStyle]::Regular)
            $whiteBrush = [System.Drawing.SolidBrush]::new($light)
            $mutedBrush = [System.Drawing.SolidBrush]::new($muted)

            $graphics.DrawString("Liquidated", $titleFont, $whiteBrush, 24, 126)
            $graphics.DrawString("Subtitle Studio", $titleFont, $whiteBrush, 24, 150)
            $graphics.DrawString("Desktop installer", $subtitleFont, $mutedBrush, 25, 188)

            $badgeBrush = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(228, $accent))
            $graphics.FillRectangle($badgeBrush, 24, 222, 114, 28)
            $badgeBrush.Dispose()
            $graphics.DrawString("Version $Version", $captionFont, [System.Drawing.Brushes]::Black, 34, 228)

            $graphics.DrawString("Publisher", $subtitleFont, $mutedBrush, 25, 266)
            $graphics.DrawString("liquidated", $bodyFont, $whiteBrush, 25, 280)

            $titleFont.Dispose()
            $subtitleFont.Dispose()
            $captionFont.Dispose()
            $bodyFont.Dispose()
            $whiteBrush.Dispose()
            $mutedBrush.Dispose()
        }

        $bitmap.Save($OutputPath, [System.Drawing.Imaging.ImageFormat]::Png)
    }
    finally {
        $graphics.Dispose()
        $bitmap.Dispose()
    }
}

Save-WizardImage -Width 164 -Height 314 -OutputPath (Join-Path $assetsDir "wizard.png") -Compact:$false
Save-WizardImage -Width 55 -Height 55 -OutputPath (Join-Path $assetsDir "wizard-small.png") -Compact:$true
