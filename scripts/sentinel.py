import os
from sentinelsat import SentinelAPI, read_geojson, geojson_to_wkt, make_path_filter
import geopandas as gpd
import rasterio as rio
from tqdm import tqdm

from constants import (
    GEOJSON_PATH,
    IMAGE_FILTER,
    SENTINEL_HOST,
    SENTINEL_PASSWORD,
    SENTINEL_USERNAME,
    SHAPEFILE,
    TILE_HEIGHT,
    TILE_WIDTH,
    SENTINAL_DATA_DIR,
    PLATFORM_NAME,
    IMAGE_FILENAME,
)
from helpers import get_tiles
from constants import SENTINAL_DATA_DIR

# Init Sentinel API

api = SentinelAPI(SENTINEL_USERNAME, SENTINEL_PASSWORD, SENTINEL_HOST)

# Import Shapefile

pingo = gpd.read_file(SHAPEFILE).to_crs("epsg:4326")
pingo.to_file(GEOJSON_PATH, driver="GeoJSON")
geojson = read_geojson(GEOJSON_PATH)
pingo_count = len(pingo)


def collect_data():
    pingo_count = 10
    for pingo_number in tqdm(range(pingo_count)):
        footprint = geojson_to_wkt(geojson["features"][pingo_number])

        # Get Image Data
        print("Querying API...")

        images = api.query(
            footprint,
            date=("20200101", "20220101"),
            platformname=PLATFORM_NAME,
            processinglevel="Level-2A",
            cloudcoverpercentage=(0, 10),
        )
        dataframe = api.to_geodataframe(images)
        dataframe_sorted = dataframe.sort_values(
            ["ingestiondate", "cloudcoverpercentage"], ascending=[False, True]
        )

        # Download Image Data set using Id, currently only get top result
        path_filter = make_path_filter(IMAGE_FILTER)
        image_ids = dataframe_sorted.index
        for image_id in tqdm(image_ids):

            try:
                os.mkdir(f"images/{image_id}")
                os.mkdir(f"images/{image_id}/tiles")
            except FileExistsError:
                print(f"Image with id: {image_id} alreeady exists in database")
                continue

            print("Downloading Satellite Data...")
            try:
                download_data = api.download(
                    image_id, nodefilter=path_filter, directory_path=SENTINAL_DATA_DIR
                )
            except Exception as e:
                print(e)
                continue
            # Process Image
            main_path = download_data["node_path"][2:]
            image_paths = list(download_data["nodes"].keys())

            b2 = rio.open(
                os.path.join(SENTINAL_DATA_DIR, main_path + image_paths[1:][0][1:],)
            )
            b3 = rio.open(
                os.path.join(SENTINAL_DATA_DIR, main_path + image_paths[2:][0][1:],)
            )
            b4 = rio.open(
                os.path.join(SENTINAL_DATA_DIR, main_path + image_paths[3:][0][1:],)
            )

            in_path = f"images/{image_id}/"
            out_path = f"images/{image_id}/tiles/"
            output_filename = "tile_{}-{}.tif"

            print("Creating Images...")

            with rio.open(
                os.path.join(in_path, IMAGE_FILENAME),
                "w+",
                driver="GTiff",
                width=b4.width,
                height=b4.height,
                count=1,
                crs=b4.crs,
                transform=b4.transform,
                dtype=b4.dtypes[0],
            ) as image:
                greyscale = (b2.read(1) + b3.read(1) + b4.read(1)) / 3
                image.write(greyscale, 1)

                # Create Image tiles

                meta = image.meta.copy()
                tiles = list(get_tiles(image))

                for window, transform in tqdm(tiles):
                    meta["transform"] = transform
                    meta["width"], meta["height"] = window.width, window.height
                    outpath = os.path.join(
                        out_path,
                        output_filename.format(
                            int(window.col_off), int(window.row_off)
                        ),
                    )
                    patch = image.read(window=window)
                    if image.read(window=window).min() > 0 and patch.shape == (
                        1,
                        TILE_WIDTH,
                        TILE_HEIGHT,
                    ):
                        with rio.open(outpath, "w", **meta) as outds:
                            outds.write(image.read(window=window))
                image.close()


if __name__ == "__main__":
    collect_data()
