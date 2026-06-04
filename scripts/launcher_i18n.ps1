param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("show-main", "show-cleanup", "warn-backend-port")]
    [string]$Mode,

    [Parameter(Mandatory = $false)]
    [ValidateSet("zh", "en")]
    [string]$Lang = "en"
)

$isZh = $Lang -eq "zh"

function Decode-Text {
    param([string]$Value)
    [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($Value))
}

function Write-MenuLine {
    param([string]$Text = "")
    [Console]::Error.WriteLine($Text)
}

function Write-Prompt {
    param([string]$Text)
    [Console]::Error.Write($Text)
}

function Show-MainMenu {
    if ($isZh) {
        Write-MenuLine "==================================================="
        Write-MenuLine (Decode-Text "IAAgACAAIAAgACAAIAAgACAAIAAgAE0AZQBnAGEAdAByAG8AbgAgAEZotmcvVKhSaFY=")
        Write-MenuLine "==================================================="
        Write-MenuLine
        Write-MenuLine (Decode-Text "IAAgACAAMQAuACAAL1SoUmhR6JAI/w5U73ogAEEAUABJACAAKwAgAE1S73oJ/w==")
        Write-MenuLine (Decode-Text "IAAgACAAMgAuACAAxU4vVKhSIABQAHkAdABoAG8AbgAgAA5U73oI/0MATABJACAAIWoPXwn/")
        Write-MenuLine (Decode-Text "IAAgACAAMwAuACAABW4GdKF7BnRoVg==")
        Write-MenuLine (Decode-Text "IAAgACAANAAuACAAiVvFiPpXQHivc4NYCP9QAHkAdABoAG8AbgABMEQAbwBjAGsAZQByAAEwTgBvAGQAZQAuAGoAcwAJ/w==")
        Write-MenuLine (Decode-Text "IAAgACAAMAAuACAAAJD6UQ==")
        Write-MenuLine
        Write-MenuLine "==================================================="
        Write-Prompt (Decode-Text "94uTj2VRCZB5mCAAKAAwAC0ANAApADoAIAA=")
        return
    }

    Write-MenuLine "==================================================="
    Write-MenuLine "           Megatron Framework Launcher"
    Write-MenuLine "==================================================="
    Write-MenuLine
    Write-MenuLine "   1. Start All (Backend API + Frontend)"
    Write-MenuLine "   2. Start Python Backend only (CLI mode)"
    Write-MenuLine "   3. Cleanup Manager"
    Write-MenuLine "   4. Install Base Environment (Python, Docker, Node.js)"
    Write-MenuLine "   0. Exit"
    Write-MenuLine
    Write-MenuLine "==================================================="
    Write-Prompt "Enter option (0-4): "
}

function Show-CleanupMenu {
    if ($isZh) {
        Write-MenuLine "==================================================="
        Write-MenuLine (Decode-Text "IAAgACAAIAAgACAAIAAJkOliBW4GdO52B2g=")
        Write-MenuLine "==================================================="
        Write-MenuLine
        Write-MenuLine (Decode-Text "IAAgACAAMQAuACAA8W2mXgVuBnQI/2hR6JAJ/w==")
        Write-MenuLine (Decode-Text "IAAgACAAMgAuACAAzZFufyAARABvAGMAawBlAHIAIABwZW5jk14=")
        Write-MenuLine (Decode-Text "IAAgACAAMwAuACAABW4GdCAAUAB5AHQAaABvAG4AIACvc4NYCP92AGUAbgB2AAEwE39YWwn/")
        Write-MenuLine (Decode-Text "IAAgACAANAAuACAABW4GdE1S73qdT1aNCP9uAG8AZABlAF8AbQBvAGQAdQBsAGUAcwAJ/w==")
        Write-MenuLine (Decode-Text "IAAgACAANQAuACAABW56evlb3YuMVLCLxl8I/91PWXWdT1aNCf8=")
        Write-MenuLine (Decode-Text "IAAgACAAMAAuACAA1lOIbQ==")
        Write-MenuLine
        Write-MenuLine "==================================================="
        Write-Prompt (Decode-Text "94sJkOliIAAoADAALQA1ACkAOgAgAA==")
        return
    }

    Write-MenuLine "==================================================="
    Write-MenuLine "       Select cleanup target"
    Write-MenuLine "==================================================="
    Write-MenuLine
    Write-MenuLine "   1. Deep clean (all)"
    Write-MenuLine "   2. Reset Docker databases"
    Write-MenuLine "   3. Clean Python environment (venv, cache)"
    Write-MenuLine "   4. Clean frontend dependencies (node_modules)"
    Write-MenuLine "   5. Clear conversations and memory only"
    Write-MenuLine "   0. Cancel"
    Write-MenuLine
    Write-MenuLine "==================================================="
    Write-Prompt "Enter option (0-5): "
}

switch ($Mode) {
    "show-main" {
        Show-MainMenu
        break
    }
    "show-cleanup" {
        Show-CleanupMenu
        break
    }
    "warn-backend-port" {
        if ($isZh) {
            Write-MenuLine (Decode-Text "WwBXAEEAUgBOAF0AIAAOVO9673rjU4dl9k4aXCpnMVzqfhv/TVLvehpPKFcAl4GJ9mV/Tyh12J6kiyAAQQBQAEkAIAAwV0BXAjA=")
        } else {
            Write-MenuLine "[WARN] Backend port file was not ready yet; frontend will use the default API base if needed."
        }
        break
    }
}
