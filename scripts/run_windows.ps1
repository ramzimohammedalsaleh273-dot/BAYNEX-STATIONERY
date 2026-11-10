# BAYNEX STATIONERY — Windows launcher
$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot

$PythonLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($PythonLauncher) {
    & $PythonLauncher.Source -3 -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11 or newer is required'"
    if ($LASTEXITCODE -ne 0) {
        throw "يلزم تثبيت Python 3.11 أو أحدث."
    }
    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        & $PythonLauncher.Source -3 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw "تعذر إنشاء بيئة Python الافتراضية." }
    }
} else {
    $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $PythonCommand) {
        throw "لم يتم العثور على Python. ثبّت Python 3.11 أو أحدث ثم أعد التشغيل."
    }
    & $PythonCommand.Source -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11 or newer is required'"
    if ($LASTEXITCODE -ne 0) { throw "يلزم تثبيت Python 3.11 أو أحدث." }
    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        & $PythonCommand.Source -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw "تعذر إنشاء بيئة Python الافتراضية." }
    }
}

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
& $VenvPython -m pip install -e .
if ($LASTEXITCODE -ne 0) {
    throw "فشل تثبيت متطلبات البرنامج. تحقق من اتصال الإنترنت ثم أعد تشغيل هذا الملف."
}

& $VenvPython (Join-Path $ProjectRoot "main.py")
if ($LASTEXITCODE -ne 0) {
    throw "توقف البرنامج بسبب خطأ. راجع رسالة الخطأ الظاهرة."
}
