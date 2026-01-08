#!/usr/bin/env python3
import sys
from pathlib import Path
from PIL import Image

def strip_exif(source_dir: Path, target_dir: Path):
    if not source_dir.exists():
        print(f"Source directory {source_dir} does not exist.")
        return

    target_dir.mkdir(parents=True, exist_ok=True)
    
    extensions = {".jpg", ".jpeg", ".png", ".webp"}
    count = 0
    
    for file_path in source_dir.iterdir():
        if file_path.suffix.lower() in extensions:
            try:
                # Open image
                with Image.open(file_path) as img:
                    # Create a new image without metadata
                    # Copying data to a new image ensures metadata is gone
                    data = list(img.getdata())
                    clean_img = Image.new(img.mode, img.size)
                    clean_img.putdata(data)
                    
                    # Target path
                    target_path = target_dir / file_path.name
                    
                    # Save without extra info
                    # For JPEG, simply saving often strips most metadata if not explicitly kept,
                    # but creating a new image is safer.
                    # Alternatively, simpler approach:
                    # data = img.tobytes()
                    # clean_img = Image.frombytes(img.mode, img.size, data)
                     
                    # Most robust way to just strip EXIF is often:
                    # Save to target, passing no exif data.
                    # But some data might persist in info dictionary.
                    # So we clear it.
                    
                    # We can also just save the original image object but delete .info["exif"] if present
                    if "exif" in img.info:
                        del img.info["exif"]
                    
                    # Save
                    img.save(target_path)
                    count += 1
                    print(f"Cleaned: {file_path.name}")
            except Exception as e:
                print(f"Failed to process {file_path.name}: {e}")

    print(f"Processed {count} images. Saved to {target_dir}")

if __name__ == "__main__":
    assets_dir = Path("assets")
    clean_dir = Path("assets_clean")
    strip_exif(assets_dir, clean_dir)
