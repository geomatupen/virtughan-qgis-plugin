# virtughan-qgis-plugin
Qgis plugin of virtughan

Goal
To build a QGIS plugin for VirtuGhan, using the core logic provided by the virtughan PyPI package (pip install virtughan).
Folder Structure
virtughan-qgis-plugin/
│
├── .venv/
├── virtughan_qgis/           # Main plugin package
│   ├── tiler/
	├── 				 # Same structure as engine
│   ├── engine/
│   		├── __init__.py
├── engine_form.ui
├── engine_logic.py
├── engine_widget.py
│   ├── extractor/
		├── 				 # Same structure as engine
│   ├── utils/
│   └── main_plugin.py
│
├── virtughan_core/            # Submodule (VirtuGhan core repo) (optional only if virtughan is not a package in pip)
│
├── metadata.txt
├── requirements.txt
├── README.md
└── .gitmodules



Setup Instructions
1. Clone the Plugin Repository
git clone https://github.com/geomatupen/virtughan-qgis-plugin.git
cd virtughan-qgis-plugin

2. Set Up a Virtual Environment
On Linux/macOS:
python -m venv .venv     #replace python with python3 if python not available
source .venv/bin/activate
On Windows:
python -m venv .venv
.venv\Scripts\activate

3. Install Dependencies
Install required Python packages from PyPI:
pip install -r requirements.txt

4. Run a Test Script
Test if the plugin logic runs correctly:
cd virtughan_qgis/tiler
python tiler_logic.py
Expected output:
Test passed. Image saved at: /home/yourname/test_tile_output.png


