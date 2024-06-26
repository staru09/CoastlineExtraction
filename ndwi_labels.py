import rasterio as rio
from rasterio import mask
from rasterio.plot import show
from rasterio.mask import mask
from rasterio.io import MemoryFile
import shapely
from shapely.geometry import Polygon, shape
import geopandas as gpd
import os
from matplotlib import pyplot as plt
import numpy as np
import cv2

def create_transect_points(transect_path, line_path, out_path):
    transects = gpd.read_file(transect_path)
    coastline = gpd.read_file(line_path)
    points = coastline.unary_union.intersection(transects.unary_union)
    fig, ax = plt.subplots(figsize=(14,14))
    plot_points = gpd.GeoSeries(points)
    plot_points.plot(ax=ax, color='green')
    transects.plot(ax=ax, color='red')
    coastline.plot(ax=ax, color='blue')

    plt.show()

    plot_points.to_file(out_path)


def clip_shp(path_to_shp, boundary_geojson):
    path_name = os.path.dirname(path_to_shp) + "/"
    shp_name = os.path.basename(path_to_shp)
    shp_base, shp_extension = os.path.splitext(shp_name)
    shp_data = gpd.read_file(path_to_shp)

    poly_boundary = Polygon(shape(boundary_geojson))

    shp_clipped = gpd.clip(shp_data, poly_boundary)
    fig, ax = plt.subplots(figsize=(12,8))
    shp_data.plot(ax=ax, color='red')
    plot_shp = gpd.GeoSeries(poly_boundary)
    plot_shp.plot(ax=ax, color='green')
    plt.show()

    out_path = path_name + shp_base + "_clipped.shp"
    shp_clipped.to_file(out_path)


def get_ndwi_label(image_path, points_path, ksize = 100):
    # establish the ndwi calculation and copy metadata
    with rio.open(image_path, driver='GTiff') as src_raster:
        green = src_raster.read(2).astype(np.float32)
        nir_num = src_raster.count  # adjusting NIR band to 4 or 5 band images
        nir = src_raster.read(nir_num).astype(np.float32)
        np.seterr(divide='ignore', invalid='ignore')
        ndwi = (green - nir) / (green + nir)
        ndwi[np.isnan(ndwi)] = 0
        
        print("Green max: {}".format(green.max()))
        print("NIR max: {}".format(nir.max()))
        print("NDWI max: {}".format(np.nanmax(ndwi)))
        print("NDWI min: {}".format(np.nanmin(ndwi)))
        ndwi_profile = src_raster.profile
        # blank label layer
        label = np.zeros((src_raster.height, src_raster.width)).astype(np.uint8)
        agg_mask = np.zeros((src_raster.height, src_raster.width)).astype(np.uint8)
        src_CRS = src_raster.crs
        # getting pixel size for correct calculation of buffer
        pixel_size = abs(src_raster.transform[0])
        figs, ax = plt.subplots(figsize=(12, 8))
        show(ndwi, transform=src_raster.transform, ax=ax, cmap='gray')

    # preparing points for creating label masks
    points_shp = gpd.read_file(points_path)
    points_geom = points_shp.geometry
    points_geom = points_geom.set_crs(epsg=4326)
    points_geom = points_geom.to_crs(src_CRS)

    # creating a holder for Otsu's threshold values
    otsu_thresholds = []
    skipped = 0
    
    # processing each point found
    for multipoint in points_geom:
        for point in multipoint.geoms:
            buffer = point.buffer(ksize * pixel_size, cap_style=3)
            buffer_series = gpd.GeoSeries(buffer)
            buffer_series.exterior.plot(ax=ax, color='red', linewidth=1)

            # writing NDWI to an in-memory dataset to use for masking
            ndwi_profile.update(count=1, nodata=0, dtype=rio.float32)
            with MemoryFile() as memfile:
                with memfile.open(**ndwi_profile) as mem_data:
                    mem_data.write_band(1, ndwi)
                with memfile.open() as dataset:
                    out_image, out_transform = mask(dataset, shapes=[buffer], nodata=0, crop=False)
                    temp_mask = np.ma.getmaskarray(out_image)
                    #plt.imshow(temp_mask[0])
                    #plt.show()
                    out_image = out_image[0]
                    out_image = (out_image * 127) + 128
                    out_image = out_image.astype(np.uint8)
                    #plt.imshow(out_image)
                    #plt.show()
                    
                    if out_image.shape[0] < 200 or out_image.shape[1] < 200:
                        skipped += 1
                        continue
                    else:
                        otsu_threshold, image_result = cv2.threshold(out_image, 0, 1, cv2.THRESH_BINARY + cv2.THRESH_OTSU, )
                        otsu_thresholds.append(otsu_threshold)
                        agg_mask = (agg_mask | np.ma.getmask(out_image).astype(np.uint8)).astype(np.uint8)
                        threshold_window = np.where(out_image >= otsu_threshold, 1, 0).astype(np.uint8)
                        label = label | threshold_window.astype(np.uint8)
    print("Total number of valid thresholds: {}".format(len(otsu_thresholds)))
    print("Number of skipped windows: {}".format(skipped))
    print("Actual thresholds (8-bit unsigned): \n{}".format(otsu_thresholds))
    print("Average threshold value (8-bit unsigned): {}".format(np.mean(otsu_thresholds)))
    print("Average threshold value (-1 to 1 NDWI range): {}".format((np.mean(otsu_thresholds) - 128) / 127))

    print("\nLabel max: {}".format(np.nanmax(label)))
    print("Label min: {}".format(np.nanmin(label)))
    plt.imshow(label)
    plt.show()

    print("\nMask max: {}".format(np.nanmax(agg_mask)))
    print("Mask min: {}".format(np.nanmin(agg_mask)))
    plt.imshow(agg_mask)
    plt.show()

    mean_threshold = np.mean(otsu_thresholds) + 10
    ndwi_8bit = ((ndwi * 127) + 128).astype(np.uint8)
    ndwi_classified = np.where(ndwi_8bit >= mean_threshold, 1, 0)
    plt.imshow(ndwi_classified, cmap="gray")
    plt.show()


            
    points_geom.plot(ax=ax, color='blue', markersize=5)
    plt.show()
    pass


boundary = {'type': 'Polygon',
            'coordinates': [[[-162.8235626220703, 66.05622435812153], 
                             [-162.674560546875, 66.05622435812153], 
                             [-162.674560546875, 66.10883816429516],
                             [-162.8235626220703, 66.10883816429516], 
                             [-162.8235626220703, 66.05622435812153]]]}
image_path = "data/369619_2016-08-29_RE1_3A_Analytic_SR_clip.tif"
# image_path = "data/268898_0369619_2016-10-15_0e14_BGRN_SR_clip.tif"
points_path = "data/Deering_transect_points_2016.shp"
get_ndwi_label(image_path, points_path)

# path_to_shp = "C:\\Users\\kjcar\\Downloads\\Deering_DSAS_Calculations\\WestChukchi_exposed_STepr_rates\\WestChukchi_exposed_STepr_rates.shp"
# clip_shp(path_to_shp, boundary)
