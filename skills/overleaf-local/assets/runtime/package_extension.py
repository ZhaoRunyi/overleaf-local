"""Package the dependency-free local extension as a VSIX for normal installation."""
import json
from pathlib import Path
import zipfile

source = Path(__file__).resolve().parent / "extension"
manifest = json.loads((source / "package.json").read_text())
output = Path("/tmp/overleaf-local-__PROJECT__.vsix")
vsix = f'''<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
<Metadata><Identity Language="en-US" Id="{manifest['name']}" Version="{manifest['version']}" Publisher="{manifest['publisher']}"/>
<DisplayName>{manifest['displayName']}</DisplayName><Description xml:space="preserve">{manifest['description']}</Description>
<Tags>workspace</Tags><Categories>Other</Categories><Properties>
<Property Id="Microsoft.VisualStudio.Code.Engine" Value="^1.90.0"/>
<Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="workspace"/>
</Properties></Metadata><Installation><InstallationTarget Id="Microsoft.VisualStudio.Code"/></Installation>
<Dependencies/><Assets><Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/></Assets></PackageManifest>'''
content_types = '''<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="json" ContentType="application/json"/><Default Extension="js" ContentType="application/javascript"/>
<Default Extension="vsixmanifest" ContentType="text/xml"/></Types>'''
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as package:
    package.writestr("extension.vsixmanifest", vsix)
    package.writestr("[Content_Types].xml", content_types)
    for file in source.iterdir():
        if file.is_file():
            package.write(file, "extension/" + file.name)
print(output)
