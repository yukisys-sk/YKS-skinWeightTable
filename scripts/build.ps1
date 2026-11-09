<#
.SYNOPSIS
    配布用の拡張機能 zip を dist/ に作る。

.DESCRIPTION
    si_weight_editor/ を一時フォルダへコピーし、リポジトリ直下の LICENSE と NOTICE.md、PySide6 の wheel を加えてから
    Blender の `extension build` で梱包する。MIT ライセンスの条件（著作権表記とライセンス文を
    配布物に含める）を満たすため、zip の中に LICENSE と NOTICE.md が入る。

.PARAMETER Blender
    blender.exe のパス。省略時は Blender 5.2 の標準インストール先。

.EXAMPLE
    .\scripts\build.ps1
#>
[CmdletBinding()]
param(
    [string]$Blender = 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath $Blender)) {
    throw "blender.exe が見つかりません: $Blender（-Blender でパスを指定してください）"
}

$stage = Join-Path ([IO.Path]::GetTempPath()) "siwe_build_$([guid]::NewGuid().ToString('N'))"
$src = Join-Path $stage 'si_weight_editor'
try {
    Copy-Item -LiteralPath (Join-Path $root 'si_weight_editor') -Destination $src -Recurse
    Get-ChildItem -LiteralPath $src -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $root 'LICENSE'), (Join-Path $root 'NOTICE.md') -Destination $src

    # PySide6 の wheel を同梱する（初回は PyPI から .wheels_cache へダウンロードする）
    $cache = Join-Path $root '.wheels_cache'
    if (-not (Get-ChildItem -LiteralPath $cache -Filter '*.whl' -ErrorAction SilentlyContinue)) {
        py -m pip download --dest $cache --platform win_amd64 --python-version 3.13 --only-binary=:all: PySide6-Essentials
        if ($LASTEXITCODE -ne 0) { throw "PySide6 の wheel のダウンロードに失敗しました（終了コード $LASTEXITCODE）" }
    }
    $wheels = Join-Path $src 'wheels'
    New-Item -ItemType Directory -Force -Path $wheels | Out-Null
    # Blender は wheel を <ユーザー設定>\extensions\.local\lib\python3.13\site-packages へ展開する。展開先のパスが
    # Windows の 260 文字に届くと展開が途中で止まるため、QtWidgets に不要で長いパスのファイル
    # （PySide6/qml/ と *.obj）を除いた wheel を同梱する（scripts/slim_wheel.py）。元の wheel は .wheels_cache に残る
    $slimTool = Join-Path $PSScriptRoot 'slim_wheel.py'
    foreach ($whl in Get-ChildItem -Path (Join-Path $cache '*.whl')) {
        $out = Join-Path $wheels $whl.Name
        py -3 $slimTool $whl.FullName $out
        if ($LASTEXITCODE -ne 0) { throw "wheel の軽量化に失敗しました: $($whl.Name)（終了コード $LASTEXITCODE）" }
    }
    $longest = 0
    foreach ($whl in Get-ChildItem -Path (Join-Path $wheels '*.whl')) {
        $line = py -3 $slimTool --longest $whl.FullName
        if ($LASTEXITCODE -ne 0) { throw "wheel の最長パスの取得に失敗しました: $($whl.Name)" }
        $longest = [Math]::Max($longest, [int]($line -split "`t")[0])
    }
    $siteRoot = Join-Path $env:APPDATA 'Blender Foundation\Blender\5.2\extensions\.local\lib\python3.13\site-packages'
    $total = $siteRoot.Length + 1 + $longest
    Write-Host "wheel 内の最長パス: $longest 文字。この PC の展開先では $total 文字（260 未満が必要）"
    if ($total -ge 260) { Write-Warning '展開先のパスが 260 文字以上になります。Windows の長いパスを有効にするか、ユーザー名を短くしてください' }

    $dist = Join-Path $root 'dist'
    New-Item -ItemType Directory -Force -Path $dist | Out-Null
    & $Blender --command extension validate $src
    if ($LASTEXITCODE -ne 0) { throw "マニフェストの検証に失敗しました（終了コード $LASTEXITCODE）" }
    & $Blender --command extension build --source-dir $src --output-dir $dist
    if ($LASTEXITCODE -ne 0) { throw "ビルドに失敗しました（終了コード $LASTEXITCODE）" }
}
finally {
    Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
}
