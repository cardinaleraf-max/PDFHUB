param([string]$Task, [string]$Folder)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$office = $null
$document = $null
$sharedPowerPoint = $false
try {
    if ($Task -eq 'scan') {
        $manager = New-Object -ComObject WIA.DeviceManager
        if (-not @($manager.DeviceInfos | Where-Object Type -eq 1).Count) {
            throw 'Nessuno scanner WIA disponibile. Collega lo scanner e riprova.'
        }
        $dialog = New-Object -ComObject WIA.CommonDialog
        $scan = $dialog.ShowAcquireImage(1, 0, 0, '{B96B3CAF-0728-11D3-9D7B-0000F81EF32E}', $true, $true, $false)
        if (-not $scan) { throw 'Acquisizione annullata.' }
        $scan.SaveFile((Join-Path $Folder 'scan.img'))
    } elseif ($Task -eq 'ocr') {
        Add-Type -AssemblyName System.Runtime.WindowsRuntime
        $null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
        $null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
        $null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
        $null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
        $asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
            $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
            $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
        } | Select-Object -First 1
        function Await-Result($Operation, $ResultType) {
            $pending = $asTask.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
            $pending.Wait()
            $pending.Result
        }
        $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
        if (-not $engine) { throw 'Installa il riconoscimento ottico per la tua lingua nelle impostazioni di Windows.' }
        foreach ($image in Get-ChildItem -LiteralPath $Folder -Filter '*.png') {
            $file = Await-Result ([Windows.Storage.StorageFile]::GetFileFromPathAsync($image.FullName)) ([Windows.Storage.StorageFile])
            $stream = Await-Result ($file.OpenAsync(0)) ([Windows.Storage.Streams.IRandomAccessStream])
            $decoder = Await-Result ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
            $bitmap = Await-Result ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
            $result = Await-Result ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
            $words = @(foreach ($line in $result.Lines) {
                foreach ($word in $line.Words) {
                    $rect = $word.BoundingRect
                    @{text=$word.Text; x=$rect.X; y=$rect.Y; w=$rect.Width; h=$rect.Height}
                }
            })
            $record = @{width=$bitmap.PixelWidth; words=$words} | ConvertTo-Json -Depth 4 -Compress
            [IO.File]::WriteAllText([IO.Path]::ChangeExtension($image.FullName, '.json'), $record)
            $bitmap.Dispose()
            $stream.Dispose()
        }
    } elseif ($Task -eq 'wordin') {
        $office = New-Object -ComObject Word.Application
        $office.Visible = $false
        $office.DisplayAlerts = 0
        $office.AutomationSecurity = 3
        $document = $office.Documents.Open((Join-Path $Folder 'input.docx'), $false, $true, $false)
        $document.ExportAsFixedFormat((Join-Path $Folder 'output.pdf'),17,$false,0,0,1,1,0,$false,$false,0,$true,$true,$false)
    } elseif ($Task -eq 'excelin') {
        $office = New-Object -ComObject Excel.Application
        $office.Visible = $false
        $office.DisplayAlerts = $false
        $office.AutomationSecurity = 3
        $document = $office.Workbooks.Open((Join-Path $Folder 'input.xlsx'),0,$true)
        $document.ExportAsFixedFormat(0,(Join-Path $Folder 'output.pdf'))
    } elseif ($Task -eq 'pptin') {
        $sharedPowerPoint = $null -ne (Get-Process -Name POWERPNT -ErrorAction SilentlyContinue | Select-Object -First 1)
        $office = New-Object -ComObject PowerPoint.Application
        $previousSecurity = $office.AutomationSecurity
        $previousAlerts = $office.DisplayAlerts
        $office.AutomationSecurity = 3
        $office.DisplayAlerts = 1
        $document = $office.Presentations.Open((Join-Path $Folder 'input.pptx'),-1,0,0)
        $document.SaveAs((Join-Path $Folder 'output.pdf'),32)
    } else { throw 'Operazione Windows sconosciuta.' }
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
} finally {
    if ($document) {
        if ($Task -in @('wordin','excelin')) { $document.Close(0) } else { $document.Close() }
    }
    if ($office) {
        if ($sharedPowerPoint) {
            $office.DisplayAlerts = $previousAlerts
            $office.AutomationSecurity = $previousSecurity
        } else { $office.Quit() }
    }
}
