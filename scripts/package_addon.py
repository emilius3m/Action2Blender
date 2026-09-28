"""Build the Blender add-on ZIP from the source directory."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "addon" / "action2blender"
DESTINATION = ROOT / "dist" / "Action2Blender-addon-0.1.0.zip"


def main() -> None:
    DESTINATION.parent.mkdir(exist_ok=True)
    with ZipFile(DESTINATION, "w", ZIP_DEFLATED) as archive:
        for source in sorted(SOURCE.glob("*.py")):
            archive.write(source, f"action2blender/{source.name}")
        archive.write(ROOT / "LICENSE", "action2blender/LICENSE")
    print(DESTINATION)


if __name__ == "__main__":
    main()
