from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


source = Path("diamonds_sorted.xlsx")
temporary = Path("diamonds_sorted.localized.xlsx")
replacements = {
    b"minecraft:deepslate_diamond_ore": "深板岩钻石".encode("utf-8"),
    b"minecraft:diamond_ore": "钻石".encode("utf-8"),
}

with ZipFile(source, "r") as source_zip, ZipFile(temporary, "w", ZIP_DEFLATED) as target_zip:
    for entry in source_zip.infolist():
        data = source_zip.read(entry.filename)
        if entry.filename.startswith("xl/worksheets/sheet"):
            for old, new in replacements.items():
                data = data.replace(old, new)
        target_zip.writestr(entry, data)

print(f"localized {temporary}")
