import rasterio as rio
from rasterio import merge
from rasterio.enums import Resampling
from rasterio.warp import calculate_default_transform, reproject
from rasterio.io import MemoryFile
from rasterio.features import shapes
from rasterio.mask import mask

import numpy as np

import os

# adapted from https://medium.com/analytics-vidhya/python-for-geosciences-raster-merging-clipping-and-reprojection-with-rasterio-9f05f012b88a
def create_dataset(data, crs, transform):
    memfile = MemoryFile()
    dataset = memfile.open(driver="GTiff", height=data.shape[0], width=data.shape[1], count=1,
                           crs=crs, transform=transform, dtype=data.dtype, nodata=0)
    dataset.write(data, 1)

    return dataset

def add_labels(input_path, label_path):
    with rio.open(label_path, 'r', driver='GTiff') as label, \
         rio.open(input_path, 'r', driver='GTiff') as input:

        # copying metadat and updating for the new band count
        input_meta = input.meta
        input_meta.update(count=5)

        # reprojecting label layer to match the CRS and resolution of input
        label_reproj, label_reproj_trans = reproject(source=rio.band(label, 1),
                                                     dst_crs = input.profile['crs'],
                                                     dst_resolution=input.res,
                                                     resampling=rio.enums.Resampling.cubic_spline)
        
        label_ds = create_dataset(label_reproj[0], input.profile['crs'], label_reproj_trans)

        # cropping reprojected labels to input image's extent
        extents, _ = next(shapes(np.zeros_like(input.read(1)), transform=input.profile['transform']))
        cropped_label, crop_transf = mask(label_ds, [extents], crop=True)

        # updating label layer to have no data where input image has no data
        cropped_label_array = cropped_label[0][:input.shape[0], :input.shape[1]]
        cropped_label_array = np.where(input.read(1) == 0, 0, cropped_label_array)
        cropped_ds = create_dataset(cropped_label_array, input.profile['crs'], crop_transf)

        # print(reprojected_labels[0].shape)
        with rio.open('data/merged_img.tif', 'w', **input_meta) as dst:
            dst.write_band(1, input.read(1))
            dst.write_band(2, input.read(2))
            dst.write_band(3, input.read(3))
            dst.write_band(4, input.read(4))
            dst.write_band(5, reprojected_labels[0].astype(rio.uint16))

# example usage
# add_labels("data/268898_0369619_2016-10-15_0e14_BGRN_SR_clip.tif", "data/2016_08_reproj.tif")

# adapted from https://mmann1123.github.io/pyGIS/docs/e_raster_reproject.html
def reproject_image(reference_image, target_image):
    filepath, filename = os.path.split(target_image)
    file_base, file_extension = os.path.splitext(filename)
    with rio.open(reference_image) as dst, \
         rio.open(target_image) as src:

        src_transform = src.transform

        # getting the new transform for the reprojection
        dst_transform, width, height = calculate_default_transform(
            src.crs,
            dst.crs,
            src.width,
            src.height,
            *src.bounds
        )

        # updating destination metadata
        dst_meta = src.meta.copy()
        dst_meta.update(
            {
                "crs": dst.crs,
                "transform": dst_transform,
                "width": width,
                "height": height,
                "nodata": 0
            }
        )

        # constructing output filename/path
        out_name = file_base + "_reproj" + file_extension
        out_path = os.path.join(filepath, out_name)

        # writing repojected output
        with rio.open(out_path, 'w', **dst_meta) as output:
            reproject(
                source=rio.band(src, 1),
                destination=rio.band(output, 1),
                src_transform=src.transform,
                src_crs = src.crs,
                dst_transform = dst_transform,
                dst_crs=dst.crs,
                resampling=Resampling.bilinear
            )
    
# example usage of reproject_image()
# reference_image = "data/268898_0369619_2016-10-15_0e14_BGRN_SR_clip.tif"
# target_image = "data/2016_08.tif"
# reproject_image(reference_image, target_image)