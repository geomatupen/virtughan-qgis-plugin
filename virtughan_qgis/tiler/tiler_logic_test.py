import sys
import os
import numpy as np
from PIL import Image
from vcube.tile import TileProcessor 


def test_tileprocessor_colormap():
    if TileProcessor is None:
        print("TileProcessor not available. Skipping test.")
        return

    test_array = np.random.rand(256, 256)

    try:
        image = TileProcessor.apply_colormap(test_array, "viridis")
        output_path = os.path.join(os.path.expanduser("~"), "projects/virtughan-qgis-plugin//static/outputs/test_tile_output.png")
        image.save(output_path)
        print(f"Test passed. Image saved at: {output_path}")
    except Exception as ex:
        print("Test failed with exception:", ex)


if __name__ == "__main__":
    test_tileprocessor_colormap()
