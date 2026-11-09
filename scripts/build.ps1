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
    Copy-Item -Path (Join-Path $cache '*.whl') -Destination $wheels

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
