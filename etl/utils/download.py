from pathlib import Path
import requests


def download_file(url: str, destination: Path, overwrite: bool = False) -> Path:
    """
    Download a file from a URL to a local destination.
    """

    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.exists() and not overwrite:
        print(f"Using existing file: {destination.name}")
        return destination

    print(f"Downloading {url}")

    response = requests.get(url, stream=True, timeout=60)
    response.raise_for_status()

    with open(destination, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    print(f"Saved to {destination}")

    return destination