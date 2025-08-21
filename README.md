# virtughan-qgis-plugin
The `virtughan qgis plugin` integrates the capabilities of the [VirtuGhan](https://pypi.org/project/virtughan/) Python package directly into QGIS. It provides a modular interface for performing remote sensing tasks, such as tiling, extraction, and visualization of satellite data, within the familiar QGIS environment.

This plugin is part of the broader **VirtuGhan** initiative, which aims to support accessible Earth observation workflows for humanitarian and environmental applications. By using the PyPI-distributed `virtughan` package, this QGIS plugin remains lightweight, maintainable, and easy to update without duplicating core logic.

VirtuGhan is an open-source, Python-based geospatial pipeline designed for on-the-fly raster tile computation using Cloud-Optimized GeoTIFFs (COGs) and Spatiotemporal Asset Catalog (STAC) endpoints. It enables real-time, scalable satellite data visualization and analysis with minimal infrastructure overhead.

By computing raster results dynamically for specific bounding boxes of interest (rather than downloading entire scenes), VirtuGhan offers a cost-effective and efficient solution for handling high-resolution Earth Observation data such as Sentinel-2. This makes it particularly well-suited for applications in land monitoring, agriculture, disaster management, and environmental science.
To learn more about VirtuGhan, visit: 
```
Live Demo: https://virtughan.live/
GitHub Link: https://github.com/kshitijrajsharma/VirtuGhan 
Python Package: https://pypi.org/project/VirtuGhan/ 
```
## Core Functionalities

The QGIS plugin will expose three core features of VirtuGhan through a dock widget (with three tabs) and Processing Toolbox integration:

### 1. Tiler (Live View)

A lightweight, real-time tile renderer that:

- Fetches COG-based satellite tiles using x/y/z coordinates  
- Computes user-defined band combinations or indices (e.g., NDVI)  
- Supports high-resolution, on-demand visualization without full scene downloads  

### 2. Engine (Analyzer)

A processing module that:

- Retrieves Sentinel/Landsat imagery based on date, area of interest (AOI), and cloud cover  
- Computes spectral indices and aggregates them over time  
- Outputs ready-to-use GeoTIFFs or time series datasets  

### 3. Extractor (Downloader)

A bulk downloader that:

- Fetches raw satellite bands within a bounding box and time range  
- Resamples and aligns data to a common grid  
- Stacks them into multi-band GeoTIFFs for offline analysis or machine learning training  

## QGIS Integration

The plugin will allow users to:

- Interact with VirtuGhan directly inside QGIS  
- Choose functionality via tabs in a dock widget UI (built using Qt Designer)  
- Configure inputs like date range, cloud cover, band combinations, and output paths  
- Automatically add results (tiles, rasters) to the QGIS canvas  
- Run tools interactively or via the Processing Toolbox and Modeler  


## Folder Structure

```

virtughan-qgis-plugin/
│
├── venv/                    # Virtual environment
├── virtughan\_qgis/           # Main plugin package
│   ├── tiler/
│   ├── engine/
│   │   ├── **init**.py
│   ├── extractor/
│   ├── utils/
│   ├── engine\_form.ui
│   ├── engine\_logic.py
│   ├── engine\_widget.py
│   └── main\_plugin.py
│
├── metadata.txt
├── requirements.txt
├── README.md

````

## Setup Instructions

### 1. Clone the Plugin Repository

```bash
git clone https://github.com/geomatupen/virtughan-qgis-plugin.git
cd virtughan-qgis-plugin
````

### 2. Set Up a Virtual Environment

#### On Linux/macOS:

```bash
python3 -m venv venv
source venv/bin/activate
```

#### On Windows:

```powershell
python -m venv venv
venv\Scripts\activate
```

### 3. Install Dependencies

Install all required packages including the core `virtughan` package:

```bash
pip install virtughan numpy pillow matplotlib rio-tiler shapely aiocache mercantile
```

Or install via requirements file:

```bash
pip install -r requirements.txt
```

### 4. Run a Test Script

Navigate to the test module and run the logic:

```bash
cd virtughan_qgis/tiler
python tiler_logic_test.py
```

### Expected Output

```
Test passed. Image saved at: /home/yourname/test_tile_output.png
```




import sys

# 1) Make sure pip is importable (usually already true on 3.34)
To make sure the pip is installed and virtughan is also installed on qgis python, follow these:
1. go to plugins > python
2. in the python console run these codes
```
try:
    import pip  # noqa
except Exception:
    import ensurepip
    ensurepip.bootstrap()
    import pip  # noqa
```

# 2) Helper that invokes pip inside the current Python, no subprocess/QGIS relaunch
```
def qgis_pip(args):
    import pip._internal
    print("pip", " ".join(args))
    rc = pip._internal.main(args)
    if rc != 0:
        raise RuntimeError(f"pip failed with exit code {rc}")
```

# 3) Upgrade pip (optional) and install virtughan
```
qgis_pip(["install", "--upgrade", "pip"])
qgis_pip(["install", "virtughan"])
```

# 4) Verify
```
from importlib.metadata import version, packages_distributions
import vcube, inspect, os

print("virtughan version:", version("virtughan"))
print("vcube loaded from:", os.path.abspath(inspect.getfile(vcube)))
```


# Quick Check: 
```
from vcube.engine import VCubeProcessor
bbox = [83.98744091391563,28.20125131106528,83.98802295327187,28.202072732710718]  # small bbox
proc = VCubeProcessor(
    bbox=bbox,
    start_date="2025-07-20",
    end_date="2025-08-20",
    cloud_cover=100,
    formula="(band2-band1)/(band2+band1)",
    band1="red",
    band2="nir",
    operation="median",
    timeseries=False,
    output_dir=r"C:\Users\ROG\Documents\virtughan_test",
    workers=1,
    smart_filter=True,
)
print("Processor created OK")
# Optional: run a tiny compute (may take a bit and hit network)
proc.compute()
```

Then you can install the plugin offline from files. 

important folders: \\wsl.localhost\Ubuntu\home\upen\projects\virtughan-qgis-plugin

C:\Users\ROG\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins







