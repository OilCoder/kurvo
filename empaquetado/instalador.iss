; Instalador de Windows con Inno Setup 6: empaqueta la carpeta que dejó construir.bat.
;   iscc empaquetado\instalador.iss                       (variante sin deep learning, la habitual)
;   iscc /DCONDL empaquetado\instalador.iss               (variante completa)
; Instala por usuario sin pedir permisos de administrador (o para todos, si el usuario lo elige),
; crea los accesos directos, asocia los proyectos .kurvo y deja un desinstalador normal.
#ifdef CONDL
  #define Carpeta "Kurvo"
#else
  #define Carpeta "Kurvo-sinDL"
#endif
#define Version "1.0.0"
#define Repo "https://github.com/OilCoder/kurvo"

[Setup]
AppId={{6F1E3B52-6C38-4D4C-9B0E-56A1C0D2B404}
AppName=Kurvo
AppVersion={#Version}
AppVerName=Kurvo {#Version}
AppPublisher=OilCoder
AppPublisherURL={#Repo}
AppSupportURL={#Repo}/issues
AppUpdatesURL={#Repo}/releases
AppCopyright=Copyright 2026 OilCoder
VersionInfoVersion={#Version}
VersionInfoDescription=Instalador de Kurvo
DefaultDirName={autopf}\Kurvo
DefaultGroupName=Kurvo
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE.md
OutputDir=..\dist
OutputBaseFilename=Kurvo-1.0-setup
SetupIconFile=kurvo.ico
UninstallDisplayIcon={app}\{#Carpeta}.exe
UninstallDisplayName=Kurvo {#Version}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ChangesAssociations=yes
CloseApplications=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
spanish.Escritorio=Crear un acceso directo en el escritorio
english.Escritorio=Create a desktop shortcut
spanish.Asociar=Abrir los proyectos .kurvo con Kurvo
english.Asociar=Open .kurvo projects with Kurvo
spanish.Abrir=Abrir Kurvo
english.Abrir=Open Kurvo
spanish.Proyecto=Proyecto de Kurvo
english.Proyecto=Kurvo project

[Tasks]
Name: "escritorio"; Description: "{cm:Escritorio}"
Name: "asociar"; Description: "{cm:Asociar}"

[Files]
Source: "..\dist\{#Carpeta}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Kurvo"; Filename: "{app}\{#Carpeta}.exe"
Name: "{autodesktop}\Kurvo"; Filename: "{app}\{#Carpeta}.exe"; Tasks: escritorio

[Registry]
Root: HKA; Subkey: "Software\Classes\.kurvo"; ValueType: string; ValueData: "Kurvo.Proyecto"; Flags: uninsdeletevalue; Tasks: asociar
Root: HKA; Subkey: "Software\Classes\Kurvo.Proyecto"; ValueType: string; ValueData: "{cm:Proyecto}"; Flags: uninsdeletekey; Tasks: asociar
Root: HKA; Subkey: "Software\Classes\Kurvo.Proyecto\DefaultIcon"; ValueType: string; ValueData: "{app}\{#Carpeta}.exe,0"; Tasks: asociar
Root: HKA; Subkey: "Software\Classes\Kurvo.Proyecto\shell\open\command"; ValueType: string; ValueData: """{app}\{#Carpeta}.exe"" ""%1"""; Tasks: asociar

[Run]
Filename: "{app}\{#Carpeta}.exe"; Description: "{cm:Abrir}"; Flags: nowait postinstall skipifsilent
