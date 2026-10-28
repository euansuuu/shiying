param(
    [string]$SdkRoot = $env:ANDROID_HOME,
    [string]$JavaHome = $env:JAVA_HOME
)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$workspaceRoot = Split-Path $projectRoot -Parent
if (-not $SdkRoot -and (Test-Path "$workspaceRoot\.tools\android-sdk")) { $SdkRoot = "$workspaceRoot\.tools\android-sdk" }
if (-not $JavaHome -and (Test-Path 'C:\Environment\Java\jdk-17\bin\java.exe')) { $JavaHome = 'C:\Environment\Java\jdk-17' }
if (-not (Test-Path "$JavaHome\bin\keytool.exe")) { throw '请设置 JAVA_HOME，使用 JDK 17 或 21。' }
if (-not (Test-Path "$SdkRoot\platforms\android-35\android.jar")) { throw '请设置 ANDROID_HOME，并安装 Android SDK Platform 35 和 Build-Tools 35.0.0。' }
$env:JAVA_HOME = (Resolve-Path $JavaHome).Path
$env:ANDROID_HOME = (Resolve-Path $SdkRoot).Path
$env:GRADLE_USER_HOME = "$workspaceRoot\.tools\gradle-home"
$env:PATH = "$env:JAVA_HOME\bin;$env:PATH"
$sdkProperty = 'sdk.dir=' + $env:ANDROID_HOME.Replace('\','/')
[IO.File]::WriteAllText("$projectRoot\native\local.properties", $sdkProperty + "`n", [Text.UTF8Encoding]::new($false))
$previousLocation = Get-Location
try {
    Set-Location $projectRoot
    & npm.cmd ci --no-audit --no-fund
    if ($LASTEXITCODE) { throw '前端依赖安装失败。' }
    & npm.cmd test
    if ($LASTEXITCODE) { throw '解析脚本测试失败。' }
    & npm.cmd run sync
    if ($LASTEXITCODE) { throw '界面编译或原生同步失败。' }

    $signingRoot = Join-Path $projectRoot '.signing'
    $signingProperties = Join-Path $signingRoot 'release.properties'
    $keystorePath = Join-Path $signingRoot 'shiying-release.jks'
    if (-not (Test-Path $signingProperties)) {
        if (Test-Path $keystorePath) { throw '签名文件已存在但配置丢失，请恢复 release.properties，避免生成不同签名。' }
        New-Item -ItemType Directory -Force $signingRoot | Out-Null
        $secretBytes = New-Object byte[] 32
        $random = [Security.Cryptography.RandomNumberGenerator]::Create()
        $random.GetBytes($secretBytes)
        $random.Dispose()
        $signingSecret = [Convert]::ToBase64String($secretBytes)
        $keyArguments = @('-genkeypair','-keystore',$keystorePath,'-storetype','JKS','-storepass',$signingSecret,'-keypass',$signingSecret,'-alias','shiying','-keyalg','RSA','-keysize','3072','-validity','10000','-dname','CN=Shiying Local, O=Shiying, C=CN','-noprompt')
        & "$env:JAVA_HOME\bin\keytool.exe" @keyArguments
        if ($LASTEXITCODE) { throw '创建本机发布签名失败。' }
        $properties = "storeFile=$($keystorePath.Replace('\','/'))`nstorePassword=$signingSecret`nkeyAlias=shiying`nkeyPassword=$signingSecret`n"
        [IO.File]::WriteAllText($signingProperties, $properties, [Text.UTF8Encoding]::new($false))
        $signingSecret = $null
    }
    $localGradle = "$workspaceRoot\.tools\gradle-8.11.1\bin\gradle.bat"
    $gradle = if (Test-Path $localGradle) { $localGradle } else { "$projectRoot\native\gradlew.bat" }
    & $gradle -p "$projectRoot\native" :app:testDebugUnitTest :app:lintRelease :app:assembleRelease --no-daemon --console=plain
    if ($LASTEXITCODE) { throw '原生编译、检查或测试失败，请查看 Gradle 报错。' }
    $outputRoot = Join-Path $projectRoot 'releases'
    New-Item -ItemType Directory -Force $outputRoot | Out-Null
    $apkPath = Join-Path $outputRoot 'Shiying-0.1.5-android.apk'
    Copy-Item -LiteralPath "$projectRoot\native\app\build\outputs\apk\release\app-release.apk" -Destination $apkPath -Force
    & "$env:ANDROID_HOME\build-tools\35.0.0\apksigner.bat" verify --verbose $apkPath
    if ($LASTEXITCODE) { throw 'APK 签名校验失败。' }
    $hash = (Get-FileHash -LiteralPath $apkPath -Algorithm SHA256).Hash.ToLowerInvariant()
    [IO.File]::WriteAllText("$apkPath.sha256", "$hash  Shiying-0.1.5-android.apk`n", [Text.UTF8Encoding]::new($false))
    Write-Host "APK: $apkPath"
    Write-Host "SHA256: $hash"
    Write-Host '请备份 android/.signing；后续更新必须使用同一签名。'
} finally { Set-Location $previousLocation }
