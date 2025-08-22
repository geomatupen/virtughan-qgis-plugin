# VirtuGhan QGIS Plugin

A QGIS plugin that integrates [VirtuGhan](https://pypi.org/project/virtughan/) capabilities directly into QGIS for remote sensing workflows.

## Features

- **Tiler**: Real-time satellite tile visualization with custom band combinations
- **Engine**: Process and analyze satellite imagery with spectral indices
- **Extractor**: Bulk download and stack satellite data

## Quick Start

### Prerequisites

- QGIS 3.22 or higher
- Python 3.10+

### Installation

1. Clone the repository:
```bash
git clone https://github.com/geomatupen/virtughan-qgis-plugin.git
cd virtughan-qgis-plugin
```

2. Set up development environment with uv:
```bash
uv sync
```

3. Build the plugin:
```bash
./build.sh
```

4. Install in QGIS:
   - Go to `Plugins > Manage and Install Plugins > Install from ZIP`
   - Select `dist/virtughan-qgis-plugin.zip`

## Development

### Environment Setup

```bash
uv sync --group dev
source .venv/bin/activate
```

### Version Management

This project uses [Commitizen](https://commitizen-tools.github.io/commitizen/) for version management:

```bash
cz bump
cz changelog
```

### Building

```bash
./build.sh
```

The build script:
- Generates `metadata.txt` from `pyproject.toml`
- Creates a clean plugin package
- Outputs `dist/virtughan-qgis-plugin.zip`

## Links

- [Live Demo](https://virtughan.live/)
- [VirtuGhan Package](https://pypi.org/project/VirtuGhan/)
- [Documentation](https://github.com/kshitijrajsharma/VirtuGhan)

## License

GPL-3.0





