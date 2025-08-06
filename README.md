# virtughan-qgis-plugin

A modular QGIS plugin for [VirtuGhan](https://pypi.org/project/virtughan/), designed to integrate remote sensing tools and visualization capabilities into the QGIS interface.

## Goal

To build a QGIS plugin for VirtuGhan, using the core logic provided by the [virtughan PyPI package](https://pypi.org/project/virtughan/) (`pip install virtughan`). No submodule setup required.

## Folder Structure

```

virtughan-qgis-plugin/
│
├── .venv/                    # Virtual environment
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
python3 -m venv .venv
source .venv/bin/activate
```

#### On Windows:

```powershell
python -m venv .venv
.venv\Scripts\activate
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
python tiler_logic.py
```

### Expected Output

```
Test passed. Image saved at: /home/yourname/test_tile_output.png
```


