$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes
Add-Type 'using System; using System.Runtime.InteropServices; public static class SaveButton { [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l); }'
$base = Split-Path -Parent $PSScriptRoot
$folder = New-Item -ItemType Directory -Path (Join-Path $env:TEMP ('pdfhub-check-'+[guid]::NewGuid().ToString('N')))
$sample = Join-Path $folder 'Documento con spazi.pdf'
python -B -c "import sys,pymupdf as p;d=p.open();d.new_page().insert_text((40,50),'Prova desktop');d.save(sys.argv[1])" $sample
$proc = Start-Process -FilePath (Join-Path $base 'PDFHub Desktop.lnk') -ArgumentList ('"'+$sample+'"') -PassThru
$root = [Windows.Automation.AutomationElement]::RootElement
$pidCondition = New-Object Windows.Automation.PropertyCondition ([Windows.Automation.AutomationElement]::ProcessIdProperty),$proc.Id
function Find-Element($label) {
    $condition = New-Object Windows.Automation.PropertyCondition ([Windows.Automation.AutomationElement]::NameProperty),$label
    for ($i=0; $i -lt 100; $i++){
        foreach ($win in $root.FindAll([Windows.Automation.TreeScope]::Children,$pidCondition)) {
            foreach($el in $win.FindAll([Windows.Automation.TreeScope]::Descendants,$condition)){
                if($label -eq 'Salva'){
                    if($el.Current.ClassName -eq 'Button' -and $el.Current.AutomationId -eq '1'){return $el}
                }elseif($el.Current.ControlType -eq [Windows.Automation.ControlType]::Button){return $el}
            }
        }
        Start-Sleep -Milliseconds 100
    }
    throw "Controllo non trovato: $label"
}
try {
    foreach ($label in @('Esporta','Estrai testo','Esegui e salva','Salva')) {
        $control = Find-Element $label
        if($label -eq 'Salva'){
            $null=[SaveButton]::PostMessage([IntPtr]$control.Current.NativeWindowHandle,0xF5,[IntPtr]::Zero,[IntPtr]::Zero)
        }else{
            $control.GetCurrentPattern([Windows.Automation.InvokePattern]::Pattern).Invoke()
        }
    }
    $output=Join-Path $folder 'Documento con spazi.txt'
    for ($i=0; $i -lt 80 -and !(Test-Path -LiteralPath $output); $i++) { Start-Sleep -Milliseconds 100 }
    if ((Get-Content -LiteralPath $output -Raw -Encoding UTF8).Trim() -ne 'Prova desktop') {throw 'Contenuto salvato errato.'}
    Write-Output 'Collegamento, orbita, editor e salvataggio Windows verificati.'
} finally {
    if (!$proc.HasExited) { $proc.Kill(); $proc.WaitForExit() }
    foreach ($file in @($sample, (Join-Path $folder 'Documento con spazi.txt'))) {
        if(Test-Path -LiteralPath $file){Remove-Item -LiteralPath $file}
    }
    if(!(Get-ChildItem -LiteralPath $folder)){Remove-Item -LiteralPath $folder}
}
